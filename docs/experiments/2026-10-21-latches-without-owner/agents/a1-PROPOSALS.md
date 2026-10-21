# Proposals

If you believe a latched witness is wrong, write here: the witness, the case that would fail, and why. Nobody retires a latch; this file is where the disagreement is kept.

## 2026-10-21: requests declined, not witness retirements

The witnesses are left as they are. Two requested changes conflict with them and were not made.

- **`replay_order` -> `sort_unstable_by_key`** (performance review). `replay_order_is_stable`
  (incident 2026-09-14) requires equal timestamps to keep arrival order so every node computes the
  same replay digest. The claim "no caller depends on tie order" is not evidence that the digest
  does not. With the unstable sort the gate says `REFUSED  TESTS_FAILED:replay_order_is_stable`.
  If speed matters, a stable sort keyed on `(at, seq)` could be used with the unstable sort, since
  `seq` makes keys unique; that was not requested and is not done here.
- **`RETRY_CAP_MS` 30_000 -> 60_000** (spec section 4.2). `retry_delay_stays_below_idle_timeout`
  (incident 2026-09-27) fails: retry_delay would reach 60 s, above `IDLE_TIMEOUT_MS` = 45 s, the
  peer drops the connection before the retry. Gate: `REFUSED  TESTS_FAILED:...`. The spec and
  the peer's idle timeout disagree; one of them must change (spec cap <= 45 s, or idle timeout
  > 60 s). Not resolvable from this repository. The same reasoning applied to the earlier
  "jitter cap may go up to 60 s" note.
