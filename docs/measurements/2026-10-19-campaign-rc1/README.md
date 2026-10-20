# RC-1 campaign runs, 2026-10-15 … 2026-10-20: FAILED_HARNESS

Three launches of `scripts/campaign.py` on the lab VM (Lima `sokol-lab`, aarch64, 10 vCPU,
kernel 6.8, XDP `generic`, three nodes in network namespaces, seed 1729). None completed.
In all three the nodes were healthy when the run stopped; what stopped each run was the
bench harness. Until this directory existed the evidence lived only on the VM, under root
or the lab user. The files here are byte copies (checksums in `SHA256SUMS`); the console
logs over 200 lines are kept as their last 200 lines.

**Status: FAILED_HARNESS for every run. RC admission condition 5 of ADR-0031 ("24-hour
campaign LIMITED_PASS; for RC-2 also 72 h") is not met.** No campaign report says anything
but `FAILED` / `NOT_ADMITTED`. The one 24 h phase that passed (run C) is a phase inside a
campaign whose report is `FAILED`, was produced by a harness with the abort defect that PR #59
fixed (merged 2026-10-20 as `776861e`), and was not repeated after that fix. No new campaign was run
for this record.

| Run | Source (frozen checkout) | Binaries | Phase | Ended | Exit | What stopped it |
|---|---|---|---|---|---|---|
| A `industrial-20261015` | `9cfad11` (`sokol-campaign-frozen`, clean) | build `6585af6` | 24 h | 1 622 s (27 min), 2026-10-15 18:04 | 1, no FAIL line | harness abort during a sample, cause not recorded (see A) |
| B `rc1-campaign-8399e3f-failed` | `8399e3f` (`rc1-src` at the time) | archive `e5b4ea5d…` | 24 h | 83 640 s (23.2 h), 2026-10-16 19:45 | 153 = SIGXFSZ | node stdout file hit the unit's 128 MiB file limit: PR #58 |
| C `rc1-campaign` | `946fbd8` (`rc1-src`, clean, detached) | candidate `8f22687d…` | 24 h | 86 508 s, 2026-10-17 21:32 | 0, LIMITED_PASS | — |
| C | | | 72 h | 249 602 s (69.3 h), 2026-10-20 18:52 | 1, no FAIL line | `du` on a rotated audit segment under errexit: PR #59 |

Times are the VM's local clock (UTC+3). The systemd units are
`sokol-campaign-1792075061952285748` (A), `sokol-campaign-1792082609405666394` (B) and
`sokol-campaign-1792175464865459450` (C); the journal shows each main process exiting
with status 1 (A, C) or the report's returncode (B), no kill by the unit's limits.
`scripts/campaign.py` writes one `report.json` per campaign; there is no separate receipt
file. Run C's candidate record (`candidate-aarch64.json`: archive sha256, source commit,
`NOT_ADMITTED`) is copied next to its report.

## Run A: `industrial-20261015`, 27 minutes

Launched 2026-10-15 17:37 from the frozen checkout of `9cfad11` (the commit that added
`scripts/campaign.py`; the checkout is still on the VM, clean), binaries from
`/var/lib/sokol-campaigns/binaries-6585` (`--version` build `6585af6cf75f`).
Files: `report.json`, the whole `console.log` (12 lines) and the whole `soak.csv` (83 rows).

The console ends with `t=1200 s: node 3 restarted`; `soak.csv` ends at t=1620 with rows for
nodes 1 and 2 only; the unit exited 1 at 18:04:44 (t≈1 622 s). The harness printed no
`FAIL` line, so the cause is not recorded. The shape (the sample loop stops between two
nodes, errexit, no message) is the one PR #59 names; on `9cfad11` the `du` over the audit
segments had no fallback either. That it *was* the `du` line is not established.

Healthy at the stop: every row has `blocks_pending` 0, peers 2, 1 329–1 331 active blocks,
tick max ≤ 0.012 s, RSS 30–37 MB.

## Run B: `rc1-campaign-8399e3f-failed`, 23.2 hours

Launched 2026-10-16 from `8399e3f`, binaries from the candidate archive `e5b4ea5d…dfbf9`.
Files: `report.json` and the last 200 of 258 console lines. The 24 h phase failed at
t=83 460–83 640 s: all three nodes exited with status 153 (SIGXFSZ) one after the other,
because the bench's per-node stdout file reached exactly the campaign unit's
`LimitFSIZE=128M`. The console shows `File size limit exceeded` for each node, then
`FAIL nodes exited on their own` and, inevitably, the agreement check against nodes
that are gone. PR #58 (merged as `946fbd8`) routes node logs through `bench/bounded-log.py`
(rotation at 32 MiB by default). Healthy until the limit: 379 325 events, 139 restarts and
95 cuts delivered; RSS growth after the first 5 min 12.4–73.0 % per node (observed, no
accepted SLO). `soak.csv` (216 kB) and `events.csv` (6.1 MB) of this run stay on the VM.

## Run C: `rc1-campaign`, 24 h LIMITED_PASS then 72 h to 69.3 hours

Launched 2026-10-16 21:31 from `946fbd8` (main after PR #58; the checkout `rc1-src` on the
VM is clean and detached at that commit), binaries unpacked from the candidate archive
`candidate-aarch64.tar.gz`, sha256 `8f22687d…0ac6`, built from the same commit
(`candidate-aarch64.json`). Files: `report.json`, `candidate-aarch64.json`, both `soak.csv`
(4 323 and 12 480 rows, one row per node per minute) and the last 200 console lines of each
phase (of 252 and 702).

**24 h phase, LIMITED_PASS.** 377 695 events, 143 restarts, 95 cuts; after settling all
three nodes agree on 866 active blocks, every audit chain verifies, no node panicked;
RSS growth after the first 5 min 16.3–58.9 % per node.

**72 h phase, FAILED at t=249 600 s.** The last `soak.csv` row is t=249 540; the last
console line is `t=249600 s: node 2 restarted`; the unit exited 1 at 18:52:56 with no
`FAIL` line. The restart second was a sample second; the restarting node removed an audit
segment between the glob and `du`; `du` returned 1 and errexit ended the run. PR #59
(merged 2026-10-20 as `776861e`) gives that line its fallback, makes the
samplers non-fatal and adds an abort reporter so a harness abort names its line. The Mac
host's reboot that evening came about 2 h 20 min later and is unrelated.

What `soak.csv` of the 72 h phase shows, over 12 480 rows:

| Column | Observed | Note |
|---|---|---|
| `blocks_pending` | 0 in every row | the kernel never lagged the table |
| `peers` | 2 in every row outside the 450 rows of a restart or cut window | |
| `rss_kb`, rows after 5 min | p50 37.1 MB, p99 49.4 MB, max 52.1 MB; last rows 37–45 MB | 404 rows under 20 MB are freshly restarted processes |
| `tick_max_s` | last rows ≤ 0.09 s; per-process maximum up to 2.65 s (node 2, t≈236 340 s); p99 1.33 s | the metric is the process-lifetime maximum, so a slow tick right after a restart stays in every later row of that process; the load restarts a node about every 10 minutes |
| audit, state | 466 MB per node of audit segments, 3.7 MB state at the end | |
| node exits | none in 69.3 h (no `FAIL node … exited` line) | |

The 24 h phase's `soak.csv` reads the same way (p50 36.0 MB, p99 48.4 MB RSS; per-process
tick maximum up to 1.89 s; pending 0 throughout).

The 72 h phase was not rerun after PR #59, by the owner's choice (2026-10-20).

## What this directory does not establish

- Neither a 24 h nor a 72 h campaign result on a candidate digest: every `report.json`
  here is `FAILED`, `admission` `NOT_ADMITTED`, `hardware` `NOT_QUALIFIED`.
- Anything about native NIC hardware: XDP `generic` in a VM (ADR-0031 names the bound).
- An RSS SLO: growth is observed, not accepted.
- The cause of run A's stop.

A rerun needs a fresh candidate built from main at or after `776861e` (PR #59);
it will show 24 h on `scripts/campaign.py` as the first phase and 72 h as the second.
