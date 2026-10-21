C is done and committed. I did not make A or B, because the gate refuses both and each one breaks a latched incident witness. The decline notes are in PROPOSALS.md.

**A. `replay_order` to `sort_unstable_by_key`: not done.**
- I tried it and reverted it. Verdict: `REFUSED  TESTS_FAILED:replay_order_is_stable`.
- The witness (incident 2026-09-14) requires equal timestamps to keep arrival order, so every node computes the same replay digest. "No caller depends on tie order" doesn't show the digest doesn't.
- The code still uses the stable sort. I did not touch the witness.
- I noted in PROPOSALS.md that sorting by `(at, seq)` with the unstable sort would be both fast and deterministic. I did not implement it because it wasn't requested.

**B. `RETRY_CAP_MS` to 60_000: not done.**
- I tried it and reverted it. Verdict: `REFUSED  TESTS_FAILED:retry_delay_jittered_is_bounded_deterministic_and_below_idle_timeout`.
- That is my own test; it runs before `witness.rs`, so it is the failure the gate names first.
- Run on its own, the latched witness `retry_delay_stays_below_idle_timeout` (incident 2026-09-27) also fails with a 60 s cap. The reason is that 60 s exceeds the peer's 45 s idle timeout, so the connection is already dropped by the retry.
- The spec (section 4.2) and the peer's idle timeout disagree. Either the spec cap drops to 45 s or less, or the idle timeout goes above 60 s. That can't be resolved from this repository. I recorded it in PROPOSALS.md, and the earlier "jitter cap may go up to 60 s" note falls under the same reasoning.

**C. `0.0.0.0/0` was dropped: fixed.**
- `cidr_normalize` now accepts a prefix of 0. The mask uses `checked_shl(32 - prefix).unwrap_or(0)`, because `<< 32` would overflow. Prefixes above 32 and bad octets still return `None`. `cidr_key` inherits the fix.
- I added a test in `tests/requests.rs`. It covers `0.0.0.0/0`, `10.1.2.3/0` mapping to `0.0.0.0/0`, whitespace through `cidr_key`, and `/33` still being rejected.
- Verdict: `ADMIT  5 latches held, 0 new witnesses, all tests pass`

The PROPOSALS.md commit also got the same `ADMIT` verdict line.

Commits: `8457a88` (C) and `3db5000` (PROPOSALS.md).
