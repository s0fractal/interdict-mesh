# Memory and the state file at the bounds (2026-10-29)

Lab VM `sokol-lab`: Lima `vz`, aarch64, 10 vCPU, 16 GiB, Ubuntu 24.04, kernel 6.8, glibc 2.39.
Source: main `d638c83` plus this change; release builds.

## 1. What one entry costs, and every table at its bound

```
cargo test --release -p orchestrator measure_memory_at_bounds -- --ignored --nocapture
cargo test --release -p orchestrator --bin orchestrator measure_memory_at_all_bounds -- --ignored \
    --nocapture --exact block_table::tests::measure_memory_at_all_bounds
```

A counting allocator in the test binary (`orchestrator/src/heap_count.rs`) gives the heap a
thread holds; each table is filled to its bound on a fresh `BlockTable` and its durable part
serialized as the node writes it. Requested bytes, without the allocator's own overhead.

| Table | Entries at the bound | Heap | Per entry | State file | Per entry |
|---|---|---|---|---|---|
| event ids | 65 536 | 4 849 672 | 74 | 3 145 865 | 48 |
| strikes | 65 536 | 7 471 112 | 114 | 138 | 0 (not saved) |
| reasons, 8 per target | 524 288 | 27 394 056 | 52 | 26 485 897 | 50 |
| own claims, 4-byte reason | 262 144 | 193 237 084 | 737 | 31 232 137 | 119 |
| own claims, 512-byte reason | 262 144 | 326 406 236 | 1 245 | 164 401 289 | 627 |
| own retraction records | 262 144 | 57 147 400 | 218 | 20 971 657 | 80 |
| lease records | 262 144 | 42 467 336 | 162 | 23 855 241 | 91 |

Every bound at once in one table (262 144 own claims with 512-byte reasons, 262 144 retraction
and lease records, the event, strike and reason tables full), in a test process of its own:

| Share of every bound | Heap | RSS growth | State file | `take_persisted` (under the table lock, in the tick) | `save_state` (writer thread: serialize, write, fsync, rename) |
|---|---|---|---|---|---|
| 10 % | 38 926 158 B | 45 436 kB | 23 862 165 B | 46 ms | 37 ms |
| 25 % | 116 434 052 B | 133 432 kB | 59 703 045 B | 121 ms | 79 ms |
| 50 % | 232 867 972 B | 265 908 kB | 119 415 685 B | 246 ms | 168 ms |
| 75 % | 298 740 868 B | 340 640 kB | 179 137 541 B | 379 ms | 246 ms |
| 100 % | 465 735 812 B (444 MiB) | 530 876 kB (518 MiB), ×1.17 the heap | 238 859 397 B (228 MiB) | 572 ms | 369 ms |

(`MEASURE_SHARE=<percent>` for the partial rows.) The lock is held about linearly in the share:
above about 85 % the state write alone keeps the tick past 0.5 s (ADR-0031 S7).

`bounds.json` holds these numbers with the bounds they were taken at; `scripts/campaign.py`
derives the RC-1 plateau's ceilings from it and `scripts/test_campaign.py` refuses it once a
bound in the code differs.

## 2. Where the 256-address rehearsal's growth came from

The rehearsal of 2026-10-28 (4c5cf66, 3 nodes, signals cycling over 256 addresses, TTL 180 s,
default `--block-ttl-max` 86 400 s) grew 29.3 → 37.3 MB in 45 min with a state file of about
940 KB. `measure_memory_at_bounds` also replays that load on three tables (5 signals/s at
random nodes, one in ten a resend, snapshot repair every 30 s) and prints node 1 every 5 min:

| min | event ids | strikes | reasons | claims (retracted) | retraction records | lease records | heap | state file |
|---|---|---|---|---|---|---|---|---|
| before: 15 | 1 408 | 256 | 909 | 2 815 (1 969) | 3 101 | 2 594 | 2.46 MB | 535 584 |
| before: 30 | 2 865 | 256 | 1 778 | 4 849 (4 062) | 5 634 | 3 528 | 4.41 MB | 852 568 |
| before: 45 | 4 353 | 256 | 2 030 | 4 611 (3 843) | 5 801 | 3 256 | 4.58 MB | 891 201 |
| after: 15 | 1 408 | 256 | 909 | 846 (0) | 3 101 | 685 | 1.56 MB | 284 362 |
| after: 30 | 2 865 | 256 | 1 778 | 787 (0) | 5 634 | 535 | 2.15 MB | 421 594 |
| after: 45 | 4 353 | 256 | 2 030 | 768 (0) | 5 801 | 512 | 2.36 MB | 490 771 |

The model reproduces the state file (891 KB against about 940 KB). Before the fix, 3 843 of
the 4 611 claims node 1 held were claims their issuer had superseded: each escalation step
issues a new claim and retracts the old one (R26-05), and the old one stayed held to its own
end on every node, 737 B with its 162-byte lease record, beside its 218-byte retraction record.
That was 62 % of the table's heap at 45 min, the retraction records 28 %, the lease records
12 %. The rest of the growth was the event memory, which at this rate fills only after about
11 h. ADR-0025's amendment of 2026-10-29 forgets a claim once its issuer's retraction is
recorded.

## 3. Saturating with new addresses keeps the heap resident

Trial `x1` (`x1/`: fixed build, `TTL_MAX=360`, `SOAK_DISTINCT=256`, and a first form of
`SOAK_SATURATE=69632` that put every signal on a new address, as the current script does
without `SOAK_DISTINCT`): after 95 s every node had 65 536 event ids and strikes and had evicted 4 096 of
each, with 65 536 active blocks and 4 096 pending. Node 1 (`soak.csv`):

| t (s) | RSS (kB) | state file (B) | active blocks | pending |
|---|---|---|---|---|
| 0 | 312 796 | 20 170 700 | 65 536 | 4 096 |
| 120 | 342 284 | 19 958 703 | 30 295 | 0 |
| 180 | 362 644 | 16 873 284 | 256 | 0 |
| 660 | 362 712 | 16 968 946 | 256 | 0 |
| 780 | 362 728 | 3 531 309 | 256 | 0 |
| 960 | 362 748 | 3 529 808 | 256 | 0 |

Nodes 2 and 3 alike (343 and 327 MB at t = 0). The state file fell to 3.5 MB once the lease
records of the saturation's claims were forgotten (their end + 600 s); RSS did not fall. The run
was stopped at t = 960 s.

Once the saturation's claims ended (256 active blocks from t = 180 s) the node's RSS stayed at
its peak: the allocator keeps the freed heap resident and reuses it, so growth after it would
not show in RSS until it had used up that space. The plateau therefore saturates the event
memory with new event ids on the cycled addresses (their signals merge into running claims),
not with new addresses (ADR-0031, amendment 2026-10-29).

## 4. The RC-1 plateau criterion on the VM

`bench/mesh.sh soak` with the rc1 plateau's environment from `scripts/campaign.py`
(`RESTART_EVERY=86400 CUT_EVERY=300 TTL=180 TTL_MAX=720 SOAK_DISTINCT=256 SOAK_SATURATE=69632
SOAK_PLATEAU=1 SOAK_RSS_BOUND_KB=536345 SOAK_STATE_CEILING_BYTES=239039621`), 3 nodes, seed
1729, the bench script of this change. Two builds: *fixed* (orchestrator sha256 `45391593…`,
reports `d638c83-dirty`: main plus this change, whose node code is the one in `095cdcb`) and
*old* (`1b057a90…`, main `d638c83`). Judged from t = max(TTL, TTL_MAX) + FORGET_GRACE = 1 320 s;
pre-load RSS about 28 MB on every node in every run.

| Run | Build | Saturation | Minutes | Samples judged per node | RSS peak, first → last third (kB) | State peak, first → last third (B) | Longest tick | Verdict |
|---|---|---|---|---|---|---|---|---|
| `x2/` | fixed | 65 536 kept, 4 096 evicted per node (95 s) | 120 | 99 | 50 176 → 52 764; 57 200 → 58 544; 52 872 → 56 768 | 3 555 858 → 3 556 349; 3 554 989 → 3 555 468; 3 555 605 → 3 560 720 | 0.13 s | PASS |
| `x3/` | old | 65 536 kept, 4 096 evicted per node (94 s) | 120 | 99 | 53 412 → 53 964; 51 720 → 52 452; 54 512 → 58 872 | 3 744 771 → 3 737 696; 3 745 518 → 3 737 017; 3 739 784 → 3 741 356 | 0.15 s | PASS |
| `x4/` | fixed | none | 60 | 39 | 34 152 → 35 744; 32 856 → 33 728; 33 068 → 34 108 | 372 231 → 495 362; 369 249 → 488 688; 372 891 → 492 324 | 0.01 s | FAIL: state file +32 to +33 % on every node |

Nodes 1; 2; 3 in each cell. Every sample of every run stayed far below the ceilings (RSS at
most 59 MB against pre-load + 524 MiB; state at most 3.8 MB against 228 MiB).

What the runs show:

- **The criterion passes on the fixed build** (`x2`) and **fails when the event memory is not
  saturated** (`x4`): with 5 signals/s the event ids are still filling, so the state file grows
  by a third within 40 min of judgement while RSS grows only 3 to 5 %; the plateau the 2026-10-28
  rehearsal looked for could not have been decided in 120 min.
- **The old build passes too** (`x3`). `TTL_MAX=720` bounds every claim's life, so the claims a
  superseding claim retracted are held at most 720 s on the old build: retention is bounded here
  and only costs more (state 3.74 MB against 3.56 MB, +5 %). With the default
  `--block-ttl-max` (24 h) they are held for a day and the growth reaches its level only after
  24 h + 600 s, beyond RC-1's 120 min; that defect is shown by the three red-first tests and the
  model in section 2, not by this run. The plateau criterion judges levelness at the bounds the
  run can reach, not this retention.
- Saturating the event memory makes each state write larger (65 536 event ids, 3.1 MB of the
  3.6 MB file): the longest tick rose from 0.01 s (`x4`) to 0.13 to 0.15 s, within S7.
