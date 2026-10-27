#!/usr/bin/env python3
"""Phase 0 of the Warrant 3 study: how much of this repository's history is governance.

    governance-baseline.py [--source REV] [--since ISO] [--out FILE]
        Count from Git objects only (nothing in the working tree is read) and print, or write
        to FILE, one JSON document. The same source commit gives the same bytes.

The predicates, exactly (docs/measurements/2026-10-27-warrant3/README.md quotes them):

- Window: the commits reachable from SOURCE whose committer date is at or after SINCE
  (`git rev-list --since`).
- Governance paths G: docs/contracts/**, docs/adr/**, scripts/contract*.py,
  scripts/witness-pin.py, docs/witness-manifest.json[.sig], docs/witness-provisional.json[.sig],
  .github/workflows/witness-gate.yml.
- (a) A non-merge commit of the window touches G when its diff against its parent names a path
  of G. It is an INVARIANT change when, for at least one contract file it changes, the
  projection {statement, evidence_text, witnesses, status, retirement} differs from the
  parent's or the file is added or removed. Otherwise it is MACHINERY when it touches a G path
  outside docs/adr/, else ADR_ONLY. A tier-only change (promote) is MACHINERY: who stands
  behind the row changed, not the row. MACHINERY is split by its non-ADR paths, first match:
  `code` (scripts/ or .github/), `pins_only` (docs/witness-* only), `proposals` (contract and pin
  files, at least one under docs/contracts/proposals/: an unsigned intent filed), `contract_files`
  (contract and pin files: decision, tier or annotation only), `other`.
- (b) Owner acts per ISO week (UTC committer date): `resign` = non-merge commits changing
  docs/witness-manifest.json.sig (each is a signature by the owner key); `agent_sign` = the same
  for docs/witness-provisional.json.sig (the agent key, ADR-0028); `promote` = contracts gaining a
  decision whose reason is "promoted by the owner"; `merge` = merge commits on SOURCE's
  first-parent chain (every merge into main); `owner_path_merge` = those merges whose diff
  against their first parent names a path the owner's signature covers (OWNER_PATHS).
- (c) Lines: newline count of each file of GOVERNANCE_CODE, GOVERNANCE_TESTS and
  GOVERNANCE_WORKFLOWS at SOURCE and at the last commit before SINCE (the first commit of the
  history when it starts inside the window).
"""
import argparse
import datetime
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G = ("docs/contracts/*", "docs/adr/*", "scripts/contract*.py", "scripts/witness-pin.py",
     "docs/witness-manifest.json", "docs/witness-manifest.json.sig", "docs/witness-provisional.json",
     "docs/witness-provisional.json.sig", ".github/workflows/witness-gate.yml")
OWNER_PATHS = (".github/witness-signers", "scripts/witness-pin.py", ".github/workflows/witness-gate.yml",
               "docs/witness-manifest.json", "docs/witness-manifest.json.sig")
PROJECTION = ("statement", "evidence_text", "witnesses", "status", "retirement")
GOVERNANCE_CODE = ("scripts/contract.py", "scripts/witness-pin.py", "scripts/contract-shadow.py",
                   "scripts/contract-task.py", "scripts/check-review.py")
GOVERNANCE_TESTS = ("scripts/test_contract_tool.py", "scripts/test_witness_pin.py", "scripts/test_contract_shadow.py",
                    "scripts/test_contract_task.py", "scripts/test_trust_root.py", "scripts/test_gate_provenance.py",
                    "scripts/test_check_review.py")
GOVERNANCE_WORKFLOWS = (".github/workflows/witness-gate.yml", ".github/workflows/agent-review.yml")
PROMOTED = "promoted by the owner"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def lines(*args):
    return git(*args).decode().split("\n")[:-1]


def in_g(path):
    return any(fnmatch.fnmatchcase(path, p) for p in G)


def changed(commit, parent):
    if parent is None:
        return lines("ls-tree", "-r", "--name-only", commit)
    return lines("diff-tree", "-r", "--no-commit-id", "--name-only", parent, commit)


def blob_json(commit, path):
    if commit is None:
        return None
    try:
        return json.loads(git("show", f"{commit}:{path}"))
    except subprocess.CalledProcessError:
        return None


def projection(doc):
    return None if doc is None else {k: doc.get(k) for k in PROJECTION}


def week(ts):
    y, w, _ = datetime.datetime.fromtimestamp(ts, datetime.UTC).isocalendar()
    return f"{y}-W{w:02d}"


def classify(commit, parent):
    paths = [p for p in changed(commit, parent) if in_g(p)]
    if not paths:
        return None, [], 0
    contracts = [p for p in paths if p.startswith("docs/contracts/") and p.endswith(".shadow.json")]
    moved = [p for p in contracts if projection(blob_json(parent, p)) != projection(blob_json(commit, p))]
    promotes = 0
    for p in contracts:
        before, after = blob_json(parent, p) or {}, blob_json(commit, p) or {}
        n0 = sum(d.get("because") == PROMOTED for d in before.get("decisions", []))
        n1 = sum(d.get("because") == PROMOTED for d in after.get("decisions", []))
        promotes += max(0, n1 - n0)
    if moved:
        kind = "INVARIANT"
    elif any(not p.startswith("docs/adr/") for p in paths):
        kind = "MACHINERY"
    else:
        kind = "ADR_ONLY"
    return kind, paths, promotes


def count_lines(commit, files):
    out = {}
    for f in files:
        try:
            out[f] = git("show", f"{commit}:{f}").count(b"\n")
        except subprocess.CalledProcessError:
            out[f] = None
    return out


def measure(source, since):
    source = lines("rev-parse", "--verify", f"{source}^{{commit}}")[0]
    window = lines("rev-list", f"--since={since}", "--format=%H %P|%ct", source)
    commits = []
    for row in window:
        if row.startswith("commit "):
            continue
        ids, ts = row.split("|")
        c, *parents = ids.split()
        commits.append((c, parents, int(ts)))
    first_parent = set(lines("rev-list", "--first-parent", f"--since={since}", source))
    a = {"INVARIANT": [], "MACHINERY": [], "ADR_ONLY": []}
    touched, weeks = {}, {}
    non_merge = 0

    def bump(ts, key, n=1):
        w = weeks.setdefault(week(ts), {"resign": 0, "agent_sign": 0, "promote": 0, "merge": 0, "owner_path_merge": 0})
        w[key] += n

    for c, parents, ts in commits:
        if len(parents) > 1:
            if c in first_parent:
                bump(ts, "merge")
                if any(p in OWNER_PATHS for p in changed(c, parents[0])):
                    bump(ts, "owner_path_merge")
            continue
        non_merge += 1
        parent = parents[0] if parents else None
        kind, paths, promotes = classify(c, parent)
        if kind is None:
            continue
        a[kind].append(c)
        touched[c] = paths
        if "docs/witness-manifest.json.sig" in paths:
            bump(ts, "resign")
        if "docs/witness-provisional.json.sig" in paths:
            bump(ts, "agent_sign")
        if promotes:
            bump(ts, "promote", promotes)
    code = (".github/", "scripts/")
    mixed = [c for c in a["INVARIANT"] if any(p.startswith(code) for p in touched[c])]
    sub = {"code": 0, "pins_only": 0, "proposals": 0, "contract_files": 0, "other": 0}
    for c in a["MACHINERY"]:
        ps = [p for p in touched[c] if not p.startswith("docs/adr/")]
        if any(p.startswith(code) for p in ps):
            sub["code"] += 1
        elif all(p.startswith("docs/witness-") for p in ps):
            sub["pins_only"] += 1
        elif all(p.startswith(("docs/witness-", "docs/contracts/")) for p in ps) and \
                any(p.startswith("docs/contracts/proposals/") for p in ps):
            sub["proposals"] += 1
        elif all(p.startswith(("docs/witness-", "docs/contracts/")) for p in ps):
            sub["contract_files"] += 1
        else:
            sub["other"] += 1
    # The lines at the window's start: the last commit before it, or the first commit of the
    # history when the history starts inside the window (this repository's starts on 2026-10-10).
    before = lines("rev-list", "-n1", f"--before={since}", source)
    base = before[0] if before else lines("rev-list", "--max-parents=0", source)[0]
    totals = {k: sum(w[k] for w in weeks.values()) for k in ("resign", "agent_sign", "promote", "merge", "owner_path_merge")}
    loc = {}
    for name, files in (("code", GOVERNANCE_CODE), ("tests", GOVERNANCE_TESTS), ("workflows", GOVERNANCE_WORKFLOWS)):
        now, then = count_lines(source, files), count_lines(base, files)
        loc[name] = {"files": now, "total": sum(v or 0 for v in now.values()),
                     "total_at_window_start": sum(v or 0 for v in then.values())}
    return {
        "source": source, "since": since, "window_start_commit": base,
        "predicates": __doc__.split("The predicates, exactly")[1].strip(),
        "commits": {"all": len(commits), "non_merge": non_merge, "merge": len(commits) - non_merge},
        "a_governance_commits": {"touching_G": sum(len(v) for v in a.values()),
                                 **{k: len(v) for k, v in a.items()},
                                 "INVARIANT_also_touching_machinery_code": len(mixed), "MACHINERY_by_paths": sub,
                                 "ids": {k: sorted(v) for k, v in a.items()}},
        "b_owner_acts": {"totals": totals, "per_week": dict(sorted(weeks.items()))},
        "c_lines": loc,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="HEAD")
    ap.add_argument("--since", default="2026-10-01T00:00:00Z")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    text = json.dumps(measure(a.source, a.since), indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
