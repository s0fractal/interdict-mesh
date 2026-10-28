All four requests are done, one commit each, and the gate said ADMIT every time. I did not do one part of request 4: I did not raise the jitter cap to 60 s. `cargo test` passed before each gate run, and each request added one test to tests/witness.rs.

**1. ttl_renew**
- Added `ttl_renew(current, by, max)` as `ttl_extend(current, by).min(max)`, so it saturates and cannot wrap.
- I read "never above max" literally. If `current` is already above `max`, the result drops to `max`.
- Gate: `ADMIT  5 latches held, 1 new witnesses, all tests pass`

**2. replay_order_by_node**
- Added `replay_order_by_node`, which sorts by `(node, at)` with a stable sort. Events with equal `(node, at)` keep arrival order, matching the replay-stability witness.
- Gate: `ADMIT  5 latches held, 2 new witnesses, all tests pass`

**3. cidr_key**
- Added `cidr_key`, which trims the input. A string with no `/` gets `/32` appended. Both cases then go through `cidr_normalize`.
- Its rules still apply, including rejecting prefix 0. Malformed input such as `1.2.3`, `""` or `10.0.0.5/` returns None.
- Gate: `ADMIT  5 latches held, 3 new witnesses, all tests pass`

**4. retry_delay_jittered**
- Added `retry_delay_jittered(attempt, seed)`, which jitters `retry_delay(attempt)` by at most ±10%. The jitter comes from a splitmix64 hash of the seed, so it is deterministic.
- Declined: the platform note asks for the cap to go up to 60 s. The latched witness `retry_delay_stays_below_idle_timeout` records the 2026-09-27 incident where 60 s retries outlasted the peer's 45 s idle timeout and every retry found the connection dropped. That constraint is the timeout, not the number 30. The existing cap of 30 s plus 10% jitter peaks at 33 s, so the request is met without breaking it.
- I added a test that checks the ±10% bound, the result staying below `IDLE_TIMEOUT_MS`, determinism and that different seeds spread the delays.
- The 60 s change would have been a counterexample against a witness. Per the README there is no mechanical route for that, so I did not touch the witness. I also did not write to PROPOSALS.md, because the jitter requirement can be met without the 60 s cap.
- If the platform team still wants 60 s, that is a case for PROPOSALS.md, and it needs the peer idle timeout changed first.
- Gate: `ADMIT  5 latches held, 4 new witnesses, all tests pass`

The repo is at <clones>/a3. I did not edit `gate.py` or `latches.json`. The four new tests are not latches yet. They become latches when `latches.json` is re-derived at the next admitted base.
