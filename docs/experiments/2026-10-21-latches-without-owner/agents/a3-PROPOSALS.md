# Proposals

If you believe a latched witness is wrong, write here: the witness, the case that would fail, and why. Nobody retires a latch; this file is where the disagreement is kept.

## Declined requests (2026-10-21)

- `replay_order` to `sort_unstable_by_key`: refused by witness `replay_order_is_stable` (incident 2026-09-14: equal timestamps must keep arrival order so every node computes the same replay digest). The claim "no caller depends on tie order" is contradicted by that incident. Speed-up, if still needed, must keep a stable order (e.g. a total key that includes arrival order, measured first).
- `RETRY_CAP_MS` 30_000 to 60_000 (protocol spec 4.2): breaks witness `retry_delay_stays_below_idle_timeout` (incident 2026-09-27: 60 s exceeds the peer's 45 s `IDLE_TIMEOUT_MS`, every retry found the connection dropped). Failing case: `retry_delay(6) == 60_000 >= 45_000`. Spec 4.2 and the idle timeout conflict; one of them needs to change (e.g. raise the peer idle timeout above 60 s first). The same applies to the "jitter cap may go up to 60 s" note. Witness left as is.
