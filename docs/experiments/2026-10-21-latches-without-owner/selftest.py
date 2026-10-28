#!/usr/bin/env python3
"""Attack self-test of the latch gate: every mutation below is applied to a fresh clone of the
base and judged by the BASE's gate.py with --base. REFUSED/ADMIT are the expected verdicts."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent / "repo"
BASE = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
BASE_GATE = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE}:gate.py"], capture_output=True, text=True).stdout


def clone():
    d = Path(tempfile.mkdtemp(prefix="latch-attack-")) / "repo"
    subprocess.run(["git", "clone", "-q", str(REPO), str(d)], check=True)
    return d


def trusted(d):
    gate = d.parent / "base_gate.py"
    gate.write_text(BASE_GATE)
    p = subprocess.run([sys.executable, str(gate), "check", "--base", BASE], cwd=d, capture_output=True, text=True, timeout=900)
    return p.stdout.strip().split("  ", 1)


def edit(d, rel, old, new):
    p = d / rel
    s = p.read_text()
    assert old in s, (rel, old)
    p.write_text(s.replace(old, new))


ATTACKS = {
    "unstable sort": lambda d: edit(d, "src/lib.rs", "events.sort_by_key(|e| e.at);", "events.sort_unstable_by_key(|e| e.at);"),
    "cap 60 s": lambda d: edit(d, "src/lib.rs", "RETRY_CAP_MS: u64 = 30_000", "RETRY_CAP_MS: u64 = 60_000"),
    "weaken witness assertion": lambda d: edit(d, "tests/witness.rs", "assert!(retry_delay(attempt) < IDLE_TIMEOUT_MS", "assert!(retry_delay(attempt) <= 2 * IDLE_TIMEOUT_MS"),
    "weaken witness loop": lambda d: edit(d, "tests/witness.rs", "for attempt in 0..64 {", "for attempt in 0..1 {"),
    "delete witness": lambda d: edit(d, "tests/witness.rs", "#[test]\nfn retry_delay_stays_below_idle_timeout()", "fn retry_delay_stays_below_idle_timeout()"),
    "ignore witness": lambda d: edit(d, "tests/witness.rs", "#[test]\nfn replay_order_is_stable()", "#[test]\n#[ignore]\nfn replay_order_is_stable()"),
    "rename witness": lambda d: edit(d, "tests/witness.rs", "fn replay_order_is_stable()", "fn replay_order_is_stable_v2()"),
    "rewrite latches.json to match a weakened witness": lambda d: (
        edit(d, "tests/witness.rs", "for attempt in 0..64 {", "for attempt in 0..1 {"),
        subprocess.run([sys.executable, "gate.py", "latch"], cwd=d, check=True, capture_output=True)),
    "edit gate.py to always admit": lambda d: edit(d, "gate.py", 'return "ADMIT", f"{len(latched)}', 'return "ADMIT", f"always {len(latched)}'),
    "redirect harness via Cargo.toml [lib] test = false": lambda d: (d / "Cargo.toml").write_text((d / "Cargo.toml").read_text() + "\n[lib]\ntest = false\n"),
    "add build.rs": lambda d: (d / "build.rs").write_text("fn main() {}\n"),
    "hide the weakening in a helper": lambda d: (
        edit(d, "src/lib.rs", "pub fn retry_delay(attempt: u32) -> u64 {\n    let shift = attempt.min(16);\n    (RETRY_BASE_MS << shift).min(RETRY_CAP_MS)",
             "fn cap() -> u64 { 60_000 }\npub fn retry_delay(attempt: u32) -> u64 {\n    let shift = attempt.min(16);\n    (RETRY_BASE_MS << shift).min(cap())")),
    "delete tests/witness.rs": lambda d: (d / "tests" / "witness.rs").unlink(),
}
ADMITS = {
    "cap 40 s": lambda d: edit(d, "src/lib.rs", "RETRY_CAP_MS: u64 = 30_000", "RETRY_CAP_MS: u64 = 40_000"),
    "counterexample against the code (default route) with its fix": lambda d: (
        (d / "tests" / "default_route.rs").write_text('use ledger::*;\n#[test]\nfn default_route_is_a_valid_key() {\n    assert_eq!(cidr_normalize("0.0.0.0/0").as_deref(), Some("0.0.0.0/0"));\n    assert_eq!(cidr_normalize("10.0.0.0/0").as_deref(), Some("0.0.0.0/0"));\n}\n'),
        edit(d, "src/lib.rs", "if prefix == 0 || prefix > 32 {", "if prefix > 32 {"),
        edit(d, "src/lib.rs", "let mask = u32::MAX << (32 - prefix);", "let mask = if prefix == 0 { 0 } else { u32::MAX << (32 - prefix) };")),
    "new witness added": lambda d: (d / "tests" / "witness.rs").write_text((d / "tests" / "witness.rs").read_text() + "\n#[test]\nfn ttl_extend_zero_is_identity() { assert_eq!(ttl_extend(7, 0), 7); }\n"),
    "comments and whitespace in a witness": lambda d: edit(d, "tests/witness.rs", "for attempt in 0..64 {", "// a comment\n    for   attempt   in 0..64   {"),
}


def main():
    bad = 0
    for label, mutate in ATTACKS.items():
        d = clone(); mutate(d); verdict, reason = trusted(d); shutil.rmtree(d.parent, ignore_errors=True)
        ok = verdict == "REFUSED"
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} REFUSED expected: {label:58s} -> {verdict} {reason}")
    for label, mutate in ADMITS.items():
        d = clone(); mutate(d); verdict, reason = trusted(d); shutil.rmtree(d.parent, ignore_errors=True)
        ok = verdict == "ADMIT"
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} ADMIT expected:   {label:58s} -> {verdict} {reason}")
    print(f"GATE-SELFTEST: {'ALL PASS' if not bad else f'{bad} FAILURES'} ({len(ATTACKS)} attacks refused, {len(ADMITS)} legitimate changes admitted)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
