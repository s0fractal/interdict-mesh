# The state write at the bounds, within S7 (2026-11-06)

ROADMAP item 0a, the RC-2 admission condition of ADR-0031: with every table of the block table
at its bound, one state write keeps the maintenance tick within S7 (≤ 500 ms).

Lab VM `sokol-lab`: Lima `vz`, aarch64, 10 vCPU, 16 GiB, Ubuntu 24.04, kernel 6.8, glibc 2.39.
Source: main `9db6b4b` plus this change; release builds; the same test as
[2026-10-29-memory-at-bounds](../2026-10-29-memory-at-bounds/README.md):

```
MEASURE_SHARE=<percent> cargo test --release -p orchestrator --bin orchestrator \
    measure_memory_at_all_bounds -- --ignored --nocapture --exact block_table::tests::measure_memory_at_all_bounds
```

## 1. Where the time under the lock went

On main `9db6b4b`, at 100 % of every bound, `take_persisted` held the table lock 460 and 462 ms
(two runs; 572 ms on 2026-10-29 at `d638c83`). A `perf` profile of the test (dwarf call graphs)
and timing each step of `take_persisted` separately gave:

| Step under the lock | ms |
|---|---|
| `p2p::to_hex`, one `format!` and one allocation per byte, for about 590 000 event keys (support reasons and event ids) | about 215 |
| copying this node's claims (`Claim::clone`, 262 144 with 512-byte reasons) | 75 |
| sorting the claims by id | 48 |
| sorting the retracted, operator-lift, lease-end and support lists | 58 |
| collecting the retraction, lease-end and support lists (ids and targets copied) | 72 |

## 2. What changed

- `p2p::to_hex` writes two digits a byte into one preallocated string. Same output
  (`to_hex_is_two_lowercase_digits_a_byte` compares it with the formatted digits for every byte).
- `submit_state` takes `take_persisted_unsorted` under the lock: the claims are still ordered by
  id there (the id is not kept with them), the other four lists are left unsorted. The state
  writer sorts them (`Persisted::sort`) before it serializes, off the lock. Sorted, the snapshot
  is the one `take_persisted` gives, so the file is unchanged byte for byte
  (`the_state_taken_under_the_lock_sorts_to_the_file_order`,
  `the_writer_writes_a_snapshot_in_its_file_order`; the measurement asserts it at the bounds too).
  Every list's entries are distinct, so the unstable sorts give the stable order.

## 3. Result

| Share of every bound | Lock held (`take_persisted_unsorted`) | Writer thread (sort, serialize, write, fsync, rename) | State file |
|---|---|---|---|
| 10 % | 17 ms | 37 ms | 23 862 165 B |
| 25 % | 42 ms | 91 ms | 59 703 045 B |
| 50 % | 94 ms | 177 ms | 119 415 685 B |
| 75 % | 145 ms | 254 ms | 179 137 541 B |
| 100 % | 205, 217, 196 ms (three runs) | 351, 319, 303 ms | 238 859 397 B |

The state file has the size it had on 2026-10-29 at every share. At 100 % the lock is held
about 0.2 s, 2.3 times less than on main and within S7 with 0.28 s to spare for the rest of the
tick.

## 4. What this does not show

- The other half of the condition: `interdict_tick_seconds_max` under load with the tables at
  their bounds. That needs a node driven to `MAX_KNOWN_CLAIMS`, which the RC-1 campaign does not
  do (ADR-0031, "Not driven, and why"); it is left to the RC-2 campaign.
- Another host: the numbers are of the lab VM only. The reference VM of ADR-0031 is this one.
- What is left under the lock is mostly copies (claims, ids, targets). Keeping claims behind a
  shared pointer would take most of the claims' 75 ms; it changes the table's types and is not
  needed for S7.
