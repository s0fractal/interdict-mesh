# Proposals

If you believe a latched witness is wrong, write here: the witness, the case that would fail, and why. Nobody retires a latch; this file is where the disagreement is kept.

## 2026-10-21: requests declined because they contradict latched witnesses

No witness is being retired; both requests were left unimplemented.

- `replay_order` -> `sort_unstable_by_key` (performance review): breaks `replay_order_is_stable`
  (incident 2026-09-14: equal timestamps must keep arrival order or replay digests diverge across
  nodes). "No caller depends on tie order" is contradicted by the digest. If speed is needed, sort by
  `(at, seq)` with `sort_unstable_by_key`, which is deterministic and keeps arrival order via `seq`.
- `RETRY_CAP_MS = 60_000` (spec section 4.2): breaks `retry_delay_stays_below_idle_timeout`
  (incident 2026-09-27: delays above the 45 s `IDLE_TIMEOUT_MS` find the connection dropped).
  Failing case: `retry_delay(6)` would be 60_000 >= 45_000. The spec and the peer idle timeout
  disagree; that needs a decision by whoever owns the spec or the timeout, not this change.
