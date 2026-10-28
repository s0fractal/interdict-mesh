# ADR-0034. The product is interdict-mesh

Status: PROPOSED; accepted by the owner's re-signature of the manifest and the merge. Date:
2026-10-28. Owner decision 2026-10-28: the product is renamed right before RC-1, and the RC-1
candidate is built after the rename. Interdiction is stopping hostile movement; it is also a
prohibitory order.

## Decision

| What | Before | After |
|---|---|---|
| Repository and product | `sokol-core`, Sokol-Core | `interdict-mesh` (the GitHub rename is the owner's, after the merge) |
| Node daemon (installed name of the `orchestrator` target) | `sokol-orchestrator` | `interdictd` |
| Control and monitor CLIs | `sokol-operator`, `sokol-monitor` (target `monitor`) | `interdict-ctl`, `interdict-mon` (target `monitor`) |
| Adapters | `sokol-suricata`, `sokol-crowdsec`, `sokol-fastnetmon-notify` | `interdict-suricata`, `interdict-crowdsec`, `interdict-fastnetmon-notify` |
| Support bundle, anchor stamper | `sokol-support-bundle`, `sokol-anchor-ots` | `interdict-support-bundle`, `interdict-anchor-ots` |
| Prometheus metrics, alerts, rule groups | `sokol_*`, `Sokol*`, `sokol-health` … | `interdict_*`, `Interdict*`, `interdict-health` … |
| Rule, test and dashboard files | `sokol-alerts{,.test}.yml`, `sokol-dashboard.json` in `deploy/` | `interdict-alerts{,.test}.yml`, `interdict-dashboard.json`; scrape job `interdict` |
| systemd units | `sokol-orchestrator.service`, `sokol-anchor.{service,timer}` | `interdictd.service`, `interdict-anchor.{service,timer}` |
| Service user and groups | `sokol`, `sokol-ipc`, `sokol-ops`, `sokol-anchor` | `interdict`, `interdict-ipc`, `interdict-ops`, `interdict-anchor` |
| Paths | `/var/lib/sokol`, `/run/sokol`, `/run/sokol.sock`, `/run/sokol-control.sock`, `/run/sokol_telemetry.sock`, `/etc/sokol`, `/etc/default/sokol`, `/usr/local/share/sokol`, `/var/lib/sokol-anchors` | the same with `interdict` |
| Operator environment | `SOKOL_ARGS`, `SOKOL_IPC_SOCKET`, `SOKOL_OPERATOR_TOKEN`, `SOKOL_OPERATOR_BIND`, `SOKOL_CROWDSEC_KEY`, `SOKOL_JAIL_ADDR`, `SOKOL_TRAP_PORTS`, `SOKOL_NODE_UIDS`, `SOKOL_TELEMETRY_GROUP` | `INTERDICT_*` |
| WireGuard example, heartbeat name | `sokol0`, `sokol-wg0`, `Sokol-Node-N` | `interdict0`, `interdict-wg0`, `interdict-node-N` |
| Operator console session cookie | sokol_operator | interdict_operator |

**The rule.** What an operator or a deployment sees is renamed: binaries, units, users, paths,
environment, metrics, alerts, dashboards, CLI help, log lines, and the prose of README, ARCHITECTURE,
RUNBOOK, INTEGRATIONS, SUPPORT and SECURITY. What names data, history, a signature or the build is
kept, because renaming it would invalidate what already exists or change an owner-pinned byte for
nothing a user sees. Before RC-1 there are no deployments: no compatibility alias is added for users.
One alias is added for one merge: the base gate runs the pinned Python witnesses with the argument
vectors of main's `ci.yml`, which name `target/release/sokol-suricata` and `sokol-crowdsec`, and their
`__main__` blocks are inside the pinned closures. `orchestrator/src/bin/sokol-suricata/main.rs` and
`orchestrator/src/bin/sokol-crowdsec/main.rs` only exec the renamed adapter from the same directory
(Cargo names a target per `src/bin` entry; no build pin changes; a directory, not the old file path,
so Git still sees the adapters' files as moved). The first pull request after the merge deletes them.

**Earlier ADRs** keep their prose (they record what was decided, under the name of the time); the
identifiers in their code spans (metrics, file paths, binaries, units, environment) now name the live
artefacts, so that `scripts/check-claims.sh` keeps checking them. A measurement README keeps the names
it measured; `check-claims.sh` reads a `sokol_` metric there as its `interdict_` successor, and refuses
a `sokol_` metric anywhere else.

**Contracts.** Four contract statements named a metric or an alert: XDP-C1, IPC-L1, MESH-C1, MESH-A2.
Each has a new version (author `claude`, decision `because` this ADR, the previous statement's hash),
which renames only the metric and alert names; the evidence and the witnesses are unchanged.

## Kept, and why

1. **Crate directories and package names** (`orchestrator/`, `common/`, `ebpf/`, `fuzz/` with package
   `sokol-fuzz`) and the Cargo targets without a product name (`orchestrator`, `monitor`,
   `trident_trap`). `-p orchestrator` is in the base gate (`witness-gate.yml`, trust root), and a
   `[[bin]]` section would be a build-pinned change; the install step names `orchestrator` `interdictd`
   and `monitor` `interdict-mon`, as it named them `sokol-*` before. `trident_trap` names a component,
   not the product. Only the four targets that carried the product name are renamed (their files move).
2. **Test names and test fixtures.** Every test function name; literals inside test bodies that no
   user sees (`argv[0]` in the adapters' CLI tests, temp-directory prefixes `sokol-*`, the Suricata rule
   text `SOKOL TEST telnet probe`, the smoke's interface and namespace names, the claim reason in
   `a_peer_reason_cannot_frame_extra_operator_telemetry_lines`). They are pinned witness bodies, and
   renaming them changes nothing a test checks.
3. **Record schemas and format identifiers**: `sokol-contract@1`, `sokol.contract-shadow.v1`,
   `sokol.candidate.v1`, `sokol.product-inventory.v1`, `sokol.build-inputs.v1`, `sokol.vm-campaign.v2`,
   `sokol.node-status.v1`, `sokol.support.v1`, `sokol.native-fuzz.v1`, `sokol.proof-challenges.v1`,
   `sokol.local-industrial-evidence.v1`, `sokol.counterexample-{execution,observation,pack,policy,view}.v1`,
   `sokol.agent.{contract-task,outbox-task,proof-run}.v1`, `sokol.dev.{inventory,map,next}.v1`, the
   worker frame `SOKOL_WORKER_REPORT_V1`, the anchored statement `sokol-audit-head v1` and the audit
   log's record magic. A format id names a shape; signed records, evidence files and timestamped
   statements carry these, and a new name would be a new version with no change in meaning.
4. **Signature namespaces and contexts**: the SSH namespace `sokol-witness` (owner and agent manifests,
   `.github/witness-signers`) and the ML-DSA context `sokol-mesh-envelope` (mesh envelopes). Every
   existing manifest signature verifies only under the first; the second is the mesh's wire identity.
5. **The Warrant store's history**: the migrated contracts' author `sokol-core/files`, and the
   `pr-head@1` roots naming `s0fractal/sokol-core`. Records are not edited; see the steps below for
   lineages opened after the GitHub rename.
6. **Build-pinned and trust-root files**: `orchestrator/build.rs` keeps `SOKOL_BUILD_ID` (the release
   pipeline's input) and `SOKOL_VERSION`, and its doc comment still names the build-info metric by its old
   name until build.rs changes for another reason; `.github/workflows/witness-gate.yml` and
   `.github/witness-signers` are unchanged.
7. **CI and test harness variables**, which no operator sets: `SOKOL_WARRANT_BIN` (set by the base gate),
   `SOKOL_GOBGP_TEST_BIN`, `SOKOL_TEST_LIST`, `SOKOL_SKIP_TEST_NAMES`, `SOKOL_FUZZ_CASES`,
   `SOKOL_FUZZ_DEBUG`, `SOKOL_TEST_SECRET`, `SOKOL_REPLAY_TEST_PATH`, `SOKOL_FNM_NOTIFY_TEST_CHILD`,
   `SOKOL_EXCHANGE_REGISTRY`; CI's `/tmp/sokol-*` files.
8. **Internal code identifiers**: the module `orchestrator/src/sokol.rs` and `SokolEngine`, the dev tool
   `scripts/sokol-dev.py`, the transient unit names `sokol-campaign-*` and `sokol-counterexample-*`, the
   bench lock. They may be renamed when touched for another reason.
9. **History documents**: `docs/measurements/`, `docs/status/`, `docs/industrial/`, `docs/pilots/`,
   `docs/experiments/`, `docs/RETIRED.md`, `docs/PAPER-SIGNED-WITNESSES.md`.
10. **Legal text**: `CLA.md`, `COPYRIGHT.md` and `AUTHORS.md` name Sokol-Core and Project Sokol. Changing
    the name in an agreement contributors accepted is the copyright holders' act, not this change's.
11. **Repository URLs and the SonarCloud key** (`s0fractal_sokol-core`) until the GitHub rename (below).
12. **External names**: the archived Stargate checker's `sokol_*.py` modules and the bridge repository
    `s0fractal/sokol-core-upstream` (its pinned commit), the private repository `s0fractal/sokol`, the
    lab VM `sokol-lab`.

## Owner-pinned bytes

`scripts/witness-pin.py check` names what the owner's signature must cover, in four groups:

- **Four moved files** (`orchestrator/src/bin/sokol-{operator,suricata,crowdsec,fastnetmon-notify}.rs`
  → `interdict-{ctl,suricata,crowdsec,fastnetmon-notify}.rs`): 43 witness bodies and 49 closures are
  pinned by path and change with it; with the files moved back their bytes are the pinned ones.
- **Trust root**: `python_arguments` of `scripts/test_crowdsec_stream.py` and
  `scripts/test_suricata_recovery.py` (`target/release/interdict-{crowdsec,suricata}`).
- **Bytes**: 3 witness bodies and 12 closures, each a consequence of a renamed name: the metric names
  in `a_failed_stats_read_keeps_the_last_counters_and_is_counted`, `peer_claims_are_rendered_by_issuer_and_result`
  and `Monitoring.test_a_renamed_metric_fails`; the rule and dashboard file names in the Monitoring
  fixture; the binary paths in the Suricata and CrowdSec Python fixtures; `INTERDICT_IPC_SOCKET` in the
  FastNetMon hook's test helper.
- **Contracts**: the four new leaf versions and their rendered rows.

No build pin, no provisional row and no witness-gate file changes.

## After the GitHub rename

The owner renames `s0fractal/sokol-core` to `s0fractal/interdict-mesh` after this merge, with no other
pull request open. GitHub redirects the old URLs, so nothing breaks at once; then, in order:

1. One pull request sets `.warrant/v3.json` `repository` to `s0fractal/interdict-mesh` (and the
   repository URLs in README, SECURITY, the paper and the candidate SBOM namespace). The gate and the
   review tools match a `pr-head@1` root against the base's `repository`, so this pull request's own
   lineage still names `s0fractal/sokol-core`; every later one names the new repository. Existing
   lineages are history and are not refiled; a pull request left open across the switch gets a new
   lineage under the new name (`warrant.review open`), its old one stays as it is.
2. The owner's waker entry (`~/.warrant/codex-waker/repositories.json`) takes the new `repository`, and
   its mirror's remote the new URL; its local paths may stay.
3. SonarCloud: the project key `s0fractal_sokol-core` becomes `s0fractal_interdict-mesh`
   (Administration → Update key), and `.sonarcloud.properties` names it.
4. Badges: the tree has none at this commit; new ones use the new name.
5. Every local checkout: `git remote set-url origin git@github.com:s0fractal/interdict-mesh.git`
   (worktrees share it).

## What is lost

1. **A lab install of the old names** (the Lima `sokol-lab` VM) is not upgraded in place: the unit,
   user, groups, paths and environment changed. Moving `/var/lib/sokol` to `/var/lib/interdict` (and
   its owner to `interdict`) keeps the node key and the audit log; nothing does it automatically.
2. **Metric history** in a Prometheus that scraped `sokol_*` does not continue under `interdict_*`.
3. **One name in the tree.** Formats, namespaces, test fixtures, the store's history and legal text
   keep `sokol`; the list above is where it remains on purpose.

## Checks

`scripts/test_check_claims.py` `FormerPrefix`: a live document citing a `sokol_` metric fails; a
measurement README's `sokol_` metric is checked as its `interdict_` successor and fails when that is
not exported. Both fail on their assertions against the check as the mechanical rename alone left it
(which no longer read `sokol_` names at all). `scripts/check-monitoring.sh` checks the renamed rules
and dashboard against the renamed exporter; promtool runs the renamed rule tests in CI.
