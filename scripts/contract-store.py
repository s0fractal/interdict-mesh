#!/usr/bin/env python3
"""The contract store under Warrant 3, in step with the tiers' SSH signatures (ADR-0033).

    contract-store.py check [--signers FILE] [--every-pin]   CI: the store as Warrant 3 assesses it
    contract-store.py carry --actor A --key SEED             after a signature: its acceptances, filed

scripts/witness-pin.py decides what the gate decides: it reads the lineages with the standard library
and refuses a leaf its tier's manifest does not pin. This file needs the pinned warrant-graph
(.github/warrant-requirements.txt) and is not part of the trust root: what it files is re-verified here
against the signatures, and nothing the gate decides reads it.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import time

_spec = importlib.util.spec_from_file_location("witness_pin", pathlib.Path(__file__).resolve().parent / "witness-pin.py")
pin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pin)
TIER_ACTOR = {"owner": "s0fractal", "provisional": "agent"}


def tier_manifests(signers):
    """[(tier, manifest bytes, signature bytes)] of the tiers' manifests that verify under `signers`."""
    out = []
    for tier, manifest, signature, principal in (("owner", pin.MANIFEST, pin.SIGNATURE, "owner"),
                                                ("provisional", pin.PROVISIONAL, pin.PROVISIONAL_SIG, "agent")):
        if pin.verify_manifest(manifest, signature, signers, principal):
            out.append((tier, manifest.read_bytes(), signature.read_bytes()))
    return out


def check(signers: pathlib.Path, every_pin: bool = False) -> int:
    """The store as Warrant 3 assesses it under .warrant/v3.json (needs the pinned warrant-graph): canonical, no
    rejected line, no problem; every contract leaf accepted by its tier's signer (`carry` files that after a
    signature; with --every-pin, a push to main, a leaf still waiting is a failure); and every acceptance `carry`
    filed re-verified from the manifest and signature it names: the tier's SSH signature under `signers`,
    pinning exactly that version. The acceptances the migration derived from Git history are vouched for by its
    replay at the commit that added the store (ADR-0033)."""
    from warrant.engine import assess
    from warrant.store import Store
    doc = json.loads((pin.ROOT / '.warrant/v3.json').read_text())
    snap = Store(pin.ROOT / '.warrant').snapshot()
    rep = assess(snap, doc['trust'], doc['profile'])
    problems, notes = [], []
    if rep['problems'] or rep['rejected'] or not rep['canonical']:
        problems.append('store: ' + json.dumps({'problems': rep['problems'][:5], 'rejected': sorted(rep['rejected'])[:5],
                                                'canonical': rep['canonical']}))
    contracts = pin.load_contracts(pin.ROOT)
    for lin in rep['lineages'].values():
        if lin['schema'] == pin.SCHEMA and lin['leaf'] is not None and lin['effective'] != lin['leaf']:
            rid = snap.lines[lin['leaf']][0]['record']['body']['id']
            (problems if every_pin else notes).append(f"{rid}: its leaf version is not accepted in the store yet "
                                                      "(scripts/witness-pin.py carry, after the tier's signature)")
    if sum(1 for lin in rep['lineages'].values() if lin['schema'] == pin.SCHEMA) != len(contracts):
        problems.append('store: a contract lineage the engine excludes or forks')
    versions = {i: e[0]['record'] for i, e in snap.lines.items()}
    for i, envs in sorted(snap.lines.items()):
        r = envs[0]['record']
        if r['kind'] != 'attest' or not r['body'].get('carried'):
            continue
        tier = r['body'].get('tier')
        target = versions.get(r['body']['target'], {'body': {}})['body']
        m, s = snap.blobs.get(r['body'].get('manifest')), snap.blobs.get(r['body'].get('signature'))
        ok = tier in TIER_ACTOR and r['actor'] == TIER_ACTOR[tier] and m is not None and s is not None
        if ok:
            with tempfile.TemporaryDirectory() as tmp:
                pathlib.Path(tmp, 'm').write_bytes(m)
                pathlib.Path(tmp, 's').write_bytes(s)
                ok = pin.verify_manifest(pathlib.Path(tmp, 'm'), pathlib.Path(tmp, 's'), signers,
                                     'owner' if tier == 'owner' else 'agent')
            ok = ok and json.loads(m).get(pin.CONTRACTS, {}).get(target.get('id')) == r['body']['target']
        if not ok:
            problems.append(f"acceptance {i[:12]} by {r['actor']}: no {tier} signature under {signers.name} pins its version")
    for x in notes:
        print('note', x)
    for x in problems:
        print('FAIL', x)
    if not problems:
        print(f"ok   store: {len(snap.lines)} records, {len(contracts)} contract lineages, basis {rep['basis']}")
    return 1 if problems else 0


def carry(actor: str, key: str) -> int:
    """After a signer pinned new leaf versions (`sign`, `sign-provisional`): file the acceptance each
    pin means as an attest by the tier's actor (s0fractal, agent) in the store, unsigned in Warrant
    terms, with the manifest and signature as blobs, and vouch for them with one migration@1 attest by
    `actor` (a `migrator` in .warrant/v3.json). `check` re-verifies each from its blobs; the voucher
    only makes the store's own assessment agree with the signatures (ADR-0033)."""
    from warrant import jcs as C
    from warrant import records as R
    from warrant.repo import Repo, load_key
    recs = pin.store_records(pin.ROOT)
    done = {(r["actor"], r["body"]["target"]) for r in recs.values() if r["kind"] == "attest"}
    at = int(time.time())
    attests, blobs = [], []
    for tier, m, s in tier_manifests(pin.SIGNERS):
        for rid, v in sorted(json.loads(m).get(pin.CONTRACTS, {}).items()):
            if (TIER_ACTOR[tier], v) in done:
                continue
            if recs.get(v, {}).get("body", {}).get("id") != rid:
                print(f"FAIL {rid}: the {tier} manifest pins {v[:12]}, which is not a version of {rid} in the store")
                return 1
            body = {"target": v, "verdict": "accept", "tier": tier, "carried": True,
                    "manifest": hashlib.sha256(m).hexdigest(), "signature": hashlib.sha256(s).hexdigest()}
            attests.append(R.record("attest", TIER_ACTOR[tier], at, body, refs=[v, body["manifest"], body["signature"]]))
            blobs += [m, s]
    if not attests:
        print("nothing to carry: every pinned leaf is accepted in the store")
        return 0
    repo = Repo(pin.ROOT)
    mapping = C.canon({"migration": "sokol-witness/carry@1", "map": [[R.rid(r), [r["body"]["manifest"], r["body"]["signature"]], []]
                                                                    for r in attests]})
    for data in blobs + [mapping]:
        repo.store.put_blob(data)
    repo.store.add_lines([R.line(r)[1] for r in attests])
    maph = hashlib.sha256(mapping).hexdigest()
    repo.file(actor, load_key(key, pin.ROOT), [R.record("attest", actor, at, {"target": maph, "verdict": "migrated",
                                                                          "records": len(attests)}, R.MIGRATION, refs=[maph])])
    print(f"carried {len(attests)} acceptance(s), vouched for by {actor}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=pathlib.Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--signers", type=pathlib.Path)
    c.add_argument("--every-pin", action="store_true")
    k = sub.add_parser("carry")
    k.add_argument("--actor", required=True)
    k.add_argument("--key", required=True)
    a = ap.parse_args(argv)
    if a.root:
        pin.configure_root(a.root)
    if a.cmd == "check":
        return check(a.signers or pin.SIGNERS, a.every_pin)
    return carry(a.actor, a.key)


if __name__ == "__main__":
    sys.exit(main())
