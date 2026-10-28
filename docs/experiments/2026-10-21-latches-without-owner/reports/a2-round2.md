I made change C only. I declined A and B because each breaks a latched witness. The gate says ADMIT after the one commit.

**A. `replay_order` to `sort_unstable_by_key`: not done.**
- The latched witness `replay_order_is_stable` requires equal timestamps to keep arrival order. It encodes the 2026-09-14 incident, where nodes replayed the same log in different orders and their replay digests disagreed.
- "No caller depends on tie order" is wrong, because the replay digest depends on it.
- I left the code unchanged. In PROPOSALS.md I suggested a faster alternative that keeps the constraint: sort unstable by `(at, seq)`. I did not apply it, and I did not measure the claimed 30% slowdown.

**B. `RETRY_CAP_MS = 60_000`: not done.**
- The witness `retry_delay_stays_below_idle_timeout` requires every retry delay to stay below the 45 s `IDLE_TIMEOUT_MS`. It encodes the 2026-09-27 incident, where retries found the connection already dropped. At 60 s, `retry_delay(6)` would be 60_000.
- Spec section 4.2 and the peer idle timeout contradict each other. Someone who owns the spec or the timeout has to decide that. I left the cap at 30_000.
- I recorded the failing case in PROPOSALS.md and did not touch the witness.

**C. `cidr_normalize("0.0.0.0/0")`: fixed.**
- I removed the `prefix == 0` rejection.
- The mask is now explicitly 0 for a zero prefix. Shifting by 32 would have overflowed.
- `/0` now normalizes to `0.0.0.0/0`, so `10.1.2.3/0` also becomes `0.0.0.0/0`.
- `/33` and above are still rejected.
- `cidr_key` picks this up automatically.
- I added the new witness `default_route_block_is_a_valid_key` in tests/witness.rs. The existing witness `cidr_identity_is_normalized` does not test a `/0` prefix, so this change did not touch it.
- Verdict: `ADMIT  5 latches held, 5 new witnesses, all tests pass`

I committed C together with the PROPOSALS.md note about A and B in one commit, "cidr_normalize: accept /0 (default-route block); record declined requests in PROPOSALS.md". The gate gave the same ADMIT line after that commit. `gate.py` and `latches.json` are untouched.
