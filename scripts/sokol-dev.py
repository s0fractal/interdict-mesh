#!/usr/bin/env python3
"""One bounded entry point to Sokol's existing evidence tools.

challenge CASE; inventory/map/next.
A contract's witnesses run as cargo or unittest cases by name (its lineage in .warrant/records.jsonl).
No annotation, imported report or diagram supplies an executable command.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_VIEW_BYTES = 65_536
MAX_ROWS = 256


def module(name):
    spec = importlib.util.spec_from_file_location('sokol_dev_' + name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def inventory(signers=None):
    gate, inputs = module('witness-pin'), module('task_inputs')
    contracts = gate.load_contracts(ROOT)
    hashes = inputs.checkout(ROOT)
    trust = Path(signers).resolve() if signers else ROOT / '.github/witness-signers'
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        status = gate.check(trust, every_pin=True)
    owner = json.loads(inputs.read(ROOT / 'docs/witness-manifest.json'))
    agent_path = ROOT / 'docs/witness-provisional.json'
    agent = json.loads(inputs.read(agent_path)) if agent_path.exists() else {'witnesses': {}}
    locations = {**agent['witnesses'], **owner['witnesses']}
    rows = []
    for rid, c in sorted(contracts.items()):
        files = sorted({loc.rsplit(':', 1)[0] for w in c['witnesses'] for loc in locations.get(w, [])})
        rows.append({'id': rid, 'tier': 'PROVISIONAL' if gate.provisional(c) else 'OWNER',
                     'lifecycle': 'RETIRED' if gate.retired(c) else 'ACTIVE',
                     'witness_count': len(c['witnesses']), 'files': files,
                     'execution': 'UNKNOWN'})
    return {'profile': 'sokol.dev.inventory.v1', 'snapshot': 'sha256:' + inputs.digest(inputs.encode(hashes)),
            'binding': 'MATCH' if status == 0 else 'REFUSED',
            'gate': log.getvalue()[:8192], 'gate_output_partial': len(log.getvalue()) > 8192,
            'signer_provenance': 'CALLER_SUPPLIED' if signers else 'LOCAL_CHECKOUT',
            'signers_sha256': inputs.digest(inputs.read(trust)),
            'rows': rows, 'execution': 'UNKNOWN',
            'limits': ['Inventory is source/signature correspondence, not execution or semantic adequacy.',
                       'A provisional row is agent authority, not owner acceptance.']}


def graph(value):
    """Typed evidence edges only; physical modules are not an inferred call graph."""
    edges = []
    files = set()
    for row in value['rows']:
        for file in row['files']:
            files.add(file)
            edges.append({'from': row['id'], 'to': file, 'kind': 'DECLARES_WITNESS_IN'})
    return {'profile': 'sokol.dev.map.v1', 'snapshot': value['snapshot'], 'binding': value['binding'],
            'contracts': value['rows'], 'modules': sorted(files), 'edges': edges,
            'execution': 'UNKNOWN', 'limits': ['Evidence placement, not compiler-resolved dependencies or architectural proof.']}


def commands(action, identity=None):
    prefix = [sys.executable, '-I']
    if action == 'challenge':
        cases, _ = module('proof-task').catalog(ROOT)
        if identity not in {c['id'] for c in cases}:
            raise ValueError('Unknown fixed proof challenge; use next for the supported catalog')
        return prefix + [str(ROOT / 'scripts/proof-task.py'), 'run', '--challenge', identity]
    raise ValueError('Unsupported action')


def emit(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    if len(data) > MAX_VIEW_BYTES:
        raise ValueError('Essential view exceeds byte budget; select a contract context')
    print(data.decode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--signers', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('inventory', 'map', 'next'):
        sub.add_parser(name)
    sub.add_parser('challenge').add_argument('identity')
    args = parser.parse_args()
    try:
        if args.action in ('inventory', 'map', 'next'):
            value = inventory(args.signers)
            if args.action == 'map':
                value = graph(value)
            elif args.action == 'next':
                cases, _ = module('proof-task').catalog(ROOT)
                value = {'profile': 'sokol.dev.next.v1', 'snapshot': value['snapshot'],
                         'binding': value['binding'], 'gate': value['gate'],
                         'owner_actions': [r['id'] for r in value['rows'] if r['tier'] == 'PROVISIONAL'],
                         'proof_challenges': [c['id'] for c in cases],
                         'plan': 'docs/INDUSTRIAL.md', 'execution': 'UNKNOWN',
                         'limits': ['A task candidate is not authority to accept, sign or deploy it.']}
            emit(value)
            return 0 if value['binding'] == 'MATCH' else 1
        command = commands(args.action, args.identity)
        # Existing owners enforce their input/output/run bounds and record their own reports.
        return subprocess.call(command, cwd=ROOT)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, subprocess.SubprocessError) as error:
        emit({'status': 'REFUSED', 'execution': 'UNKNOWN', 'reason': str(error)})
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
