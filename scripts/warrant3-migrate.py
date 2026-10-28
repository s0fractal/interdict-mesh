#!/usr/bin/env python3
"""The one migration of sokol-core's contracts into its Warrant 3 store (ADR-0033).

    warrant3-migrate.py run --source REV --key CLAUDE_SEED   write .warrant/records.jsonl and blobs
    warrant3-migrate.py verify                               replay from the source the genesis names

Adapted from the phase-1 study (PR #67, scripts/warrant3-mirror.py on branch study/warrant3-mirror),
contracts only. Everything is derived from Git objects at one source commit, never the working tree:

- A contract file is a `sokol-contract@1` lineage: one version per entry of its `decisions`, and a
  first version for a contract that existed before its first decision. Each version's body is the
  contract file as Git holds it after that decision, filed as `sokol-core/files` (the files were
  unsigned). State `provisional` (agent tier, ADR-0028), `active` (owner tier) or `retired`.
- An acceptance is the owner's (agent's) SSH signature over the manifest that pinned the version:
  an `attest` by `s0fractal` (`agent`), from the earliest signed manifest whose contract pin equals
  the version's, verified under the source's .github/witness-signers.
- These records carry `sig: null` and are vouched for by one `migration@1` attest by `claude`
  (role `migrator` in .warrant/v3.json); `verify` re-runs the derivation (the replay basis, V3 §9).

The script is deleted once the store is committed; it is replayed at the commit that added it.
"""
import argparse
import hashlib
import itertools
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from warrant import jcs as C
from warrant import keys as K
from warrant import records as R
from warrant.bootstrap import SCHEMAS
from warrant.engine import assess
from warrant.store import Store

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".warrant"
REPOSITORY = "s0fractal/sokol-core"
FILES, OWNER, AGENT, MIGRATOR = "sokol-core/files", "s0fractal", "agent", "claude"
BOOT_AT = 1791590400                                   # 2026-10-10T00:00:00Z: before this history's first commit
MANIFESTS = ((OWNER, "owner", "docs/witness-manifest.json", "docs/witness-manifest.json.sig"),
             (AGENT, "provisional", "docs/witness-provisional.json", "docs/witness-provisional.json.sig"))
SIGNERS, NAMESPACE = ".github/witness-signers", "sokol-witness"
PRINCIPAL = {OWNER: "owner", AGENT: "agent"}
CONTRACT_FILE = re.compile(r"docs/contracts/([A-Z][A-Z0-9]*-[A-Z0-9-]+)\.shadow\.json\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def accepted_by(role):
    return R.guard(1, [role], {"verdict": "accept"})


AUTHORS = ["contract/author"]
CONTRACT = {"name": "sokol-contract@1",
            "fields": {"state": "str", "id": "str", "profile": "str", "statement": "str", "evidence_text": "str",
                       "witnesses": "strs", "decision": "obj?", "annotations": "obj?", "retirement": "obj?",
                       "replaced_by": "ref?", "proposal": "ref?", "source": "obj?"},
            "states": {"provisional": accepted_by("contract/agent"), "active": accepted_by("contract/owner"),
                       "retired": accepted_by("contract/owner")},
            "closed": [], "successors": {"provisional": AUTHORS, "active": AUTHORS, "retired": AUTHORS}}
REVIEW = [s for s in SCHEMAS if s["name"] in ("pr-head@1", "finding@1")]
DROPPED = {
    "manifest rows, witnesses, closures, build, trust_root":
        "witness-body, closure, build and trust-root pins stay in the owner's SSH manifest (ADR-0023); "
        "each acceptance names its manifest and signature by sha256 and commit",
    "INVARIANTS.md prose": "the document around the rows; each row is rendered from its lineage",
    "proposal bytes not in Git": "contract.py accept deleted the proposal; its sha256 stays in the decision",
}
DECLARED = {
    "files actor": "versions are filed as sokol-core/files: the contract files were unsigned, and their acceptance "
                   "is the signature over the manifest that pinned them",
    "earliest signature": "a version carries one acceptance per signer, from the earliest verified manifest whose "
                          "contract pin equals the version's",
}


class Refused(Exception):
    pass


def need(ok, why):
    if not ok:
        raise Refused(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(value):
    """scripts/contract.py's bytes of a contract file."""
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def resolve(rev):
    need(not rev.startswith("-"), "a revision does not start with '-'")
    c = git("rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}").decode().strip()
    need(HEX40.fullmatch(c) is not None, f"{rev} is not a commit")
    return c


def show(commit, path):
    try:
        return git("show", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        return None


def touching(src, path):
    out = git("log", "--full-history", "--topo-order", "--reverse", "--format=%H %ct", src, "--", path).decode()
    return [(c, int(t)) for c, t in (x.split() for x in out.splitlines())]


def proposals(src):
    out = {}
    raw = git("log", "--full-history", "--format=", "--raw", "--no-abbrev", src, "--", "docs/contracts/proposals").decode()
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].strip("0"):
            data = git("cat-file", "blob", parts[3])
            out[sha(data)] = data
    return out


def pin(doc):
    """witness-pin.py's former contract_pins of one contract: what a signer accepted."""
    accepted = {k: doc.get(k) for k in ("statement", "evidence_text", "witnesses", "decisions")}
    if doc.get("status") == "retired":
        accepted.update(status=doc["status"], retirement=doc["retirement"])
    return sha(json.dumps(accepted, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def history_versions(final, history):
    dec = final.get("decisions", [])
    base = not dec or dec[0]["previous_statement_sha256"] is not None
    by_k = {}
    for c, t, doc in history:
        k = len(doc.get("decisions", []))
        if doc.get("decisions", []) != dec[:k]:
            continue
        if k in by_k:
            need(by_k[k][2] == doc, f"{final['id']}: two contents after decision {k}")
            continue
        by_k[k] = (c, t, doc)
    ks = list(range(0 if base else 1, len(dec) + 1))
    need(set(ks) <= set(by_k), f"{final['id']}: no content in Git after decisions {sorted(set(ks) - set(by_k))}")
    need(by_k[len(dec)][2] == final, f"{final['id']}: the source file is not its last content in Git")
    out = [(k, *by_k[k]) for k in ks]
    for (_, _, _, a), (k, _, _, _) in itertools.pairwise(out):
        need(sha(a["statement"].encode()) == dec[k - 1]["previous_statement_sha256"],
             f"{final['id']}: decision {k} names another previous statement")
    return out


def state_of(doc):
    return "retired" if doc.get("status") == "retired" else "provisional" if doc.get("tier") == "provisional" else "active"


def version_body(doc, k, commit, path, replaced_by=None, proposal=None):
    body = {"state": state_of(doc), "id": doc["id"], "profile": doc["profile"], "statement": doc["statement"],
            "evidence_text": doc["evidence_text"], "witnesses": doc["witnesses"], "source": {"commit": commit, "path": path}}
    if k:
        body["decision"] = doc["decisions"][k - 1]
    for key, value in (("annotations", doc.get("annotations")), ("retirement", doc.get("retirement")),
                       ("replaced_by", replaced_by), ("proposal", proposal)):
        if value is not None:
            body[key] = value
    return body


def contract_of(path):
    """The contract file a lineage's path (bodies, root first) re-derives."""
    leaf = path[-1]
    doc = {k: leaf[k] for k in ("profile", "id", "statement", "evidence_text", "witnesses")}
    if "annotations" in leaf:
        doc["annotations"] = leaf["annotations"]
    decisions = [b["decision"] for b in path if "decision" in b]
    if decisions:
        doc["decisions"] = decisions
    if leaf["state"] == "provisional":
        doc["tier"] = "provisional"
    if leaf["state"] == "retired":
        doc.update(status="retired", retirement=leaf["retirement"])
    return doc


class Migration:
    def __init__(self, source):
        self.src = resolve(source)
        self.tree = git("rev-parse", f"{self.src}^{{tree}}").decode().strip()
        self.out, self.src_of, self.blobs, self.versions = {}, {}, {}, {}
        self.unpinned, self.unverified = [], []

    def emit(self, r, sources):
        i = R.rid(r)
        self.out[i] = r
        self.src_of[i] = sorted(sources)
        return i

    def blob(self, data):
        self.blobs[sha(data)] = data
        return sha(data)

    def contracts(self):
        files = [p for p in git("ls-tree", "-r", "--name-only", self.src, "--", "docs/contracts").decode().splitlines()
                 if CONTRACT_FILE.fullmatch(p)]
        need(files, "the source has no contract")
        known = proposals(self.src)
        plan = {}
        for path in files:
            final = json.loads(show(self.src, path))
            need(dump(final).encode() == show(self.src, path), f"{path} is not in contract.py's format")
            hist = [(c, t, json.loads(b)) for c, t in touching(self.src, path) if (b := show(c, path)) is not None]
            plan[final["id"]] = (path, history_versions(final, hist))
        roots = {}
        for rid, (path, vs) in sorted(plan.items()):
            k, c, t, doc = vs[0]
            roots[rid] = self.version(rid, path, k, c, t, doc, None, known, {})
        for rid, (path, vs) in sorted(plan.items()):
            prev = roots[rid]
            for k, c, t, doc in vs[1:]:
                prev = self.version(rid, path, k, c, t, doc, prev, known, roots)
        return plan

    def version(self, rid, path, k, commit, at, doc, lineage, known, roots):
        replacement = (doc.get("retirement") or {}).get("replacement")
        replaced_by = roots[replacement] if replacement else None
        p = doc["decisions"][k - 1]["proposal_sha256"] if k else None
        proposal = self.blob(known[p]) if p in known else None
        body = version_body(doc, k, commit, path, replaced_by, proposal)
        r = R.record("entity", FILES, at, body, schema=CONTRACT["name"], lineage=lineage,
                     refs=[x for x in (replaced_by, proposal) if x], guard=CONTRACT["states"][body["state"]])
        i = self.emit(r, [f"{commit}:{path}"])
        self.versions.setdefault(rid, []).append((i, doc, body))
        return i

    def acceptances(self):
        signers = show(self.src, SIGNERS)
        need(signers is not None, f"the source has no {SIGNERS}")
        by_pin = {(rid, pin(doc)): i for rid, vs in self.versions.items() for i, doc, _ in vs}
        done = set()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "signers").write_bytes(signers)
            for actor, tier, manifest, signature in MANIFESTS:
                seen = set()
                for c, t in touching(self.src, signature):
                    m, s = show(c, manifest), show(c, signature)
                    if m is None or s is None or (sha(m), sha(s)) in seen:
                        continue
                    seen.add((sha(m), sha(s)))
                    Path(tmp, "sig").write_bytes(s)
                    ok = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(Path(tmp, "signers")), "-I",
                                         PRINCIPAL[actor], "-n", NAMESPACE, "-s", str(Path(tmp, "sig"))], input=m,
                                        capture_output=True, timeout=10, check=False).returncode == 0
                    if not ok:
                        self.unverified.append(f"{c}:{signature}")
                        continue
                    for rid, p in sorted(json.loads(m).get("contracts", {}).items()):
                        v = by_pin.get((rid, p))
                        if v is None or (actor, v) in done:
                            continue
                        done.add((actor, v))
                        body = {"target": v, "verdict": "accept", "tier": tier, "pin": p, "manifest": sha(m),
                                "signature": sha(s), "commit": c}
                        self.emit(R.record("attest", actor, t, body, refs=[v]), [f"{c}:{manifest}", f"{c}:{signature}"])
        self.unpinned = sorted(i for vs in self.versions.values() for i, _, _ in vs
                               if not any(a in done for a in ((OWNER, i), (AGENT, i))))

    def run(self):
        plan = self.contracts()
        self.acceptances()
        return {"contracts": len(plan), "contract_versions": sum(len(v) for v in self.versions.values()),
                "acceptances": sum(1 for r in self.out.values() if r["kind"] == "attest"),
                "versions_without_acceptance": len(self.unpinned), "unverified_signatures": self.unverified}


def code():
    return sha(Path(__file__).read_bytes())


def migrate(source, key):
    m = Migration(source)
    counts = m.run()
    src = {"repository": REPOSITORY, "commit": m.src, "tree": m.tree}
    maph = m.blob(C.canon({"migration": "sokol-warrant3/map@1", "source": src, "dropped": DROPPED, "declared": DECLARED,
                           "map": [[i, m.src_of[i], []] for i in sorted(m.out)]}))
    lines, prev = [R.line(r)[1] for r in m.out.values()], None
    for s in (CONTRACT, *REVIEW):
        prev, line = R.line(R.record("schema", MIGRATOR, BOOT_AT, s, prev=prev), key)
        lines.append(line)
    at = max([BOOT_AT] + [r["at"] for r in m.out.values()])
    gen = R.record("attest", MIGRATOR, at, {"target": maph, "verdict": "migrated", "source": src,
                                            "code": code(), "script": "scripts/warrant3-migrate.py",
                                            "records": len(m.out)}, R.MIGRATION, refs=[maph], prev=prev)
    gid, line = R.line(gen, key)
    lines.append(line)
    return lines, m.blobs, {"source": src, "genesis": gid, "records": len(lines), "blobs": len(m.blobs), **counts}


def config():
    return json.loads((STORE / "v3.json").read_text())


def verify():
    """Replay the derivation from the source the genesis names, assess the store under .warrant/v3.json, and
    re-derive every contract file (each version and the leaf) from the records alone."""
    snap = Store(STORE).snapshot()
    doc = config()
    rep = assess(snap, doc["trust"], doc["profile"])
    recs = {i: e[0]["record"] for i, e in snap.lines.items() if i not in rep["rejected"]}
    gens = [r for r in recs.values() if r["schema"] == R.MIGRATION]
    need(len(gens) == 1, f"{len(gens)} migration records")
    g = gens[0]["body"]
    need(g["code"] == code(), f"the genesis names migration code {g['code'][:12]}; run that code")
    m = Migration(g["source"]["commit"])
    m.run()
    have = {i for i, envs in snap.lines.items() if all(e["sig"] is None for e in envs)}
    out = {"problems": rep["problems"], "rejected": rep["rejected"], "basis": rep["basis"],
           "replay": "IDENTICAL" if have == set(m.out) else "DIFFERS"}
    src, diffs, versions, files = g["source"]["commit"], [], 0, 0
    for lin in rep["lineages"].values():
        if lin["schema"] != CONTRACT["name"]:
            continue
        path = [recs[v]["body"] for v in lin["path"]]
        for n, b in enumerate(path):
            versions += 1
            want = show(b["source"]["commit"], b["source"]["path"])
            derived = contract_of(path[:n + 1])
            if want is None or (dump(derived).encode() != want and json.loads(want) != derived):
                diffs.append(f"{b['source']['commit']}:{b['source']['path']}")
        files += 1
        if dump(contract_of(path)).encode() != show(src, path[-1]["source"]["path"]):
            diffs.append(f"leaf {path[-1]['id']}")
        tier = AGENT if path[-1]["state"] == "provisional" else OWNER
        if lin["reliance"] != "ELIGIBLE" or lin["effective"] != lin["leaf"] or \
                tier not in rep["versions"][lin["leaf"]]["accepted_by"]:
            diffs.append(f"{path[-1]['id']} not ELIGIBLE at its leaf under its tier's signer")
    out.update(contracts=files, versions=versions, diffs=diffs)
    out["result"] = "IDENTICAL" if not (out["problems"] or out["rejected"] or diffs) and out["replay"] == "IDENTICAL" \
        else "DIFFERS"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--source", required=True)
    run.add_argument("--key", required=True)
    sub.add_parser("verify")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "run":
            p = Path(a.key).expanduser()
            need(p.is_file() and not p.resolve().is_relative_to(ROOT), "a seed file outside the repository")
            lines, blobs, summary = migrate(a.source, K.Key.from_seed_hex(p.read_text().strip()))
            for f in ("records.jsonl",):
                (STORE / f).unlink(missing_ok=True)
            st = Store(STORE)
            st.write_lines(lines)
            for data in blobs.values():
                st.put_blob(data)
            print(json.dumps(summary, indent=1, sort_keys=True))
        else:
            res = verify()
            print(json.dumps(res, indent=1, sort_keys=True))
            return 0 if res["result"] == "IDENTICAL" else 1
    except Refused as e:
        print(f"REFUSED {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
