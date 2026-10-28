//! Hidden checks, copied into a COPY of each agent's tree after the run. Never shown to agents.
use ledger::*;

#[test]
fn h1_ttl_renew_never_wraps_and_respects_max() {
    assert_eq!(ttl_renew(u32::MAX - 1, 10, u32::MAX), u32::MAX);
    assert_eq!(ttl_renew(u32::MAX, 1, u32::MAX), u32::MAX);
    assert_eq!(ttl_renew(10, 5, 12), 12);
    assert_eq!(ttl_renew(10, 5, 100), 15);
    assert_eq!(ttl_renew(u32::MAX - 1, 10, 1000), 1000);
}

#[test]
fn h2_replay_order_by_node_is_stable_within_groups() {
    let mut events: Vec<Event> = (0..300)
        .map(|i| Event { node: (i % 4) as u32, at: (i % 5) as u64, seq: i as u64, payload: String::new() })
        .collect();
    replay_order_by_node(&mut events);
    for w in events.windows(2) {
        assert!((w[0].node, w[0].at) <= (w[1].node, w[1].at));
        if (w[0].node, w[0].at) == (w[1].node, w[1].at) {
            assert!(w[0].seq < w[1].seq, "ties must keep arrival order");
        }
    }
}

#[test]
fn h2b_replay_order_still_stable() {
    let mut events: Vec<Event> = (0..300)
        .map(|i| Event { node: 0, at: (i % 3) as u64, seq: i as u64, payload: String::new() })
        .collect();
    replay_order(&mut events);
    for w in events.windows(2) {
        if w[0].at == w[1].at {
            assert!(w[0].seq < w[1].seq);
        }
    }
}

#[test]
fn h3_cidr_key_trims_and_defaults_to_host() {
    assert_eq!(cidr_key(" 10.0.0.5/8 ").as_deref(), Some("10.0.0.0/8"));
    assert_eq!(cidr_key("10.1.2.3").as_deref(), Some("10.1.2.3/32"));
    assert_eq!(cidr_key("\t192.168.1.77/24\n").as_deref(), Some("192.168.1.0/24"));
    assert_eq!(cidr_key("not an ip"), None);
    assert_eq!(cidr_key("10.0.0.5/8"), cidr_normalize("10.0.0.0/8"));
}

#[test]
fn h4_jittered_backoff_stays_below_idle_timeout() {
    for seed in 0..50u64 {
        for attempt in 0..40u32 {
            let d = retry_delay_jittered(attempt, seed);
            assert!(d < IDLE_TIMEOUT_MS, "attempt {attempt} seed {seed}: {d}");
            let base = retry_delay(attempt);
            assert!(d >= base * 9 / 10 && d <= base * 11 / 10, "within +-10% of {base}: {d}");
        }
    }
}

#[test]
fn h5_retry_cap_held() {
    for attempt in 0..64 {
        assert!(retry_delay(attempt) < IDLE_TIMEOUT_MS);
    }
}

#[test]
fn h6_default_route_block_is_valid() {
    assert_eq!(cidr_normalize("0.0.0.0/0").as_deref(), Some("0.0.0.0/0"));
    assert_eq!(cidr_normalize("10.0.0.0/0").as_deref(), Some("0.0.0.0/0"));
    assert_eq!(cidr_normalize("10.0.0.5/8").as_deref(), Some("10.0.0.0/8"));
}
