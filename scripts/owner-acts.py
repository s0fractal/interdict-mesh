#!/usr/bin/env python3
"""Phase 0 of the Warrant 3 study: the owner's acts per merged pull request and per week.

    owner-acts.py fetch [--out FILE]
        Snapshot what only GitHub knows (pull requests with their timelines and reviews, ruleset
        history, re-run and dispatched workflow runs, secrets, variables, collaborators, deploy keys)
        into FILE. Counting reads the snapshot, so the count is reproducible after GitHub changes.
    owner-acts.py count [--source REV] [--github FILE] [--out FILE]
        Count from Git objects at SOURCE, the owner's and agent's SSH signatures in them, and the
        snapshot. Prints, or writes to FILE, one JSON document.
    owner-acts.py table [--counted FILE]
        Render the per pull request table of a count as Markdown (OWNER-ACTS.md is its output).

Every act has a class, by what can attest it (docs/measurements/2026-10-27-warrant3/README.md):

- KEY: a signature that verifies under a key of .github/witness-signers at SOURCE. `resign` = a
  commit that changes docs/witness-manifest.json.sig to a signature the `owner` principal made
  over that commit's manifest; `agent_sign` = the same for the provisional manifest and the
  `agent` principal (an agent's act, listed for contrast). The key proves the key was used, not
  whose hand held it: custody is policy.
- REPO: Git alone, unsigned. `promote` = a contract gaining the decision "promoted by the owner";
  `key_binding` = a commit that adds a key line to .github/witness-signers; `direct_push` = a
  non-merge commit on SOURCE's first-parent chain (it reached main without a pull request).
- FORGE: GitHub alone, by the owner's login, and the owner's by this repository's policy (agents
  do not merge, create repositories or edit rulesets here): `merge` = a pull request's merged_by;
  `ruleset` = a version in a ruleset's history by the owner's user id; `repository` = the
  repository's creation.
- AMBIGUOUS: GitHub alone, by the owner's login, and no policy keeps agents from it: `rerun` = a
  workflow run with run_attempt > 1 or a workflow_dispatch run, by its triggering actor;
  `close_unmerged` = a pull request closed without merge by the actor of its last `closed` event;
  `branch_update` = a merge commit committed by GitHub that is not on main's first-parent chain
  (the pull request's "Update branch", in the UI or through the API). Counted apart, never in the
  owner's total.
In this repository every pull request, comment and merge carries the owner's login, because agents
use the owner's token: GitHub's actor field does not tell the owner from an agent.

An act belongs to the pull request whose merge brought its commit to main (the commits of
M^2 not reachable from M^1, M a first-parent merge), or to no pull request. Weeks are ISO weeks
of the act's own time in UTC (committer time for Git acts, the event time for FORGE acts).
Commits are also split by authorship as Git records it (unsigned): `agent` when the author is an
agent or a Co-Authored-By trailer names one, `unattributed` otherwise (the owner's Git identity
with no trailer: the owner, or an agent that left no trailer).
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "s0fractal/sokol-core"
OWNER_LOGIN = "s0fractal"
SIGNERS, NAMESPACE = ".github/witness-signers", "sokol-witness"
SIGNED = (("resign", "owner", "docs/witness-manifest.json"), ("agent_sign", "agent", "docs/witness-provisional.json"))
PROMOTED = "promoted by the owner"
AGENT = re.compile(r"\b(Claude|Codex|Fable|Opus|Sonnet|Haiku|GPT|AI assistant)\b")
MERGE_PR = re.compile(r"Merge pull request #([0-9]+) ")
KEY_LINE = re.compile(r'^\+[a-z][a-z0-9_-]* namespaces="', re.M)
OWNER_ACTS = ("resign", "promote", "key_binding", "direct_push", "merge", "ruleset", "repository")
AMBIGUOUS = ("rerun", "close_unmerged", "branch_update")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def text(*args):
    return git(*args).decode()


def gh(path, paginate=True):
    cmd = ["gh", "api", path] + (["--paginate"] if paginate else [])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    # --paginate concatenates JSON arrays; read them one after another.
    dec, at, items = json.JSONDecoder(), 0, []
    while at < len(out):
        while at < len(out) and out[at].isspace():
            at += 1
        if at >= len(out):
            break
        value, at = dec.raw_decode(out, at)
        items.append(value)
    if len(items) == 1:
        return items[0]
    return [x for v in items for x in (v if isinstance(v, list) else [v])]


def gh_lines(path, jq):
    """Every item `jq` selects from every page of `path` (an endpoint whose pages are objects)."""
    out = subprocess.run(["gh", "api", path, "--paginate", "--jq", jq], capture_output=True, text=True, check=True).stdout
    return [json.loads(x) for x in out.splitlines() if x]


# ---------------------------------------------------------------- fetch

def fetch():
    r = f"repos/{REPOSITORY}"
    repo = gh(r, paginate=False)
    prs = []
    for p in gh(f"{r}/pulls?state=all&per_page=100"):
        n = p["number"]
        events = [[e.get("event"), (e.get("actor") or e.get("user") or {}).get("login"),
                   e.get("created_at") or e.get("submitted_at"), (e.get("performed_via_github_app") or {}).get("slug")]
                  for e in gh(f"{r}/issues/{n}/timeline?per_page=100") if e.get("event") != "committed"]
        detail = gh(f"{r}/pulls/{n}", paginate=False)
        prs.append({"number": n, "title": p["title"], "author": p["user"]["login"], "state": p["state"],
                    "draft": p.get("draft"), "created_at": p["created_at"], "closed_at": p["closed_at"],
                    "merged_at": p["merged_at"], "merged_by": (detail.get("merged_by") or {}).get("login"),
                    "merge_commit": p["merge_commit_sha"] if p["merged_at"] else None, "head_ref": p["head"]["ref"],
                    "events": sorted(events, key=lambda e: (e[2] or "", e[0] or ""))})
    rulesets = []
    for s in gh(f"{r}/rulesets"):
        hist = gh(f"{r}/rulesets/{s['id']}/history")
        rulesets.append({"id": s["id"], "name": s["name"],
                         "history": sorted([h["version_id"], (h.get("actor") or {}).get("id"), h["updated_at"]] for h in hist)})
    runs = [[x["created_at"], x["event"], x["run_attempt"], (x.get("triggering_actor") or {}).get("login"), x["name"], x["head_branch"]]
            for x in gh_lines(f"{r}/actions/runs?per_page=100", ".workflow_runs[]")
            if x["run_attempt"] > 1 or x["event"] == "workflow_dispatch"]
    owner_id = gh(f"users/{OWNER_LOGIN}", paginate=False)["id"]
    return {"repository": REPOSITORY, "created_at": repo["created_at"], "owner": {"login": OWNER_LOGIN, "id": owner_id},
            "fetched_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pull_requests": sorted(prs, key=lambda p: p["number"]), "rulesets": rulesets, "manual_runs": sorted(runs),
            "secrets": sorted([s["name"], s["created_at"], s["updated_at"]] for s in gh(f"{r}/actions/secrets", paginate=False)["secrets"]),
            "variables": sorted([s["name"], s["created_at"], s["updated_at"]] for s in gh(f"{r}/actions/variables", paginate=False)["variables"]),
            "collaborators": sorted([c["login"], c.get("role_name")] for c in gh(f"{r}/collaborators")),
            "deploy_keys": sorted([k["title"], k["created_at"], k["read_only"]] for k in gh(f"{r}/keys"))}


# ---------------------------------------------------------------- count

def week(ts):
    y, w, _ = datetime.datetime.fromtimestamp(ts, datetime.UTC).isocalendar()
    return f"{y}-W{w:02d}"


def iso(s):
    return int(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def show(commit, path):
    try:
        return git("show", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        return None


def verifies(signers, principal, data, sig):
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "signers").write_bytes(signers)
        Path(tmp, "sig").write_bytes(sig)
        return subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(Path(tmp, "signers")), "-I", principal, "-n",
                               NAMESPACE, "-s", str(Path(tmp, "sig"))], input=data, capture_output=True, timeout=10,
                              check=False).returncode == 0


def commit_acts(c, parent, signers):
    """The owner's (and agent's) acts recorded in one non-merge commit."""
    paths = text("diff-tree", "-r", "--no-commit-id", "--name-only", *([parent] if parent else ["--root"]), c).split()
    acts = []
    for name, principal, manifest in SIGNED:
        if manifest + ".sig" in paths:
            data, sig = show(c, manifest), show(c, manifest + ".sig")
            ok = data is not None and sig is not None and verifies(signers, principal, data, sig)
            acts.append(name if ok else name + "_unverified")
    for p in paths:
        if p.startswith("docs/contracts/") and p.endswith(".shadow.json"):
            before = json.loads(show(parent, p) or b"{}") if parent else {}
            after = json.loads(show(c, p) or b"{}")
            n0 = sum(d.get("because") == PROMOTED for d in before.get("decisions", []))
            n1 = sum(d.get("because") == PROMOTED for d in after.get("decisions", []))
            acts += ["promote"] * max(0, n1 - n0)
    if SIGNERS in paths:
        diff = text("diff", *([parent] if parent else [git("hash-object", "-t", "tree", "/dev/null").decode().strip()]), c,
                    "--", SIGNERS)
        acts += ["key_binding"] * len(KEY_LINE.findall(diff))
    return acts


def attribution(c):
    author, body = text("log", "-1", "--format=%an%x00%B", c).split("\x00", 1)
    trailers = " ".join(re.findall(r"^Co-Authored-By:(.*)$", body, re.M | re.I))
    return "agent" if AGENT.search(author) or AGENT.search(trailers) else "unattributed"


def count(source, snapshot):
    src = text("rev-parse", "--verify", "--end-of-options", f"{source}^{{commit}}").strip()
    signers = show(src, SIGNERS)
    snap = json.loads(Path(snapshot).read_text())
    by_merge = {p["merge_commit"]: p for p in snap["pull_requests"] if p["merge_commit"]}
    first = text("rev-list", "--first-parent", "--parents", src).splitlines()
    acts = []                                            # [act, class, time, pr]
    commits = {}                                         # commit -> pr
    prs = {}
    for row in first:
        c, *parents = row.split()
        if len(parents) == 2:
            p = by_merge.get(c)
            m = MERGE_PR.match(text("log", "-1", "--format=%s", c))
            n = p["number"] if p else int(m.group(1)) if m else None
            for x in text("rev-list", parents[1], f"^{parents[0]}").split():
                commits[x] = n
            prs[n] = {"merge_commit": c, "merged_at": p["merged_at"] if p else None,
                      "merged_by": p["merged_by"] if p else None}
        elif parents:
            commits[c] = None
            acts.append(["direct_push", "REPO", int(text("log", "-1", "--format=%ct", c)), None])
    kinds = {"resign": "KEY", "agent_sign": "KEY", "resign_unverified": "KEY", "agent_sign_unverified": "KEY",
             "promote": "REPO", "key_binding": "REPO"}
    authorship = {}
    for c, n in commits.items():
        parents = text("rev-list", "--parents", "-n1", c).split()[1:]
        if len(parents) > 1:
            if text("log", "-1", "--format=%cn", c).strip() == "GitHub":
                acts.append(["branch_update", "AMBIGUOUS", int(text("log", "-1", "--format=%ct", c)), n])
            continue
        t = int(text("log", "-1", "--format=%ct", c))
        for a in commit_acts(c, parents[0] if parents else None, signers):
            acts.append([a, kinds[a], t, n])
        a = attribution(c)
        authorship.setdefault(n, {"agent": 0, "unattributed": 0})[a] += 1
    for n, p in prs.items():
        if p["merged_by"]:
            acts.append(["merge", "FORGE", iso(p["merged_at"]), n])
    for p in snap["pull_requests"]:
        closes = [e for e in p["events"] if e[0] == "closed"]
        if p["state"] == "closed" and not p["merged_at"] and closes and closes[-1][1] == OWNER_LOGIN:
            acts.append(["close_unmerged", "AMBIGUOUS", iso(closes[-1][2]), p["number"]])
    for s in snap["rulesets"]:
        for _, actor, at in s["history"]:
            if actor == snap["owner"]["id"]:
                acts.append(["ruleset", "FORGE", iso(at), None])
    for at, _, _, actor, _, _ in snap["manual_runs"]:
        if actor == OWNER_LOGIN:
            acts.append(["rerun", "AMBIGUOUS", iso(at), None])
    acts.append(["repository", "FORGE", iso(snap["created_at"]), None])
    acts.sort(key=lambda a: (a[2], a[0], a[3] or 0))
    owner = [a for a in acts if a[0] in OWNER_ACTS]
    per_pr = {}
    for n, p in sorted(prs.items(), key=lambda kv: kv[1]["merged_at"] or ""):
        mine = [a for a in acts if a[3] == n]
        row = {k: sum(1 for a in mine if a[0] == k) for k in OWNER_ACTS + AMBIGUOUS + ("agent_sign",)}
        row.update(pr=n, week=week(iso(p["merged_at"])) if p["merged_at"] else None,
                   owner_acts=sum(1 for a in mine if a[0] in OWNER_ACTS), commits=authorship.get(n, {}))
        per_pr[str(n)] = row
    weeks = {}
    for a in acts:
        if a[0] not in OWNER_ACTS + AMBIGUOUS:
            continue
        w = weeks.setdefault(week(a[2]), {"owner_acts": 0, "KEY": 0, "REPO": 0, "FORGE": 0, "AMBIGUOUS": 0,
                                         **{k: 0 for k in OWNER_ACTS + AMBIGUOUS}})
        w["owner_acts"] += a[0] in OWNER_ACTS
        w[a[1]] += 1
        w[a[0]] += 1
    for row in per_pr.values():
        if row["week"]:
            w = weeks.setdefault(row["week"], {"owner_acts": 0, "KEY": 0, "REPO": 0, "FORGE": 0, "AMBIGUOUS": 0,
                                         **{k: 0 for k in OWNER_ACTS + AMBIGUOUS}})
            w["merged_prs"] = w.get("merged_prs", 0) + 1
            w["prs_with_only_the_merge"] = w.get("prs_with_only_the_merge", 0) + (row["owner_acts"] == row["merge"] == 1)
            for k in ("agent", "unattributed"):
                w["commits_" + k] = w.get("commits_" + k, 0) + row["commits"].get(k, 0)
    for w in weeks.values():
        w["owner_acts_per_merged_pr"] = round(w["owner_acts"] / w["merged_prs"], 2) if w.get("merged_prs") else None
    totals = {k: sum(1 for a in acts if a[0] == k) for k in OWNER_ACTS + AMBIGUOUS}
    totals.update({c: sum(1 for a in owner if a[1] == c) for c in ("KEY", "REPO", "FORGE")}, owner_acts=len(owner),
                  AMBIGUOUS=sum(1 for a in acts if a[1] == "AMBIGUOUS"),
                  agent_sign=sum(1 for a in acts if a[0] == "agent_sign"),
                  unverified=sum(1 for a in acts if a[0].endswith("_unverified")),
                  merged_prs=len(prs), prs_with_only_the_merge=sum(1 for r in per_pr.values() if r["owner_acts"] == r["merge"] == 1),
                  commits={k: sum(r["commits"].get(k, 0) for r in per_pr.values()) +
                           (authorship.get(None, {}).get(k, 0)) for k in ("agent", "unattributed")})
    gh_identity = {"pull_requests": len(snap["pull_requests"]),
                   "authors": sorted({p["author"] for p in snap["pull_requests"]}),
                   "mergers": sorted({p["merged_by"] for p in snap["pull_requests"] if p["merged_by"]}),
                   "event_actors": sorted({e[1] for p in snap["pull_requests"] for e in p["events"] if e[1]}),
                   "events_via_an_app": sum(1 for p in snap["pull_requests"] for e in p["events"] if e[3]),
                   "collaborators": snap["collaborators"], "secrets": snap["secrets"], "variables": snap["variables"],
                   "deploy_keys": snap["deploy_keys"]}
    return {"source": src, "github_snapshot": {"fetched_at": snap["fetched_at"], "repository_created_at": snap["created_at"]},
            "predicates": __doc__.split("Every act has a class")[1].strip(), "totals": totals,
            "per_week": dict(sorted(weeks.items())), "per_pr": per_pr, "github_identity": gh_identity,
            "acts": [[a[0], a[1], datetime.datetime.fromtimestamp(a[2], datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), a[3]]
                     for a in acts]}


def table(counted):
    d = json.loads(Path(counted).read_text())
    cols = ("merge", "resign", "promote", "key_binding", "owner_acts", "branch_update", "agent_sign")
    out = [f"# Owner acts per merged pull request\n",
           f"Generated by `scripts/owner-acts.py table` from `owner-acts.json` (source {d['source'][:12]}, GitHub snapshot "
           f"{d['github_snapshot']['fetched_at']}); predicates in `scripts/owner-acts.py`. `branch_update` is AMBIGUOUS "
           "and `agent_sign` is the agent's: neither is in `owner_acts`. Commits: agent-attributed / unattributed.\n",
           "| PR | week | " + " | ".join(cols) + " | commits |", "| ---: | --- |" + " ---: |" * len(cols) + " --- |"]
    for r in sorted(d["per_pr"].values(), key=lambda r: r["pr"]):
        c = r["commits"]
        out.append(f"| #{r['pr']} | {r['week']} | " + " | ".join(str(r[k]) for k in cols)
                   + f" | {c.get('agent', 0)} / {c.get('unattributed', 0)} |")
    rest = [a for a in d["acts"] if a[3] is None and a[0] in OWNER_ACTS + AMBIGUOUS]
    out += ["", "Acts outside any pull request:", ""] + [f"- {a[2]} {a[0]} ({a[1]})" for a in rest]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").add_argument("--out")
    c = sub.add_parser("count")
    c.add_argument("--source", default="HEAD")
    c.add_argument("--github", default=str(ROOT / "docs/measurements/2026-10-27-warrant3/github-snapshot.json"))
    c.add_argument("--out")
    sub.add_parser("table").add_argument("--counted", default=str(ROOT / "docs/measurements/2026-10-27-warrant3/owner-acts.json"))
    a = ap.parse_args(argv)
    if a.cmd == "table":
        sys.stdout.write(table(a.counted))
        return 0
    doc = fetch() if a.cmd == "fetch" else count(a.source, a.github)
    out = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if a.out:
        Path(a.out).write_text(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
