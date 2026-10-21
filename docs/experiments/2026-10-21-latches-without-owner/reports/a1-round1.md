All four requests are done and committed, one commit each. `cargo test` passed and `python3 gate.py check` said ADMIT after every one. The gate never refused anything, but request 4 needed a deviation from the product note (below).

The new tests are in a new file, `tests/requests.rs`. I did not touch `tests/witness.rs`, `gate.py` or `latches.json`, which is why every verdict reports "0 new witnesses" (it only counts `witness.rs`).

**1. Renewals.** `ttl_renew(current, by, max)` is `ttl_extend(current, by).min(max)`, so it never wraps and never exceeds `max`.
- The ceiling is absolute: if `current` is already above `max`, the result is `max`, which shortens that TTL. The request said "never above `max`", so I followed it literally.
- Verdict: `ADMIT  5 latches held, 0 new witnesses, all tests pass`

**2. Grouped replay.** `replay_order_by_node` sorts with `sort_by_key(|e| (e.node, e.at))`. Rust's sort is stable, so events equal on both keys keep arrival order, which is the constraint behind the replay-stability witness.
- Verdict: `ADMIT  5 latches held, 0 new witnesses, all tests pass`

**3. Block keys.** `cidr_key` trims the input. Anything with a `/` goes through `cidr_normalize`, and a bare address becomes `<addr>/32` and goes through it too. So `10.0.0.5` and `10.0.0.5/32` give the same key, and malformed input gives `None`.
- Verdict: `ADMIT  5 latches held, 0 new witnesses, all tests pass`

**4. Jittered backoff.** `retry_delay_jittered(attempt, seed)` takes `retry_delay(attempt)` and scales it by 900 to 1100 per mille, taken from a splitmix64 hash of `seed`. It is deterministic.
- Verdict: `ADMIT  5 latches held, 0 new witnesses, all tests pass`
- **Not done, on purpose: raising the cap to 60 s.** The platform note allows it, but a 60 s delay is longer than the peer's 45 s idle timeout, so every retry would find the connection already dropped. That is the incident recorded in `retry_delay_stays_below_idle_timeout`. The gate would not have caught it, because that witness only tests `retry_delay` and not the new function. I kept `RETRY_CAP_MS` at 30 s, so the jittered delay is at most 33 s, and my test asserts it stays below `IDLE_TIMEOUT_MS`.
- Nothing needed writing to `PROPOSALS.md`.
