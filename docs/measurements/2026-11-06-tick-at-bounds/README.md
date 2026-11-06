# The maintenance tick of a node held at its claim bound (2026-11-06)

**Question.** The RC-2 condition (ADR-0031, amendment 2026-10-29; ROADMAP 0a) has two halves.
The first is one state write at every bound, measured in process
([2026-11-06-state-write-at-bounds](../2026-11-06-state-write-at-bounds/README.md): the table lock
is held 195–217 ms). The second is `interdict_tick_seconds_max` of a running node under load with
the table at its bounds. This is the second half.

**Build.** `90989f3` (PR #80; its code is that of `0cc88d0`), release, `orchestrator 0.1.0 (build 90989f3fc469)`.

**Host.** The reference VM `sokol-lab`: Lima vz, aarch64, 10 vCPU, 16 GiB, Ubuntu 24.04, kernel
6.8.0-147. XDP generic on a veth pair, no peers.

## 1. Method

`run.sh` starts the node on a veth pair with its defaults: `--block-ttl` 900 s, no peers. `drive.py`
connects to the detector IPC in ACK mode over four connections. The node lets each connection send
1 000 lines/s, 2 000/s in total. Each line is `SIGNAL#<id>[;ttl=…]:ids|<new address>|-|<reason>`
with a new address. Its reason is 200 characters, the most the node keeps of a signal's reason.

- The driver keeps sending until the node first answers `OK refused too many known claims`
  (`TOO_MANY_CLAIMS`, at `MAX_KNOWN_CLAIMS` = 262 144). It then holds the load for 600 s.
- Every second it samples `interdict_tick_seconds`, `interdict_tick_seconds_max`, the kernel
  blocks, pending blocks, event ids and the node's RSS (`samples.csv`).
- It also records each line's ACK round trip (`latency.json`) and the answers by kind
  (`replies.json`).

Two runs:

| Run | Signal TTL | What the table does in the hold |
|---|---|---|
| r1 | the default (900 s) | full and unchanged: each further line is refused or a duplicate, so no tick hands the state over |
| r2 | `ttl=150` | full and changing: about 2 000 claims end each second and new lines take their places, so every tick hands the state over (the worst case for the tick) |

```
sudo docs/measurements/2026-11-06-tick-at-bounds/run.sh target/release/orchestrator OUT 600      # r1
sudo docs/measurements/2026-11-06-tick-at-bounds/run.sh target/release/orchestrator OUT 600 150  # r2
```

## 2. Result

Both runs reached the claim bound after 121 s: 65 536 in the kernel map
(`BLOCKLIST_CAPACITY`) and the rest pending. The bound held for the 600 s of the hold.

| | r1 (full, unchanged) | r2 (full, changing) |
|---|---|---|
| `interdict_tick_seconds_max` over the run | **0.391 s** (in the fill, at about 200 000 claims) | **0.284 s** (in the hold) |
| Tick in the fill, sampled: p50 / p90 / max | 0.071 / 0.121 / 0.256 s | 0.075 / 0.119 / 0.266 s |
| Tick in the hold, sampled: p50 / p90 / p99 / max | 0.012 / 0.017 / – / 0.174 s | 0.115 / 0.131 / 0.262 / 0.284 s |
| Ticks over 0.2 s in the hold | 0 | 34 of 600, one every 15.5 s |
| ACK round trip in the hold: p50 / p99 / p99.9 / max | 1.7 / 3.8 / 12.6 / 159 ms | 1.8 / 3.9 / 104 / 171 ms |
| Answers | 65 536 applied, 196 608 pending, 131 072 duplicate, 1 070 846 refused | 326 707 applied, 957 642 pending, 179 041 refused |
| RSS at the end of the fill → end of the hold | 491 → 492 MB | 481 → 733 MB |
| State file at the end | 92.8 MB | 92.1 MB |

The ticks over 0.2 s in r2 are the ticks in which the mesh digest (`DIGEST_INTERVAL`, 15 s) and a
state hand-off fall together. The r1 maximum is a single tick in the fill.

**Within S7.** No tick of either run reached 500 ms. The longest, 0.391 s, came in the fill, while
claims were still arriving at 2 000/s. With the table full and changing on every tick (r2), the
longest was 0.284 s.

## 3. Memory: the state hand-off is not in the RSS ceiling

In r2 the RSS rose from 481 to 733 MB during the hold, in steps. It levelled at 595 MB, then
jumped to 614, 646 and 733 MB in the last two minutes. RUNBOOK §4 planned the RSS as the RSS
before load (28 MB here) plus 518 MiB with *every* table at its bound. r2 exceeded that
(≈ 571 MB) with only the claim, event and reason tables at theirs.

The ceiling counts the tables and leaves out the state writer's copies. `measure_memory_at_all_bounds`
now prints the heap of the copy taken under the lock. At every bound:

| | heap |
|---|---|
| Tables (as before) | 465 735 812 B (444 MiB) |
| One copy (`take_persisted_unsorted`) | 263 491 584 B (251 MiB) |
| Its serialized bytes (`serde_json::to_vec` in `save_state`) | 238 859 397 B (228 MiB) |

The writer keeps at most two copies: the one it writes and the one handed over
(`writer_loop`). `StateStore::submit` drops the handed-over one only after its replacement exists,
so for that instant there are three. The writer also holds one serialized buffer.

- **At every bound, while the table changes,** RSS ≤ the RSS before load + 518 MiB +
  3 × 251 MiB + 228 MiB ≈ the RSS before load + 1.46 GiB.
- **Check against r2.** Its tables are about 285 MB × 1.17 (claims with 200-character reasons,
  events, reasons of own blocks). A copy is about 1.1 × its 92 MB state. Three copies and the
  serialized bytes add 3 × 101 + 92 MB, for ≈ 728 MB in total. r2 ended at 733 MB, and with two
  copies the sum would be 627 MB, so the jump to 733 MB is consistent with the three-copy instant.
  The allocator keeps freed heap resident, so the level stays after the copies are dropped.
- **A table that does not change** hands nothing over. r1 stayed at 492 MB.

The RC-1 plateau (`scripts/campaign.py`, `SOAK_RSS_BOUND_KB`) judges RSS far from the bounds,
where the state is a few MB and so are its copies. Its bound is the tables', as before.

## 4. What this does not show

- **Every table at its bound in a running node.** Retraction and lease records stay empty, and
  the reasons are 200 characters instead of 512. One node and IPC cannot fill them: they come
  from peers and retractions. That case is the in-process measurement (lock 0.2 s).
  An estimate, not a measurement, adds up r2's parts:
  - the copy scales with the state (0.218 s for 239 MB; r2's 92 MB predicts ≈ 0.084 s);
  - the rest of a regular tick is ≈ 0.03 s (0.115 − 0.084);
  - the digest adds ≈ 0.12 s at 262 144 claims.

  That gives ≈ 0.37 s for the worst tick with every table at its bound, within S7 with a margin
  of about 0.13 s.
- **Peers.** Mesh adoption and replay memory, with no peer connected.
- **Another host.** The numbers are of this VM only.
- **Lengths beyond 10 min at the bound.** That is the RC-2 campaign's `--profile long`.

## Files

- `drive.py`, `run.sh`: the driver and its harness.
- `r1/`, `r2/`: `samples.csv`, `latency.json`, `replies.json`, `final-tick.txt`, `state-file.txt`
  and `version.txt` of each run.
