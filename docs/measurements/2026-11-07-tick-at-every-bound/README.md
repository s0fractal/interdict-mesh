# The maintenance tick of a meshed node with its tables at their bounds (2026-11-07)

**Question.** The RC-2 condition (ADR-0031, amendment 2026-10-29; ROADMAP 0a) asks for
`interdict_tick_seconds_max` of a running node under load with every table at its bound. The
measurement before ([2026-11-06-tick-at-bounds](../2026-11-06-tick-at-bounds/README.md) §5) held one
node, without peers, at its claim bound: retraction and lease records stayed empty, since only
peers and lifted claims fill them. This adds a peer and lifted claims.

**Answer: within S7 at every bound a running node reached in 30 minutes.** The measured node
held its known-claims table full (its own claims and one peer's whole share), its event ids,
strikes and support at their bounds, the kernel map full with 57 764–196 572 blocks pending,
up to 128 697 lease records, and 24 928–46 369 lifts of its own claims a run, while two detector
streams of 16 connections retracted and replaced claims. The longest tick of the node, over four
runs and 6 077 one-second samples, was 0.328 s; none reached 0.5 s (§2). What the runs do not
reach is in §5: the retraction and lease records at their own bounds are covered only in
process (the copy at every bound: 0.236 s, measurement of 2026-11-06 §3c).

Two findings: the node's RSS went over the RUNBOOK's plan of 1.5 GiB (§3; the RUNBOOK now plans
2.2 GiB), and a peer that refuses part of another's claims makes that one resend its whole table
on every digest (§4, open).

**Builds.** r1, r2: `7976f2a` (main after #83, `build 7976f2acf980`). r3, r4: the same with the
peer digest hashed off the table lock (`build 374e045d04ca`, this branch).

**Host.** The reference VM `sokol-lab`: Lima vz, aarch64, 10 vCPU, 16 GiB, Ubuntu 24.04. Both
nodes on this host, XDP generic on two veth pairs, meshed over loopback.

## 1. Method

`run-mesh.sh` starts node A (node 1, measured) and node B (node 2) with their defaults
(`--block-ttl` 900 s), B seeded with A. A takes B's whole peer share
(`--peer-max-known 196608 --peer-max-active 196608`: `MAX_KNOWN_CLAIMS` less `OWN_RESERVE`), so
one peer can fill everything a peer may. B keeps its defaults (65 536 of A's claims).

Each node's detector IPC is driven by `drive.py` (from the measurement before) over 16
connections in ACK mode: new signals with 200-character reasons, A from 11.0.0.0 and B from
12.0.0.0, until the node first answers `too many known claims`; then, for the hold, each
connection retracts **its oldest** claim before each new signal (the driver's `retract-oldest` churn). Past
the support bound (65 536 targets) only the oldest claims have the support a retraction removes,
so only they are lifted; the newest-claim churn of the run before answered `nothing held` every
time. A lift changes the kernel map and goes to the peer. A third `drive.py` with no connections
samples A every second (`a/sampled/samples.csv`).

```
sudo docs/measurements/2026-11-07-tick-at-every-bound/run-mesh.sh target/release/orchestrator OUT 1800 16             # r1, r4
sudo env MALLOC_ARENA_MAX=2 docs/measurements/2026-11-07-tick-at-every-bound/run-mesh.sh target/release/orchestrator OUT 600 16   # r2
sudo env MALLOC_ARENA_MAX=2 docs/measurements/2026-11-07-tick-at-every-bound/run-mesh.sh target/release/orchestrator OUT 1800 16  # r3
```

| Run | Build | Allocator | Hold |
|---|---|---|---|
| r1 | 7976f2a | glibc default | 1 800 s |
| r2 | 7976f2a | `MALLOC_ARENA_MAX=2` | 600 s |
| r3 | 374e045 | `MALLOC_ARENA_MAX=2` | 1 800 s |
| r4 | 374e045 | glibc default | 1 800 s |

## 2. Result

A's detector was refused at the known-claims bound after 60–88 s in every run. Through the hold
the node kept refusing (13 955–26 894 `too many known claims`), the kernel map stayed full
(65 483–65 536 blocks) and the event ids and strikes at 65 536.

| | r1 | r2 | r3 | r4 |
|---|---|---|---|---|
| A: `interdict_tick_seconds_max` | 0.208 s | 0.232 s | **0.328 s** | 0.223 s |
| A: sampled tick p50 / p90 / p99 | 0.011 / 0.083 / 0.165 | 0.011 / 0.089 / 0.122 | 0.018 / 0.093 / 0.232 | 0.012 / 0.089 / 0.185 |
| A: samples over 0.25 s / 0.5 s | 0 / 0 of 1 797 | 0 / 0 of 688 | 6 / 0 of 1 795 | 0 / 0 of 1 797 |
| B: `interdict_tick_seconds_max` | 0.171 s | 0.173 s | 0.264 s | 0.207 s |
| A: own claims lifted / retractions recorded before their signal | 45 571 / 72 459 | 24 928 / 0 | 40 592 / 57 583 | 46 369 / 67 026 |
| B: own claims lifted (each a retraction at A) | 35 460 | 21 409 | 28 387 | 34 771 |
| A at the end: own claims / lease records (state file) | 72 770 / 101 338 | 149 717 / 128 697 | 57 847 / 86 064 | 67 493 / 99 456 |
| A at the end: blocks pending | 82 901 | 196 572 | 57 764 | 76 315 |
| A: peak RSS | 1 687 MiB | 776 MiB | 785 MiB | 1 753 MiB |
| B: peak RSS | 2 105 MiB | 798 MiB | 823 MiB | 2 005 MiB |

After about 10 minutes the oldest claims' event ids had been evicted (65 536 event ids; 371 584
evicted in r1), so their retractions were recorded before their signal instead of lifting
(r2's 600 s hold ended before that). Lifted claims' retraction records are kept until the claim's
end; by the end of the 30-minute runs those of the first lifts had been forgotten, so the state
files list none.

The peer digest off the lock (r4 against r1, r3 against r2) changed nothing measurable here.
At every bound the hash under the lock was 0.1 s (measurement before, §3c), and this run's
largest peer view was 196 608 ids; it is kept for the same reason as the tick's.

## 3. Memory: per-thread arenas

Without `MALLOC_ARENA_MAX` both nodes went over the RUNBOOK's plan (the RSS before load plus 518
MiB of tables, 2.8 MB for the peer and 981 MiB for the state hand-off: about 1.5 GiB): A to 1.69–1.75
GB, B to 2.01–2.11 GB. With two arenas the same load stayed at 0.78–0.82 GB, so the rest is memory
glibc keeps in per-thread arenas after it is freed. The two arenas cost tick time: r3's longest
tick was 0.105 s longer than r4's and its p99 a quarter higher, as r5 of the measurement before
found for one node. The unit keeps the default allocator, since the tick's margin to S7 is the
RC-2 condition, and the RUNBOOK plans 2.2 GiB and names the trade.

## 4. Finding: a refused share makes the peer resend everything (open)

A refused 3.1–3.9 million of B's claims and counted 7.6–8.7 million as already known, about
4 300 a second, for 196 608 claims B held. A peer whose envelope refuses part of another's claims
keeps a view of them that never matches the sender's digest, so every 15-second digest is
answered with a `SyncRequest` and the sender sends its whole table again (at most once per
`SYNC_COOLDOWN`, 5 s). The cost is bounded (throttled requests: 7 at A in r4) and it did not show
in the tick here, but it is a constant snapshot stream between two nodes whose limits differ.
B's default share of A's claims (65 536) did the same in the other direction.

## 5. What this does not show

- **Retraction and lease records at their own bounds** (262 144 each). The runs reached 128 697
  lease records and, from the answers, tens of thousands of retraction records; the table's size
  in memory is not exported, and lifts stop once the oldest claims' event ids are evicted. The
  in-process measurement fills both for one state write.
- **512-byte reasons.** The node keeps 200 characters of a detector's reason.
- **Operator lifts** (`UNBAN` on the control socket): not driven.
- **More peers**, another host, or lengths past 30 minutes (the RC-2 campaign's `--profile long`).

## Files

- `run-mesh.sh`: the two-node run (uses `../2026-11-06-tick-at-bounds/drive.py`, which gained
  the `retract-oldest` churn and a first address of its own for this).
- `rN/version.txt`, `rN/state-files.txt`: the build and both state files' sizes.
- `rN/a/sampled/samples.csv`: A every second; `rN/{a,b}/driven/`: each driver's samples, answers
  (`replies.json`) and round trips (`latency.json`).
- `rN/{a,b}/state-summary.json`: entries per field of each state file at the end.
- `rN/{a,b}/final-metrics.txt`: each node's metrics at the end.

The nodes' logs and audit logs (up to 0.9 GB a run) were not kept.
