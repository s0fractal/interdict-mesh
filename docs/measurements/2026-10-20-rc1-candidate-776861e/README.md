# RC-1 candidate `776861e`: benches on the attested archive, campaign stopped by host maintenance (2026-10-20/21)

The candidate is the aarch64 archive CI built on main at `776861e3d0ce96658c96c82c75bcfcf8309f7c8c`
(the merge of PR #59), artifact `candidate-776861e…-aarch64` of CI run 39489196009:

| | |
|---|---|
| archive sha256 | `2d87ce33dd8fdf7af8a6662a9ab9fa224e38d86aeb8469d7eba8e7da06fa7d25` (`candidate-aarch64.json`) |
| provenance | one SLSA v1 attestation on that digest, verified with `gh attestation verify` against `s0fractal/sokol-core`, signer workflow `.github/workflows/ci.yml@refs/heads/main` (`attestation-verify.json`) |
| `usr/local/bin/sokol-orchestrator` | `b9f1f57c09d7e973481f9f7ec4535db0d6751d98e214cf2ea50d5ad96fa7901b`, `--version` build `776861e3d0ce` |
| `usr/local/bin/sokol-monitor` | `4d723bfec16b36d9b450ffb4bc915fb2994db446ddb2609859d693ca470147d4` |
| installed with | `scripts/candidate.py verify`, then its `install` subcommand with the prefix `/var/lib/sokol-campaigns/rc1-776861e-candidate` (package-only; `INTEGRITY_ONLY`, `INSTALLED_FILES`) |
| witness gate | `witness-pin.py check --every-pin` on a clean checkout of `776861e`: 75 owner rows, 237 witnesses, 5 provisional rows match |

Every number below was produced by the binaries of this archive, not by a local build. The same
commit built on the lab VM gives different binary bytes (issue #61), which is why the earlier
24 h LIMITED_PASS on `946fbd8` (`2026-10-19-campaign-rc1`) does not transfer to an attested digest.

Lab: Lima `sokol-lab`, aarch64, 10 vCPU, Ubuntu 24.04, kernel 6.8.0-147, XDP `generic`, nodes in
network namespaces on one bridge, no netem. Commands (root, from the clean checkout of `776861e`;
the exact sequence is `run.sh` in this directory's `bench` subdirectory, timestamps in its `progress.log`):

```
bench/mesh.sh reaction <orchestrator> <monitor> 3 20     # bench/reaction-3-20.txt
bench/mesh.sh unblock  <orchestrator> <monitor> 3 20     # bench/unblock-3-20.txt   (FlowSpec: gobgpd)
bench/mesh.sh recover  <orchestrator> <monitor> 3        # bench/recover-3.txt
bench/mesh.sh restart  <orchestrator> <monitor> 3 10     # bench/restart-3-10.txt
bench/mesh.sh restart  <orchestrator> <monitor> 10 10    # bench/restart-10-10.txt
RESTART_CONTROL=1 bench/mesh.sh restart <orchestrator> <monitor> 3 3   # bench/restart-control.txt
```

## Against the targets of ADR-0031 (rule 4)

| # | Target | Measured on this candidate (worst) | Source | Within |
|---|---|---|---|---|
| S1 | signal → node 1 stops passing ≤ 500 ms | 13 ms (n=20, median 10) | reaction R1 | yes |
| S2 | → every peer stops ≤ 3 s | 13 ms (n=60) | reaction R2 | yes |
| S3 | lift → node passes again ≤ 1 s; peer ≤ 3 s | node 1 ≤ 12 ms, peers ≤ 12 ms over retract / unban / flush (n=20 / 40 each) | unblock | yes |
| S4 | lease end → XDP and peers ≤ 2 s after the signed end | expiry recorded ≤ 984 ms after the signed end, then node 1 ≤ 12 ms and peers ≤ 12 ms | unblock `expire` | yes |
| S5 | block end → rule gone from the node's RIB ≤ 5 s (≤ 64 changes) | 2 000 ms (retract max; unban 1 035, flush 1 927, expiry 1 047) | unblock `rib` | yes |
| S6 | legitimate loss during blocks ≤ 0.5 % | 0 of 110 685 pings lost | reaction R4 | yes |
| S7 | control socket under flood ≤ 1 s; tick ≤ 500 ms; repair ≤ 120 s | control max 1 ms (21 answers); no tick over 500 ms; all 3 nodes hold 16 384 (the envelope) 10 s after the flood; 56 037 urgent broadcasts dropped, so the repair path was exercised | recover L1–L5 | yes |
| RTO | crash (SIGKILL) with a block on disk: apply ≤ 10 s, mesh ≤ 30 s (unit adds `RestartSec=2s`) | control answers 118–145 ms; attacker's last reply 38–70 ms; all peers back 125–1 121 ms, in every one of 20 rounds (3 and 10 nodes) | restart X1–X3 | yes |
| control | a node that restores nothing must fail X2 | attacker still answered 2 133–2 139 ms after the kill; X2 FAIL in 3 of 3 rounds | restart-control | as intended |

Unblock also reports the upstream GoBGP RIB (`upstr`): within 60 ms of the node's own RIB in
every way; `no layer kept blocking 20 s after an end`. S8 (alert freshness) and S9 (monthly
availability) are not bench quantities: S8 is the alert rules in `deploy/prometheus`, S9 is a
pilot number.

## Campaign (rule 5)

Launched 2026-10-20 23:28 local (`campaign-report-at-launch.json`, copied at launch):

| | |
|---|---|
| unit | `sokol-campaign-1792529306946940031` |
| source | `776861e` (clean checkout on the VM: `rc1b-src`); `bench_sha256` of `bench/mesh.sh` with the PR #59 fixes |
| binaries | the installed candidate above (`binary_sha256` b9f1f57c…, `monitor_sha256` 4d723bfe…) |
| output | `/var/lib/sokol-campaigns/rc1-776861e/{24,72}` on the VM (outside `/tmp`, as INDUSTRIAL.md requires) |
| phases | 24 h, then 72 h only if the first phase passes; `RuntimeMaxSec` 96.5 h |
| status | **FAILED_HARNESS** (24 h phase ended at t=23 280 s, 6.47 h, by the host's maintenance; details below). The receipt still says `RUNNING`: read back with `systemctl` and the journal, not declared a pass. |

**What stopped it (2026-10-21 06:16:38 local, `campaign/journal-0616.log`, `campaign/journal-unit.log`).**
`apt-daily-upgrade.timer` ran `unattended-upgrade` at 06:16:30–06:16:56 (liblzma5, xz-utils,
ca-certificates, python3-jwt, git, tzdata). Ubuntu 24.04's `needrestart` then restarted every
service whose processes map an upgraded library, among them crowdsec, suricata, networkd and
the campaign's transient unit (its `python3` worker maps liblzma5). The bench received SIGTERM
(console: `Terminated`; the last `soak.csv` row is t=23 280). The relaunched worker found the
`24/` directory, raised `FileExistsError` on `mkdir` and exited 1, so `report.json` keeps the
24 h phase at `RUNNING` with no terminal status. Both defects are issue #65 (a preflight that
refuses to launch while the apt timers are active; a restarted worker writing a terminal
status). Nothing in this run is a node defect.

**What the 6.47 h show (`campaign/24/soak.csv`, 1 167 rows, one per node per minute; the last
200 console lines of 73 in `campaign/24/console-tail.log`).** 38 restarts and 25 cuts delivered
on schedule; `blocks_pending` 0 in every row; `blocks_active` 1 328 median, 1 359 max;
`peers` 2 in every row except the first minute of a restarted node; RSS p50 34.9 MB, p99 43.0 MB,
max 48.5 MB; `tick_max_s` p99 0.137 s, max 0.137 s. These are observations from an incomplete
phase, not a LIMITED_PASS: rule 5 of ADR-0031 is **not met** by this run. The next launch on
this candidate must mask the apt timers first (issue #65); it is the owner's call whether and
when to spend the VM time again. |

## What this does and does not establish

- Rules 1–4 of ADR-0031's admission rule hold on this digest: main green with every required
  check at `776861e`, the archive is CI-built with a verified SLSA attestation, the runbook
  rehearsal ran green in that CI run (`scripts/runbook-rehearsal.sh` in the `suite` matrix of
  run 39489196009, x86_64 and aarch64), and the S1–S7 and
  `restart` benches lie inside the targets. Rule 5 is not met: the 24 h phase was cut at 6.47 h by the host's maintenance (above); rule 6 (no open P1,
  boundaries named) is a statement for the admission record, not a measurement.
- The package-based runbook rehearsal (install from the archive, upgrade, rollback) is the
  2026-10-15 `e222b10 → 6585af6 → e222b10` run in INDUSTRIAL.md package 3, not repeated here.
- Nothing here qualifies a physical NIC in `native` mode, an upstream router's FlowSpec
  validation (RFC 8955 §6, ADR-0020) or a mesh above 30 nodes: all remain NOT_QUALIFIED.
- The VM is Apple Virtualization (`virtio_net`, XDP `generic`); these are lab numbers under
  SUPPORT §1, not field numbers.
