#!/usr/bin/env python3
"""Phase 1 of the Warrant 3 study: a read-only shadow of the contracts and ADRs as Warrant 3 records.

    warrant3-mirror.py identity                         the mirror checker's code identity
    warrant3-mirror.py keygen [--out SEED]              a mirror seed, outside the repository
    warrant3-mirror.py run [--source REV] [--key SEED]  write the store to .warrant/
    warrant3-mirror.py verify [--store DIR]             replay and re-derive: IDENTICAL or the exact diff
    warrant3-mirror.py selftest                         the mapping's round trip and mutants of the store

Runs under warrant-graph==3.0.0a1 exactly (scripts/warrant3-mirror.requirements.txt), refused otherwise.
Nothing here is read by the gate, CI or scripts/contract.py: the contracts, the manifests and their
signatures stay the only authority (ADR-0023, ADR-0024, ADR-0028). The store is derived from Git
objects at one source commit (never the working tree), so the same commit gives the same record ids.

The mapping (docs/measurements/2026-10-27-warrant3/README.md):

- A contract is a `sokol-contract@1` lineage: one version per entry of its `decisions` history, and a
  first version for a contract that existed before its first decision. Each version's content is the
  contract file as Git holds it at that decision; the versions are filed as `sokol-core/files`,
  because sokol's contract files are unsigned. Its state is `provisional` (the agent tier),
  `active` or `retired` (with the retirement record and a `replaced_by` reference).
- An acceptance is the owner's (or for the agent tier, the agent's) SSH signature over the manifest
  that pins the version (docs/witness-manifest.json, docs/witness-provisional.json): an `attest` by
  `owner` or `agent`, from the earliest signed manifest whose contract pin equals the version's,
  verified under the source's .github/witness-signers.
- An ADR is a `sokol-adr@1` lineage of one version whose `file` is the Markdown file as a blob.
- Every such record carries `sig: null` (the mirror never signs as the owner, the agent or the
  files) and is vouched for by one `migration@1` attest of the checker `sokol-warrant3-mirror`,
  whose map lists the Git objects each record was derived from.
"""
import argparse
import difflib
import hashlib
import importlib.metadata
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".warrant"
CONFIG = "mirror.json"
WARRANT_VERSION = "3.0.0a1"
# engine.code_identity() of the warrant-graph 3.0.0a1 wheel: the package files and the signature library.
WARRANT_CODE = "a03d889ea115724b3b953193ccdd5e0ede7fe97bfa6f9572ad74c9b1b6567519"
HASHED = ("scripts/warrant3-mirror.py", "scripts/witness-pin.py")
SEED = Path.home() / ".config/warrant/sokol-mirror.seed"
REPOSITORY = "s0fractal/sokol-core"
MIRROR, FILES, OWNER, AGENT = "sokol-warrant3-mirror", "sokol-core/files", "owner", "agent"
BOOT_AT = 1791590400                                   # 2026-10-10T00:00:00Z: before this history's first commit
MANIFESTS = ((OWNER, "owner", "docs/witness-manifest.json", "docs/witness-manifest.json.sig"),
             (AGENT, "provisional", "docs/witness-provisional.json", "docs/witness-provisional.json.sig"))
SIGNERS, NAMESPACE = ".github/witness-signers", "sokol-witness"
CONTRACT_FILE = re.compile(r"docs/contracts/([A-Z][A-Z0-9]*-[A-Z0-9-]+)\.shadow\.json\Z")
ADR_FILE = re.compile(r"docs/adr/([0-9]{4})-[a-z0-9-]+\.md\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")

if importlib.metadata.version("warrant-graph") != WARRANT_VERSION:
    sys.exit(f"REFUSED warrant-graph {importlib.metadata.version('warrant-graph')} is installed; this needs {WARRANT_VERSION}")
from warrant import jcs as C                              # noqa: E402
from warrant import keys as K                             # noqa: E402
from warrant import records as R                          # noqa: E402
from warrant.engine import assess, code_identity          # noqa: E402
from warrant.store import Store                           # noqa: E402

_spec = importlib.util.spec_from_file_location("witness_pin", ROOT / "scripts/witness-pin.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def accepted_by(role):
    return R.guard(1, [role], {"verdict": "accept"})


CONTRACT = {"name": "sokol-contract@1",
            "fields": {"state": "str", "id": "str", "profile": "str", "statement": "str", "evidence_text": "str",
                       "witnesses": "strs", "decision": "obj?", "annotations": "obj?", "retirement": "obj?",
                       "replaced_by": "ref?", "proposal": "ref?", "source": "obj"},
            "states": {"provisional": accepted_by("contract/agent"), "active": accepted_by("contract/owner"),
                       "retired": accepted_by("contract/owner")},
            "closed": [], "successors": {}}
ADR = {"name": "sokol-adr@1", "fields": {"state": "str", "number": "int", "path": "str", "file": "ref", "source": "obj"},
       "states": {"recorded": None}, "closed": [], "successors": {}}
# What the mirror does not carry, and why (the map blob lists it; GAPS.md says what each loss costs).
DROPPED = {
    "manifest rows, witnesses, closures_v1..v4, build_v1..v3, trust_root_v1..v2":
        "witness-body, closure, build and trust-root pins: each acceptance names its manifest by sha256 and commit; "
        "no Warrant 3 rule recomputes them (GAPS G1)",
    "INVARIANTS.md prose and row order": "the document around the rows; each row is re-derived from its contract",
    "proposal bytes not in Git": "contract.py accept deletes the proposal; its sha256 stays in the decision",
    "acceptances of versions no verified signature pins": "counted in the summary, never invented",
}
DECLARED = {
    "files actor": "versions are filed as sokol-core/files: the contract files are unsigned, and their acceptance "
                   "is the signature over the manifest that pins them",
    "earliest signature": "a version carries one acceptance per signer, from the earliest verified manifest whose "
                          "contract pin equals the version's; later re-signatures of the same pin add nothing",
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


# ---------------------------------------------------------------- identity

def identity():
    """The digest of what decides the store: this file, the witness-pin.py it imports, the Warrant
    package (its own code identity, pinned) and the interpreter's version."""
    files = {name: sha((ROOT / name).read_bytes()) for name in HASHED}
    return C.doc_id({"mirror": "sokol-warrant3-mirror@1", "files": files, "warrant": code_identity(),
                     "python": list(sys.version_info[:2])})


def env():
    import cryptography
    return {"python": ".".join(map(str, sys.version_info[:3])), "cryptography": cryptography.__version__,
            "warrant-graph": WARRANT_VERSION}


def closure_problem():
    if code_identity() != WARRANT_CODE:
        return f"the installed warrant package is not the {WARRANT_VERSION} wheel (code {code_identity()[:12]})"
    hashed = {(ROOT / n).resolve() for n in HASHED}
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if f and Path(f).resolve().is_relative_to(ROOT) and Path(f).resolve() not in hashed:
            return f"{Path(f).resolve().relative_to(ROOT)} is imported and not in the identity"
    return None


# ---------------------------------------------------------------- Git objects

def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def resolve(rev):
    """The canonical full id of a commit (never a ref in what is recorded)."""
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
    """[(commit, committer time)] of the commits reachable from src that change path, oldest first."""
    out = git("log", "--full-history", "--topo-order", "--reverse", "--format=%H %ct", src, "--", path).decode()
    return [(c, int(t)) for c, t in (x.split() for x in out.splitlines())]


def listing(src, prefix):
    return git("ls-tree", "-r", "--name-only", src, "--", prefix).decode().splitlines()


def proposals(src):
    """{sha256: bytes} of every proposal file Git holds in src's history."""
    out = {}
    raw = git("log", "--full-history", "--format=", "--raw", "--no-abbrev", src, "--", "docs/contracts/proposals").decode()
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].strip("0"):
            data = git("cat-file", "blob", parts[3])
            out[sha(data)] = data
    return out


# ---------------------------------------------------------------- the mapping (pure)

def pin(doc):
    """witness-pin.py contract_pins of one contract: what a signer accepts (selftest S1 holds it to the original)."""
    accepted = {k: doc.get(k) for k in ("statement", "evidence_text", "witnesses", "decisions")}
    if doc.get("status") == "retired":
        accepted.update(status=doc["status"], retirement=doc["retirement"])
    return sha(json.dumps(accepted, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def history_versions(final, history):
    """[(k, commit, time, doc)]: the contract after each of its decisions (k = how many), and before the
    first one when it existed then. history: [(commit, time, doc)] oldest first."""
    dec = final.get("decisions", [])
    base = not dec or dec[0]["previous_statement_sha256"] is not None
    by_k = {}
    for c, t, doc in history:
        k = len(doc.get("decisions", []))
        if doc.get("decisions", []) != dec[:k]:
            continue                                     # a branch whose decisions did not land
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
    """The contract file a lineage's path (its versions' bodies, root first) re-derives."""
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


def guard_of(state):
    return CONTRACT["states"][state]


# ---------------------------------------------------------------- the migration

class Migration:
    def __init__(self, source):
        self.src = resolve(source)
        self.tree = git("rev-parse", f"{self.src}^{{tree}}").decode().strip()
        for name in HASHED[1:]:
            need(show(self.src, name) == (ROOT / name).read_bytes(),
                 f"{name} differs from the source's: the mirror renders with the source's own code")
        self.out, self.src_of, self.blobs = {}, {}, {}
        self.versions = {}                               # rid -> [(version id, doc, body)]
        self.unpinned, self.unverified = [], []

    def emit(self, r, sources):
        i = R.rid(r)
        self.out[i] = r
        self.src_of[i] = sorted(sources)
        return i

    def blob(self, data):
        h = sha(data)
        self.blobs[h] = data
        return h

    def contracts(self):
        files = [p for p in listing(self.src, "docs/contracts") if CONTRACT_FILE.fullmatch(p)]
        need(files, "the source has no contract")
        known = proposals(self.src)
        plan = {}
        for path in files:
            final = json.loads(show(self.src, path))
            need(dump(final).encode() == show(self.src, path), f"{path} is not in contract.py's format")
            hist = [(c, t, json.loads(b)) for c, t in touching(self.src, path) if (b := show(c, path)) is not None]
            plan[final["id"]] = (path, history_versions(final, hist))
        roots = {}
        for rid, (path, vs) in sorted(plan.items()):     # roots first: a retirement names its replacement's root
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
        refs = [x for x in (replaced_by, proposal) if x]
        r = R.record("entity", FILES, at, body, schema=CONTRACT["name"], lineage=lineage, refs=refs,
                     guard=guard_of(body["state"]))
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
                    ok = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(Path(tmp, "signers")), "-I", actor,
                                         "-n", NAMESPACE, "-s", str(Path(tmp, "sig"))], input=m, capture_output=True,
                                        timeout=10, check=False).returncode == 0
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

    def adrs(self):
        files = sorted(p for p in listing(self.src, "docs/adr") if ADR_FILE.fullmatch(p))
        need(files, "the source has no ADR")
        for path in files:
            data = show(self.src, path)
            c, t = touching(self.src, path)[-1]
            body = {"state": "recorded", "number": int(ADR_FILE.fullmatch(path).group(1)), "path": path,
                    "file": self.blob(data), "source": {"commit": c, "path": path}}
            self.emit(R.record("entity", FILES, t, body, schema=ADR["name"], refs=[body["file"]]), [f"{c}:{path}"])
        return files

    def run(self):
        plan = self.contracts()
        self.acceptances()
        adrs = self.adrs()
        return {"contracts": len(plan), "contract_versions": sum(len(v) for v in self.versions.values()),
                "adrs": len(adrs), "acceptances": sum(1 for r in self.out.values() if r["kind"] == "attest"),
                "versions_without_acceptance": len(self.unpinned), "unverified_signatures": self.unverified,
                "proposal_blobs": sum(1 for vs in self.versions.values() for _, _, b in vs if "proposal" in b),
                "decisions_with_proposal": sum(1 for vs in self.versions.values() for _, _, b in vs
                                               if (b.get("decision") or {}).get("proposal_sha256"))}


def migrate(source, key):
    """(lines, blobs, config, summary) of the mirror of `source`."""
    m = Migration(source)
    counts = m.run()
    me = identity()
    src = {"repository": REPOSITORY, "commit": m.src, "tree": m.tree}
    mapdoc = C.canon({"migration": "sokol-warrant3/map@1", "source": src, "dropped": DROPPED, "declared": DECLARED,
                      "map": [[i, m.src_of[i], []] for i in sorted(m.out)]})
    maph = m.blob(mapdoc)
    lines, prev = [R.line(r)[1] for r in m.out.values()], None
    for s in (CONTRACT, ADR):
        prev, line = R.line(R.record("schema", MIRROR, BOOT_AT, s, prev=prev), key)
        lines.append(line)
    at = max([BOOT_AT] + [r["at"] for r in m.out.values()])
    gen = R.record("attest", MIRROR, at, {"target": maph, "verdict": "migrated", "source": src, "code": me, "env": env(),
                                          "records": len(m.out)}, R.MIGRATION, refs=[maph], prev=prev)
    gid, line = R.line(gen, key)
    lines.append(line)
    # The shape of warrant's .warrant/v3.json (repository/3); named mirror.json: it grants this repository nothing.
    config = {"warrant": "repository/3", "repository": REPOSITORY,
              "trust": {"warrant": "trust/3", "keys": {MIRROR: [key.public]}},
              "profile": {"warrant": "profile/3", "roles": {"contract/agent": [AGENT], "contract/owner": [OWNER],
                                                            "migrator": [MIRROR], "schema/author": [MIRROR]}}}
    summary = {"source": src, "genesis": gid, "code": me, "env": env(), "records": len(lines), "blobs": len(m.blobs), **counts}
    return lines, m.blobs, config, summary


def write(out, lines, blobs, config):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    st = Store(out).init()
    st.write_lines(lines)
    for data in blobs.values():
        st.put_blob(data)
    (out / CONFIG).write_text(json.dumps(config, indent=1, sort_keys=True) + "\n")


def load_key(path):
    p = Path(path).expanduser()
    need(p.is_file(), f"no seed at {p}")
    need(not p.resolve().is_relative_to(ROOT), "a seed lives outside the repository")
    return K.Key.from_seed_hex(p.read_text().strip())


# ---------------------------------------------------------------- verify

def diff(name, want, have):
    return "".join(difflib.unified_diff(want.splitlines(keepends=True), have.splitlines(keepends=True),
                                        f"{name} (source)", f"{name} (from the store)"))


def _config(store):
    config = json.loads((Path(store) / CONFIG).read_text())
    return config["trust"], config["profile"]


def verify(store=STORE):
    """Replay the migration from the source commit the genesis names, assess the store under the mirror's
    profile, and re-derive every contract file (each version and the leaf), the INVARIANTS.md rows and every
    ADR from the store's records alone, comparing each with the source's bytes. A historical version whose bytes
    in Git are not in contract.py's format but equal the re-derived value as JSON is listed apart, never hidden."""
    store = Path(store)
    snap = Store(store).snapshot()
    rep = assess(snap, *_config(store))
    out = {"problems": rep["problems"], "rejected": rep["rejected"], "basis": rep["basis"], "canonical": rep["canonical"]}
    recs = {i: e[0]["record"] for i, e in snap.lines.items() if i not in rep["rejected"]}
    gens = [r for r in recs.values() if r["schema"] == R.MIGRATION]
    need(len(gens) == 1, f"{len(gens)} migration records")
    g = gens[0]["body"]
    need(g["code"] == identity(), f"the genesis names mirror code {g['code'][:12]}; run that code")
    m = Migration(g["source"]["commit"])
    m.run()
    have = {i for i, envs in snap.lines.items() if all(e["sig"] is None for e in envs)}
    want = set(m.out)
    out["replay"] = {"result": "IDENTICAL" if have == want else "DIFFERS", "replayed": len(want),
                     "missing": sorted(want - have), "extra": sorted(have - want)}
    src = g["source"]["commit"]
    diffs, versions, leaves, wrong, format_only = [], 0, {}, [], []
    for L, lin in rep["lineages"].items():
        if lin["schema"] != CONTRACT["name"]:
            continue
        path = [recs[v]["body"] for v in lin["path"]]
        for n in range(len(path)):
            b = path[n]
            versions += 1
            name = f"{b['source']['commit']}:{b['source']['path']}"
            derived = contract_of(path[:n + 1])
            have_bytes, want_bytes = dump(derived), show(b["source"]["commit"], b["source"]["path"])
            if want_bytes is not None and have_bytes.encode() != want_bytes and json.loads(want_bytes) == derived:
                format_only.append(name)            # the same value, written before contract.py's format existed
            elif want_bytes is None or have_bytes.encode() != want_bytes:
                diffs.append(diff(name, (want_bytes or b"").decode(), have_bytes))
        leaf = path[-1]
        leaves[leaf["source"]["path"]] = contract_of(path)
        tier = AGENT if leaf["state"] == "provisional" else OWNER
        if lin["reliance"] != "ELIGIBLE" or lin["effective"] != lin["leaf"] or \
                tier not in rep["versions"][lin["leaf"]]["accepted_by"]:
            wrong.append({"lineage": L, "id": leaf["id"], "reliance": lin["reliance"],
                          "leaf_effective": lin["effective"] == lin["leaf"],
                          "accepted_by": rep["versions"][lin["leaf"]]["accepted_by"], "tier_signer": tier})
    files = [p for p in listing(src, "docs/contracts") if CONTRACT_FILE.fullmatch(p)]
    for p in sorted(set(files) - set(leaves)):
        diffs.append(diff(p, show(src, p).decode(), ""))
    for p in sorted(set(leaves) - set(files)):
        diffs.append(diff(p, "", dump(leaves[p])))
    for p in sorted(set(files) & set(leaves)):
        if dump(leaves[p]).encode() != show(src, p):
            diffs.append(diff(p, show(src, p).decode(), dump(leaves[p])))
    out["contracts"] = {"result": "IDENTICAL" if not diffs else "DIFFERS", "files": len(files), "lineages": len(leaves),
                        "versions": versions, "diffs": diffs, "not_eligible": wrong,
                        "historical_versions_equal_as_json_only": format_only}
    rows_have = sorted(gate.contract_row(c) for c in leaves.values() if c.get("status") != "retired")
    text = show(src, "docs/INVARIANTS.md").decode()
    rows_want = sorted(line for line in text.splitlines() if gate.ROW.match(line))
    out["invariants_rows"] = {"result": "IDENTICAL" if rows_have == rows_want else "DIFFERS", "rows": len(rows_want),
                              "diff": diff("docs/INVARIANTS.md rows (sorted)", "\n".join(rows_want) + "\n",
                                           "\n".join(rows_have) + "\n")}
    adr_have = {recs[lin["leaf"]]["body"]["path"]: snap.blob(recs[lin["leaf"]]["body"]["file"])
                for lin in rep["lineages"].values() if lin["schema"] == ADR["name"] and lin["leaf"]}
    adr_files = [p for p in listing(src, "docs/adr") if ADR_FILE.fullmatch(p)]
    adr_diffs = [diff(p, (show(src, p) or b"").decode(), (adr_have.get(p) or b"").decode())
                 for p in sorted(set(adr_files) | set(adr_have)) if adr_have.get(p) != show(src, p)]
    out["adrs"] = {"result": "IDENTICAL" if not adr_diffs else "DIFFERS", "files": len(adr_files), "diffs": adr_diffs}
    ok = (not out["problems"] and not out["rejected"] and out["replay"]["result"] == "IDENTICAL"
          and out["contracts"]["result"] == "IDENTICAL" and not wrong
          and out["invariants_rows"]["result"] == "IDENTICAL" and out["adrs"]["result"] == "IDENTICAL")
    out["result"] = "IDENTICAL" if ok else "DIFFERS"
    out["source"] = g["source"]
    return out


# ---------------------------------------------------------------- selftest

def selftest():
    """S1: pin() equals witness-pin.py's contract_pins for every contract of the working tree.
    S2: a synthetic contract (base, a changed witness, a provisional row promoted, a retirement) survives the
    mapping and its re-derivation at every version. S3: a broken previous-statement chain is refused.
    M1-M5: mutants of the store, each caught by the check it names; the unmutated store must verify
    IDENTICAL first (BASELINE_RED otherwise)."""
    results = {}
    want = {**gate.contract_pins(ROOT), **gate.contract_pins(ROOT, "provisional")}
    have = {rid: pin(c) for rid, c in gate.load_contracts(ROOT).items()}
    results["S1 pin equals contract_pins"] = want == have and len(want) > 0
    base = {"profile": "sokol.contract-shadow.v1", "id": "TEST-X1", "statement": "s0", "evidence_text": "`a_b_c_d`",
            "witnesses": ["a_b_c_d"], "annotations": {"status": "UNSIGNED_EXPLANATORY_DRAFT"}}
    d1 = {"because": "w", "previous_statement_sha256": sha(b"s0"), "proposal_sha256": "1" * 64}
    v1 = dict(base, statement="s1", decisions=[d1], tier="provisional")
    d2 = {"because": "promoted by the owner", "previous_statement_sha256": sha(b"s1"), "proposal_sha256": None}
    v2 = {k: v for k, v in v1.items() if k != "tier"} | {"decisions": [d1, d2]}
    d3 = {"because": "r", "previous_statement_sha256": sha(b"s1"), "proposal_sha256": "2" * 64}
    v3 = dict(v2, decisions=[d1, d2, d3], status="retired",
              retirement={"mode": "SUPERSEDED", "loss": ["x"], "replacement": "TEST-X2", "counterexamples": []})
    hist = [(f"{n:040x}", n, d) for n, d in enumerate((base, v1, v2, v3))]
    vs = history_versions(v3, hist)
    bodies = [version_body(doc, k, c, "p", "a" * 64 if doc.get("status") else None) for k, c, _, doc in vs]
    results["S2 every version re-derives"] = [contract_of(bodies[:n + 1]) for n in range(len(bodies))] == \
        [base, v1, v2, v3] and [b["state"] for b in bodies] == ["active", "provisional", "active", "retired"]
    try:
        history_versions(v3, [(c, t, dict(d, statement="other") if d is v1 else d) for c, t, d in hist])
        results["S3 a broken previous-statement chain is refused"] = False
    except Refused:
        results["S3 a broken previous-statement chain is refused"] = True
    base_run = verify(STORE)
    if base_run["result"] != "IDENTICAL":
        results["BASELINE_RED: the unmutated store does not verify IDENTICAL"] = False
        return results
    lines = (STORE / "records.jsonl").read_bytes().split(b"\n")[:-1]

    def first(pred):
        return next(x for x in lines if pred(json.loads(x)["record"]))

    leaves = {lin["leaf"] for lin in assess(Store(STORE).snapshot(), *_config(STORE))["lineages"].values()}
    contract = first(lambda r: r["schema"] == CONTRACT["name"] and r["lineage"] is None)
    accept = first(lambda r: r["kind"] == "attest" and r["actor"] == OWNER and r["body"]["target"] in leaves)
    adr = first(lambda r: r["schema"] == ADR["name"])
    later = first(lambda r: r["schema"] == CONTRACT["name"] and r["lineage"] is not None)
    gen = first(lambda r: r["schema"] == R.MIGRATION)
    flipped = re.sub(rb'"ed25519":"(.)', lambda m: b'"ed25519":"' + (b"0" if m.group(1) != b"0" else b"1"), gen, count=1)
    # Each mutant names the check that must catch it: a DIFFERS for another reason, or a refusal, is no kill.
    mutants = {
        "M1 a statement edited in a record": (
            [x.replace(b'"statement":"', b'"statement":"X', 1) if x == contract else x for x in lines],
            lambda v: v["rejected"] and v["replay"]["missing"] and v["contracts"]["diffs"]),
        "M2 an owner acceptance of a leaf dropped": (
            [x for x in lines if x != accept], lambda v: v["replay"]["missing"] and v["contracts"]["not_eligible"]),
        "M3 an ADR version dropped": ([x for x in lines if x != adr], lambda v: v["adrs"]["diffs"]),
        "M4 the migration's signature broken": ([flipped if x == gen else x for x in lines], "0 migration records"),
        "M5 a later contract version dropped": (
            [x for x in lines if x != later], lambda v: v["replay"]["missing"] and v["contracts"]["diffs"]),
    }
    with tempfile.TemporaryDirectory() as tmp:
        for name, (keep, caught) in mutants.items():
            copy = Path(tmp, name[:2])
            shutil.copytree(STORE, copy)
            (copy / "records.jsonl").write_bytes(b"".join(x + b"\n" for x in keep))
            try:
                v = verify(copy)
                results[name] = v["result"] == "DIFFERS" and not isinstance(caught, str) and bool(caught(v))
            except Refused as e:
                results[name] = isinstance(caught, str) and caught in str(e)
    return results


# ---------------------------------------------------------------- command line

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("identity")
    sub.add_parser("keygen").add_argument("--out", default=str(SEED))
    run = sub.add_parser("run")
    run.add_argument("--source", default="HEAD")
    run.add_argument("--key", default=str(SEED))
    sub.add_parser("verify").add_argument("--store", default=str(STORE))
    sub.add_parser("selftest")
    a = ap.parse_args(argv)
    try:
        why = closure_problem()
        need(why is None, f"IDENTITY: {why}")
        if a.cmd == "identity":
            print(json.dumps({"actor": MIRROR, "code": identity(), "env": env()}))
        elif a.cmd == "keygen":
            p = Path(a.out).expanduser()
            need(not p.resolve().is_relative_to(ROOT), "a seed lives outside the repository")
            p.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            key = K.Key.generate()
            os.write(fd, key.seed_hex().encode())
            os.close(fd)
            print(json.dumps({"seed": str(p), "public": key.public, "actor": MIRROR}))
        elif a.cmd == "run":
            lines, blobs, config, summary = migrate(a.source, load_key(a.key))
            write(STORE, lines, blobs, config)
            print(json.dumps(summary, indent=1, sort_keys=True))
        elif a.cmd == "verify":
            res = verify(a.store)
            print(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False))
            return 0 if res["result"] == "IDENTICAL" else 1
        else:
            res = selftest()
            for name, ok in res.items():
                print(("ok   " if ok is True else "FAIL ") + name)
            return 0 if all(v is True for v in res.values()) else 1
    except Refused as e:
        print(f"REFUSED {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
