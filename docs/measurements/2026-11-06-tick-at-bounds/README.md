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
tick skips its copy while the writer is behind. §3a measures that change.

## 3a. One copy per write (r4, 2026-11-07)

`persist_now` and the tick now copy only into a free handoff slot. A caller that finds the writer
behind waits for it, and a generation handed over after its call began covers its change
(`answers_waiting_for_the_disk_share_one_copy_per_write`: eight answers, 3 generations instead
of 9). r4 is r3's run on that build, `c77909f` (`build c77909f4e29f`). A second run of r3's code
(`build 1cefcdd6504e`, the same node code) reproduced r3: 0.860 s at most, 80 of 596 sampled
ticks over 0.5 s, RSS 1.86 GB.

| | r3 (a copy per answer) | r4 (one copy per write) |
|---|---|---|
| Claims held in the hold | 262 144 in every sample | 262 144 in every sample |
| Retractions answered in 600 s | 4 647 | **8 023** |
| Retraction round trip: p50 / p99 / max | 422 / 759 / 869 ms | **274 / 437 / 550 ms** |
| Signal round trip in the hold: p50 / p99 / max | 93 / 232 / 304 ms | **2 / 96 / 141 ms** |
| Tick in the hold, sampled: p50 / p90 / p99 / max | 0.321 / 0.547 / 0.755 / 0.881 s | **0.074 / 0.183 / 0.347 / 0.510 s** |
| Sampled hold ticks over 0.5 s | 82 of 597 | **1 of 596** |
| `interdict_tick_seconds_max` | 0.881 s | **0.631 s** |
| RSS in the hold, at most | 1 921 MB | **1 499 MB** |

**Still not within S7.** The longest tick was 0.631 s.
- Copies are now one per write of the state writer, but each still holds the table lock, about
  85 ms at this size. The tick takes the lock several times (expiry, kernel retries, the
  hand-off, the digest), and one of them can come after a copy.
- RSS stays above the derivation of §4. The copies are taken on whichever tokio worker thread
  answers, and the allocator keeps each thread's freed heap. This is not measured further here.

Both are open in ROADMAP 0a.

## 3b. Spaced copies (r6, 2026-11-07), and the allocator (r5)

Copies for the writer now start at least `COPY_SPACING` (4) times the last copy's length after it
started (`StateStore::copy_due_in`). Copies therefore hold the table lock at most a quarter of the
time, and a tick shorter than that gap either copies or waits behind one copy, not both
(`copies_are_spaced_by_their_length`). r6 is r3's run on that build, `260fedb` (`build 260fedb5e5d9`).

| | r3 | r4 | r5: r4 with `MALLOC_ARENA_MAX=2` | **r6: spaced** |
|---|---|---|---|---|
| `interdict_tick_seconds_max` | 0.881 s | 0.631 s | 0.828 s | **0.392 s** (in the hold) |
| Tick in the hold, sampled: p50 / p99 | 0.321 / 0.755 s | 0.074 / 0.347 s | 0.141 / 0.634 s | **0.010 / 0.285 s** |
| Sampled hold ticks over 0.5 s | 82 | 1 | 21 | **0** |
| Retractions in 600 s; round trip p50 / max | 4 647; 422 / 869 ms | 8 023; 274 / 550 ms | 5 507; 348 / 835 ms | 4 616; 516 / 942 ms |
| Signal round trip in the hold: p99 | 232 ms | 96 ms | 175 ms | **41 ms** |
| RSS in the hold, at most | 1 921 MB | 1 499 MB | 916 MB | 1 047 MB |

- **The claim bound is within S7 now.** With the claim table full and changed by retractions, no
  tick reached 500 ms. The longest was 0.392 s. Retractions are answered more slowly than in r4,
  since copies wait out their spacing. All answers stay within `DURABLE_WAIT` (2 s): at most
  0.942 s.
- **The allocator (r5).** With two malloc arenas instead of one per thread, RSS stayed at 916 MB,
  within §4's derivation (≈ 966 MB here). That is evidence that r4's 1.5 GB was heap kept per
  thread. But the tick got slower: 21 ticks over 0.5 s and 0.828 s at most. So it is not a fix.
  r6's spacing alone took RSS to 1.05 GB.
- **Every bound is not shown.** At every bound a copy holds the lock 0.218 s, not about 0.085 s
  (`measure_memory_at_all_bounds`). Adding the difference to r6's longest tick estimates
  ≈ 0.52 s, past S7 by about 20 ms. This is an estimate, not a measurement. What is left is the
  tick's own work under load (≈ 0.3 s: expiry, kernel retries, the digest). It is the next lever
  of ROADMAP 0a.

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
- `r1/` … `r6/`: `samples.csv`, `latency.json`, `replies.json`, `final-tick.txt`,
  `state-file.txt` and `version.txt` of each run.
