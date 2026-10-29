# RC-1 candidate `ee16318`: admission record (2026-10-29)

**Status: ADMITTED as RC-1** on 2026-10-29 19:30:31 +02:00 by the owner's signed tag `v0.1.0-rc.1`
(tag object `6565c820f6afdbbaa864882afe3cc8b78fb17d10`, target `ee16318`); rules 1–6 of ADR-0031
hold on the digest below. Supported until RC-2 or 2027-01-27, whichever is earlier (see *Admission*).

The candidate is the aarch64 archive CI built on main at `ee16318a3dc92d5238afc99f45b23a035bcec158`
(the merge of PR #76), artifact `candidate-ee16318…-aarch64` of CI run 40877306864:

| | |
|---|---|
| archive sha256 | `03bae666742ded82c8b60c940d37ad525996283f7f4bb589ca0383dbf675ab99` (`candidate-aarch64.json`) |
| provenance | one SLSA v1 attestation on that digest, verified with `gh attestation verify` against repository `s0fractal/interdict-mesh`, signer workflow `.github/workflows/ci.yml` at `refs/heads/main`, source digest `ee16318…`, self-hosted runners denied (`attestation-verify.json`; `runnerEnvironment` github-hosted). The SPDX 2.3 SBOM attestation on the same digest verified the same way. |
| `usr/local/bin/interdictd` | `42c3047b8929c955af83d67635cd7157934cff6ab7fd57220b4ce4c6ec53d5bf`, `--version`: `orchestrator 0.1.0 (build ee16318a3dc9)` |
| `usr/local/bin/interdict-mon` | `99d74a8cf8240cf37c5bf2fe15be66e69ae357e6fdbab9c24afd681a262a6592` |
| installed with | `scripts/candidate.py verify` (`INTEGRITY_ONLY`), then its `install` subcommand with the prefix `/var/lib/sokol-campaigns/rc1-ee16318-pkg` (`INSTALLED_FILES`) |
| witness gate | on a clean checkout of `ee16318`: `witness-pin.py check --every-pin` ok (74 rows, 234 witnesses, 5 provisional); `contract-store.py check --every-pin` ok (262 records, 82 lineages) |

Every number below was produced by the binaries of this archive, not by a local build (issue #61:
the same commit built on the VM gives other bytes). The x86_64 archive of the same run is attested
too but was not measured here: ARM and x86 are qualified separately (ROADMAP), so this record concerns
the aarch64 digest only.

Lab: Lima `sokol-lab`, aarch64, 10 vCPU, Ubuntu 24.04, kernel 6.8.0-147, XDP `generic`, nodes in
network namespaces on one bridge, no netem. Order: campaign first (quiet host), then the benches,
then the rehearsal; none ran concurrently.

## Rule 5: campaign `--profile rc1`, LIMITED_PASS

`campaign/report.json`: profile `sokol.vm-campaign.v2`, status **LIMITED_PASS**, unit
`sokol-campaign-1793279357021931758` (`Result=success`, exit 0, `campaign/unit-journal.txt`),
`binary_sha256` and `monitor_sha256` = the two above, `source_commit` `ee16318`, seed 1729; the apt
timers and unattended-upgrades masked before the start (issue #65's trigger). 15:09–18:13 local.

**Chaos, 60 min** (`campaign/chaos/`): 59 restarts and 39 cuts on schedule, 15 938 events.
PASS all 3 nodes agree on the active blocks (403); PASS every audit chain verifies, no node panicked;
PASS no block pending at the end (all three final readings 0). Of the 183 samples, 127 read
`blocks_pending` and every one of them is 0; 56 have no reading (the node was restarting or its
metrics endpoint not yet up), which is unknown, not zero. Longest tick 0.017 s over the 130 samples
that read it (53 without a reading); RSS read in all 183, max 32.3 / 32.2 / 48.6 MB. The console's informational line "RSS growth … max 406.5 %" is not a
criterion and not growth: node 1's first sample after 5 min (t = 300 s) fell inside a restart
(6 076 kB, metrics empty), its last sample is 30 772 kB.

**Plateau, 120 min** (`campaign/plateau/`): no restarts, 23 cuts, 31 746 events. Saturation before
the load on every node: 65 536 event ids remembered, 4 096 evicted (94–95 s). PASS agreement (256),
audit chains, no panic; `blocks_pending` read in all 363 samples, 0 in every one. Judged from t = 1 320 s, first vs last third:

| Node | RSS peak (kB) | State file peak (bytes) | fds |
|---|---|---|---|
| 1 | 54 596 → 57 336 | 3 702 220 → 3 697 460 | 27 → 27 |
| 2 | 53 308 → 57 452 | 3 702 184 → 3 696 239 | 27 → 27 |
| 3 | 53 168 → 56 988 | 3 699 061 → 3 697 949 | 27 → 27 |

PASS plateau: level within 10 % (RSS +5.0 / +7.8 / +7.2 %), every sample read, every sample within
the ceilings (RSS ≤ own pre-load RSS + 536 345 kB; state ≤ 239 039 621 B). Longest tick 0.10 s.
On every node the last RSS sample is also its maximum: RSS was still creeping when the phase ended;
120 min do not show where it levels (see *What this does not establish*).

## Rule 4: benches on the candidate

Commands (root, from the clean checkout of `ee16318`; the exact sequence is `docs/measurements/2026-10-29-rc1-candidate-ee16318/bench/run.sh`,
timestamps in `docs/measurements/2026-10-29-rc1-candidate-ee16318/bench/progress.log`):

```
bench/mesh.sh reaction <interdictd> <interdict-mon> 3 20     # bench/reaction-3-20.txt
bench/mesh.sh unblock  <interdictd> <interdict-mon> 3 20     # bench/unblock-3-20.txt   (FlowSpec: gobgpd)
bench/mesh.sh recover  <interdictd> <interdict-mon> 3        # bench/recover-3.txt
bench/mesh.sh restart  <interdictd> <interdict-mon> 3 10     # bench/restart-3-10.txt
bench/mesh.sh restart  <interdictd> <interdict-mon> 10 10    # bench/restart-10-10.txt
RESTART_CONTROL=1 bench/mesh.sh restart <interdictd> <interdict-mon> 3 3   # bench/restart-control.txt
```

| # | Target (ADR-0031) | Measured on this candidate (worst) | Source | Within |
|---|---|---|---|---|
| S1 | signal → node 1 stops passing ≤ 500 ms | 12 ms (n=20, median 10) | reaction R1 | yes |
| S2 | → every peer stops ≤ 3 s | 12 ms (n=60) | reaction R2 | yes |
| S3 | lift → node passes again ≤ 1 s; peer ≤ 3 s | node 1 ≤ 12 ms, peers ≤ 12 ms over retract / unban / flush (n=20 / 40 each); unban in reaction R3 ≤ 17 ms | unblock, reaction | yes |
| S4 | lease end → XDP and peers ≤ 2 s after the signed end | expiry recorded ≤ 998 ms after the signed end, then node 1 ≤ 10 ms, peers ≤ 15 ms | unblock `expire` | yes |
| S5 | block end → rule gone from the node's RIB ≤ 5 s (≤ 64 changes) | 1 999 ms (retract max; unban 1 982, flush 1 995, expiry 1 048) | unblock `rib` | yes |
| S6 | legitimate loss during blocks ≤ 0.5 % | 0 of 104 295 pings lost | reaction R4 | yes |
| S7 | control socket under flood ≤ 1 s; tick ≤ 500 ms; repair ≤ 120 s | control max 0 ms (22 answers); no tick over 500 ms; all 3 nodes hold 16 384 (the envelope) 8 s after the flood; 56 502 urgent broadcasts dropped, so the repair path was exercised | recover L1–L5 | yes (below the bounds; at the bounds see rule 6) |
| RTO | crash (SIGKILL) with a block on disk: apply ≤ 10 s, mesh ≤ 30 s | control answers 119–148 ms; attacker's last reply 41–73 ms; all peers back 138–1 131 ms, in every one of 20 rounds (3 and 10 nodes; each run exit 0) | restart X1–X3 | yes |
| control | a node that restores nothing must fail X2 | attacker still answered 2 130–3 106 ms after the kill; X2 FAIL in 3 of 3 rounds | restart-control | as intended |

Upstream GoBGP (`upstr`) worst case within 5 ms of the node's own RIB for retract, unban and flush
(2 003 / 1 986 / 2 000 ms) and lower for expiry (991 ms); `no layer kept blocking 20 s after an
end`.

## Rule 3: runbook rehearsal from the package

`scripts/runbook-rehearsal.sh` of `ee16318` (`rehearsal/run.sh`) with A = the candidate's
`interdictd`/`interdict-mon` and B = the attested main candidate of the previous merge, `d638c83`
(archive `3c17c8c58540d9f197450c9530356c5fe6c88811fc3e6a8a455f802e077a854e`, CI run 40771378585,
SLSA provenance verified the same way: `rehearsal/attestation-b-d638c83-verify.json`;
`interdictd` `781f60a5…`, build `d638c8397df8`). Input hashes: `rehearsal/inputs.sha256`.

Result (`rehearsal/rehearsal.txt`): **0 failed, 0 runbook deviations**, 33 PASS lines: install, keys,
first start, a wrong block and its lift, state not restored (`ACCEPT_STATE_LOSS`), upgrade
`ee16318a3dc9 → d638c8397df8` and rollback to `ee16318a3dc9` with the operator ban kept through
both, emergency removal of the filter, support bundle without key bytes. The swap goes from the
candidate to the older build and back, so both directions cross one state file between two
attested builds; `interdict-mon` is byte-identical in the two archives.

## Rules 1, 2 and 6

1. main at `ee16318`: CI run 40877306864 succeeded (kani, test/demo/smoke on x86_64 and aarch64,
   `build-test-smoke` on both, `candidate origin` on both; mutants skip on push); the gate checks
   above. PR #76 was accepted by Codex (review record 3769b8a) before the owner merged it.
2. Above: CI-built archive, provenance and SBOM attestations verified.
6. No open P1 at 2026-10-29 (open issues: #61 reproducibility, #65 campaign worker restart; neither
   labelled P1). Named limits: native NIC and upstream FlowSpec validation NOT_QUALIFIED; S7 with
   the block table at its bounds (ADR-0031, amendment 2026-10-29; an RC-2 admission condition).

## Admission

**ADMITTED.** Rules 1–6 of ADR-0031 hold on archive `03bae666…` (above); the owner's signature is
the act of admission (ADR-0031, *Responsibility*). The owner signed it after this record was merged
(main `28fdee0`, PR #77):

| | |
|---|---|
| tag | `v0.1.0-rc.1`, annotated, SSH-signed with the owner key of `.github/witness-signers` (ED25519 `SHA256:4dJ6IEtOAZpBdQ07gvhKTiwTqsiZnaf1Jh/GuYuTeA4`) |
| tag object | `6565c820f6afdbbaa864882afe3cc8b78fb17d10` |
| target | `ee16318a3dc92d5238afc99f45b23a035bcec158` (the candidate's source commit, not the record's merge) |
| tagger date | 1793295031 = 2026-10-29 19:30:31 +02:00 |
| message | names archive `03bae666…`, main run 40877306864 and this record |
| support (ADR-0031) | until RC-2 or 90 days after the tag, whichever is earlier: at the latest 2027-01-27 |

`candidate-aarch64.json` and `campaign/report.json` keep `NOT_ADMITTED`: they are what the tools
wrote when they ran, and no tool output admits a candidate; the tag above does.

**Verifying the signature with what is in this repository.** `.github/witness-signers` pins the owner
key for the namespace `sokol-witness` (the manifest signatures), while `git tag -s` signs in the
namespace `git`, so `tag -v` against that file as it is says the key "is not permitted" there. The
same owner line with its namespace set to `git` verifies the tag (from a checkout with the tag
fetched; the file stays as the witness gate pins it):

```bash
f=$(mktemp) && grep '^owner ' .github/witness-signers | sed 's/namespaces="sokol-witness"/namespaces="git"/' > "$f" && git -c gpg.ssh.allowedSignersFile="$f" tag -v v0.1.0-rc.1; s=$?; rm -f "$f"; [ $s = 0 ]
```

Expected: `Good "git" signature for owner with ED25519 key SHA256:4dJ6IE…`, exit 0, and `object
ee16318a…` in the printed tag. Checked 2026-10-29; the agent line in its place fails (exit 1).

**CI on the tag.** Run 40922177860 (event push, ref `v0.1.0-rc.1`, head `ee16318`): **success**,
finished 2026-10-29 17:44:27 UTC: kani, test, demo and smoke on x86_64 and aarch64,
`build-test-smoke` on both; mutants and `candidate origin` skipped, as they are on every tag (the
attested candidate comes only from main's run). A CI run on the tag rebuilds and proves the commit again; its bytes
are not this candidate (issue #61): the RC is the digest above.

## What this does and does not establish

- Three-hour VM campaign only (amendment 2026-10-28): effects with a period longer than three hours,
  claim lifetimes above 720 s and host daily timers are not seen; RC-2 runs `--profile long`.
- The plateau RSS rose 5–8 % from the first to the last judged third and peaked in the last sample
  on every node: within the criterion, not shown to be level beyond 120 min.
- S7 is met here below the bounds; at the bounds it is not (named limit above).
- Nothing here qualifies a physical NIC in `native` mode, an upstream router's FlowSpec validation
  (RFC 8955 §6, ADR-0020) or a mesh above 30 nodes: all remain NOT_QUALIFIED.
- The VM is Apple Virtualization (`virtio_net`, XDP `generic`); these are lab numbers under
  SUPPORT §1, not field numbers.
- Files kept outside the repository (with `SHA256SUMS`) under `~/Projects/.worktrees/rc1-ee16318`
  on the lab host's Mac: the archives, the per-node logs and `events.csv` of both phases.
