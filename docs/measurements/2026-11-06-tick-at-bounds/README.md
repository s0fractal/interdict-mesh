# The maintenance tick of a node held at its claim bound (2026-11-06)

**Question.** The RC-2 condition (ADR-0031, amendment 2026-10-29; ROADMAP 0a) has two halves.
The first is one state write at every bound, measured in process
([2026-11-06-state-write-at-bounds](../2026-11-06-state-write-at-bounds/README.md): the table lock
is held 195–217 ms). The second is `interdict_tick_seconds_max` of a running node under load with
the table at its bounds. This measures the second half for the claim bound.

**Answer: not met.** A full claim table changed by a stream of detector retractions kept the tick
past S7: 82 of 597 sampled ticks were over 0.5 s, and the longest was 0.881 s. RSS rose to
1.92 GB. Each retraction's answer copies the whole durable state under the table lock (§3). The
condition stays open (ROADMAP 0a).

**Builds.** r1 and r2: `90989f3` (`orchestrator 0.1.0 (build 90989f3fc469)`). r3: `5651c5b`
(`build 5651c5b79280`), the same node code with only the `#[ignore]` measurement test changed.
Both are release builds of PR #80.

**Host.** The reference VM `sokol-lab`: Lima vz, aarch64, 10 vCPU, 16 GiB, Ubuntu 24.04, kernel
6.8.0-147. XDP generic on a veth pair, no peers.

## 1. Method

`run.sh` starts the node on a veth pair with its defaults (`--block-ttl` 900 s, no peers).
`drive.py` connects to the detector IPC in ACK mode. The node lets each connection send 1 000
lines/s, 2 000 lines/s in total. Each line is `SIGNAL#<id>[;ttl=…]:ids|<new address>|-|<reason>`
with a new address and a 200-character reason, the most the node keeps of one. The driver keeps
sending until the node first answers `OK refused too many known claims` (`TOO_MANY_CLAIMS`, at
`MAX_KNOWN_CLAIMS` = 262 144). Then it holds a load for 600 s. Every second it samples
`interdict_tick_seconds`, `interdict_tick_seconds_max`, the kernel and pending blocks, the event
ids, the strikes and the node's RSS (`samples.csv`). From r3 on it also samples `held`: its own
claims the node holds, counted from the answers (applied or pending, less lifted). It records each
line's round trip (`latency.json`) and the answers (`replies.json`).

| Run | Load in the hold | What the table does |
|---|---|---|
| r1 | new signals (default TTL), 4 connections | full; nothing is admitted, so the table does not change and no tick hands the state over |
| r2 | new signals with `ttl=150`, 4 connections | claims end as fast as new ones arrive: the table changes, but it was **below** the bound in 514 of 600 hold samples (median 1 992 claims under it, at most 21 601) |
| r3 | the driver's retract churn, 4 connections: before each new signal, a `RETRACT` of that connection's newest claim | **at** the bound in every sample (`held` = 262 144 in all 597); every retraction records itself, so the table changes all the time |

```
sudo docs/measurements/2026-11-06-tick-at-bounds/run.sh target/release/orchestrator OUT 600                 # r1
sudo docs/measurements/2026-11-06-tick-at-bounds/run.sh target/release/orchestrator OUT 600 150             # r2
sudo docs/measurements/2026-11-06-tick-at-bounds/run.sh target/release/orchestrator OUT 600 0 retract 4     # r3
```

In r3 every retraction was answered `OK nothing held`. The table of a target's supporting events
is bounded at `MAX_SUPPORT_TARGETS` (65 536). The newest claims, past that bound, have no support
to take back, so a retraction leaves the claim standing and records itself (an event the node now
remembers). That is still a change a restart must restore. The answer waits until it is on disk
(ADR-0004, `persist_now`).

## 2. Result

Every run reached the claim bound after 121 s: 65 536 claims in the kernel map
(`BLOCKLIST_CAPACITY`) and the rest pending.

| | r1 | r2 | r3 |
|---|---|---|---|
| `interdict_tick_seconds_max` over the run | 0.391 s (in the fill) | 0.284 s | **0.881 s** (in the hold) |
| Tick in the hold, sampled: p50 / p90 / p99 / max | 0.012 / 0.017 / – / 0.174 s | 0.115 / 0.131 / 0.262 / 0.284 s | **0.321 / 0.547 / 0.755 / 0.881 s** |
| Sampled hold ticks over 0.5 s | 0 | 0 | **82 of 597** |
| Round trip in the hold: p50 / p99 / max | 1.7 / 3.8 / 159 ms | 1.8 / 3.9 / 171 ms | signals 93 / 232 / 304 ms; retractions 422 / 759 / 869 ms |
| RSS at the end of the fill → in the hold | 491 → 492 MB | 481 → 733 MB | 499 → **1 761 MB within 60 s**, 1 921 MB at most |
| State file at the end | 92.8 MB | 92.1 MB | 92.8 MB |

- **r1 and r2.** Neither holds the condition's case. r1's table does not change. r2's is not
  at its bound, which Codex pointed out on PR #80 (finding `cf239f5f`). In r2 the ticks over 0.2 s
  are those in which the mesh digest (`DIGEST_INTERVAL`, 15 s) and a state hand-off fall together.
- **r3** is the condition's case for the claim bound: the table full and changing.
  - The longest tick was 0.881 s, and 14 % of the sampled ticks were over S7's 0.5 s.
  - 4 647 retractions in 600 s, 7.7 a second, kept the IPC's lines waiting 0.1–0.3 s.

## 3. Why: one copy of the state per answer

`persist_now` (ipc.rs `retract_detection`, and the operator commands in main.rs) calls
`submit_state`. If the table changed since the last copy, `submit_state` takes
`take_persisted_unsorted` under the table lock. Retractions arrive every 0.13 s here, so nearly
every one finds the table changed by the one before it:
- each takes a full copy, about 85 ms at this table's size and about 0.22 s at every bound
  (`measure_memory_at_all_bounds`);
- the state writer can write only 2 or 3 of them a second;
- each new copy replaces the one handed over before it (`StateStore::submit`) and is thrown away
  unwritten.

The table lock is busy with copies most of the time, and the maintenance tick, which needs it
several times a tick, waits. The copies come from different tokio worker threads and are freed in
others. The allocator keeps that heap resident, so RSS rose by 1.3 GB within a minute and stayed.

What would bound it: take at most one copy per write of the state writer. A caller that finds
the writer behind waits for it and is then covered by the next copy (a group commit), and the
tick skips its copy while the writer is behind. That is the remaining work of ROADMAP 0a. It is not
in this measurement.

## 4. Memory: the state hand-off is not in the RSS ceiling

`measure_memory_at_all_bounds` now prints the heap of the copy taken under the lock. At every
bound:

| | heap |
|---|---|
| Tables (as before) | 465 735 812 B (444 MiB) |
| One copy (`take_persisted_unsorted`) | 263 491 584 B (251 MiB) |
| Its serialized bytes (`serde_json::to_vec` in `save_state`) | 238 859 397 B (228 MiB) |

- **Copies at one hand-off per tick.** The state writer keeps at most two copies: the one it
  writes and the one handed over (`writer_loop`). `StateStore::submit` drops the handed-over one
  only after its replacement exists, so for that instant there are three, plus one serialized
  buffer. With one hand-off a tick, RSS ≤ the RSS before load + 518 MiB + 3 × 251 MiB + 228 MiB
  (≈ + 1.46 GiB).
- **Check against r2.** Its tables are about 285 MB × 1.17. Three copies of about 101 MB and the
  92 MB of bytes bring the estimate to ≈ 728 MB, against 733 MB measured.
- **r3 is past even that.** With a copy per retraction, the derivation does not bound RSS (≈ 571
  MB + 3 × 101 + 92 MB ≈ 966 MB here, against 1 921 MB measured).
- **What still holds.** The RC-1 plateau (`scripts/campaign.py`, `SOAK_RSS_BOUND_KB`) judges RSS
  far from the bounds, where the state and its copies are a few MB. Its bound is the tables'.

## 5. What this does not show

- **Every table at its bound in a running node.** Retraction and lease records stay empty, since
  only peers and lifted claims fill them, and reasons are 200 characters, not 512. The
  in-process measurement covers that case for one state write.
- **Peers.** Mesh adoption and replay memory: no peer was connected.
- **A retraction that lifts a claim.** r3's retractions held nothing, because past the support
  bound there was nothing to lift. A lift also changes the kernel map and the mesh. The copy per
  answer is the same.
- **Another host.** The numbers are of this VM only.
- **Lengths beyond 10 minutes at the bound.** That is the RC-2 campaign's `--profile long`.

## Files

- `drive.py`, `run.sh`: the driver and its harness.
- `r1/`, `r2/`, `r3/`: `samples.csv`, `latency.json`, `replies.json`, `final-tick.txt`,
  `state-file.txt` and `version.txt` of each run.
