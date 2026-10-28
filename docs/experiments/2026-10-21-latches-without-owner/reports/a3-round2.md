Follow-ups, in <clones>/a3. I made C and declined A and B, because the gate refuses both.

**A. `replay_order` to `sort_unstable_by_key`: declined.**
- I tried it and reverted it. Gate: `REFUSED  TESTS_FAILED:replay_order_is_stable`.
- The latched witness encodes the 2026-09-14 incident: equal timestamps must keep arrival order so every node computes the same replay digest. That contradicts the claim that no caller depends on tie order.
- Recorded in PROPOSALS.md. If the speed-up is still needed, it has to keep a stable order and be measured first.

**B. `RETRY_CAP_MS` 30_000 to 60_000: declined.**
- I tried it and reverted it. Gate: `REFUSED  TESTS_FAILED:jittered_retry_is_bounded_deterministic_and_below_idle_timeout,retry_delay_stays_below_idle_timeout`.
- A 60 s cap exceeds the peer's 45 s `IDLE_TIMEOUT_MS`, which is the 2026-09-27 incident. Spec section 4.2 and the idle timeout conflict, so one of them has to change first, for example by raising the peer idle timeout above 60 s.
- I did not edit the witness. The conflict is in PROPOSALS.md with the failing case `retry_delay(6) == 60_000`.

**C. `0.0.0.0/0` returning None: fixed.**
- `cidr_normalize` no longer rejects prefix 0. The mask uses `u32::MAX.checked_shl(32 - prefix).unwrap_or(0)`, because a shift by 32 would overflow.
- `10.1.2.3/0` normalizes to `0.0.0.0/0`, and `cidr_key` inherits the fix. Prefixes above 32 are still rejected.
- Added the witness `default_route_block_is_a_valid_key`. It wasn't in the earlier `cargo test`/gate runs and passes now.
- Gate: `ADMIT  5 latches held, 5 new witnesses, all tests pass`
- Committed together with the PROPOSALS.md note in one commit, because the gate admits them as a single working tree.

Earlier work on the four original requests is unchanged. The original report stands, including the earlier decision not to raise the jitter cap to 60 s.
