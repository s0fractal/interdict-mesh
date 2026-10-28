#!/usr/bin/env python3
"""Bounded inputs for the evidence tools (proof-task.py, counterexample-task.py, sokol-dev.py).

Bounded reads, a bounded process runner, the tracked-file inventory and its hash-checked private
copy, and `prepare`: a contract's context packet from its lineage in .warrant/records.jsonl, bound
to the owner's signed manifest. Kept from scripts/contract-task.py when its own command line (context,
run, verify reports) was removed (ADR-0033). Nothing here accepts, signs or declares a statement proved.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 2_097_152
MAX_FILES = 4096
MAX_CHECKOUT_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 1_048_576
MAX_PACKET_BYTES = 16_384
RUN_TIMEOUT = 900
RECIPES = {
    'delivery': ['bash', 'scripts/check-delivery.sh'],
    'orchestrator-unit': ['cargo', 'test', '--release', '--locked', '-p', 'orchestrator', '--bins', '{witness}', '--', '--color', 'never'],
    'workspace-unit': ['cargo', 'test', '--release', '--locked', '-p', 'orchestrator', '-p', 'common', '--lib', '--bins', '{witness}', '--', '--color', 'never'],
    'common-unit': ['cargo', 'test', '--release', '--locked', '-p', 'common', '--lib', '{witness}', '--', '--color', 'never'],
}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path, bound=MAX_FILE_BYTES):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink input refused: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(bound + 1)
    if len(data) > bound:
        raise ValueError('Input exceeds byte bound: ' + str(path))
    return data


def run_bounded(root, command, timeout=RUN_TIMEOUT, bound=MAX_OUTPUT_BYTES, env=None):
    """Retain at most bound+1 bytes; signal the process group and reap the direct child."""
    process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True, env=env)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('Verifier exceeded time bound')
                if not selector.select(min(remaining, 1)):
                    continue
                data = os.read(process.stdout.fileno(), min(65536, bound + 1 - len(output)))
                if not data:
                    selector.unregister(process.stdout)
                    continue
                output.extend(data)
                if len(output) > bound:
                    raise ValueError('Verifier exceeded output bound')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Verifier exceeded time bound')
        return process.wait(timeout=remaining), bytes(output)
    finally:
        # End this verifier's process group, also on a normal exit. Children that created
        # a separate session are outside this cancellation mechanism.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()


def checkout(root):
    status, data = run_bounded(root, ['git', 'ls-files', '-z'], timeout=10)
    if status:
        raise ValueError('Cannot enumerate checkout')
    names = sorted(set(x.decode('utf-8') for x in data.split(b'\0') if x))
    if len(names) > MAX_FILES:
        raise ValueError('Checkout exceeds file count bound')
    hashes, size = {}, 0
    for name in names:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or '.git' in path.parts:
            raise ValueError('Invalid checkout path')
        value = read(root / path)
        size += len(value)
        if size > MAX_CHECKOUT_BYTES:
            raise ValueError('Checkout exceeds aggregate byte bound')
        hashes[name] = {'sha256': digest(value), 'executable': bool((root / path).stat().st_mode & 0o111)}
    return hashes


@contextmanager
def copied_inputs(root, inputs):
    """Freeze exactly the inventoried bytes/modes, then verify this private copy again."""
    with tempfile.TemporaryDirectory(prefix='sokol-witness-inputs-') as directory:
        work = Path(directory).resolve()
        for name, expected in inputs.items():
            source = root / name
            value = read(source)
            executable = bool(source.stat().st_mode & 0o111)
            if digest(value) != expected['sha256'] or executable != expected['executable']:
                raise ValueError('Inputs moved while copying verifier snapshot')
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
            target.chmod(0o755 if executable else 0o644)
        for command in (['git', 'init', '-q'], ['git', 'add', '-f', '--', *inputs]):
            status, _ = run_bounded(work, command, timeout=10)
            if status:
                raise ValueError('Cannot index verifier snapshot')
        yield work


def checker(root):
    spec = importlib.util.spec_from_file_location('task_inputs_pin', root / 'scripts/witness-pin.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration():
    # Other environment and generated/untracked inputs are outside the declared closure.
    keys = ('SOKOL_GOBGP_TEST_BIN', 'CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR',
            'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS',
            'RUSTUP_TOOLCHAIN', 'CARGO_HOME', 'RUSTUP_HOME', 'PATH', 'SOKOL_BUILD_ID',
            'RUSTC', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUST_TEST_THREADS',
            'RUST_TEST_NOCAPTURE', 'PROPTEST_CASES', 'PROPTEST_RNG_SEED', 'PROPTEST_RNG_ALGORITHM')
    return {'system': platform.system(), 'machine': platform.machine(),
            'environment_sha256': {k: digest(os.environ.get(k, '').encode()) for k in keys}}


def prepare(root, rid, signers=None):
    """The context of one contract: its leaf version in the store, its witnesses' bodies and whether they
    and the leaf are what the owner pinned (MATCH) or the row is not the owner's (UNPINNED)."""
    pin = checker(root)
    if not isinstance(rid, str) or not pin.CONTRACT_ID.fullmatch(rid):
        raise ValueError('Invalid contract ID')
    hashes = checkout(root)
    contract = pin.load_contracts(root).get(rid)
    source = '.warrant/records.jsonl'
    if not contract:
        raise ValueError('Unknown contract')
    if source not in hashes:
        raise ValueError('Stage the store before making a reproducible context')
    trust = Path(signers).resolve() if signers else root / '.github/witness-signers'
    trust_bytes = read(trust)
    manifest_bytes = read(root / 'docs/witness-manifest.json')
    signature_bytes = read(root / 'docs/witness-manifest.json.sig')
    for name, value in [('docs/witness-manifest.json', manifest_bytes),
                        ('docs/witness-manifest.json.sig', signature_bytes)]:
        if hashes.get(name, {}).get('sha256') != digest(value):
            raise ValueError('Signed inputs moved during projection')
    # Verify exactly the declared bytes, also for an external signer file. A moving
    # path cannot make a signature valid under a different, transient trust file.
    with tempfile.TemporaryDirectory(prefix='sokol-contract-signature-') as directory:
        paths = [Path(directory) / name for name in ('manifest', 'signature', 'signers')]
        for path, data in zip(paths, (manifest_bytes, signature_bytes, trust_bytes)):
            path.write_bytes(data)
        if not pin.verify_manifest(*paths):
            raise ValueError('Owner signature verification failed')
    # Use exactly the gate's public current representation. It also validates the generated
    # projection; no row or hash implementation lives here.
    current_rows = pin.rows()
    current_contracts = pin.contract_pins(root)
    manifest = json.loads(manifest_bytes)
    witnesses = contract['witnesses']
    if not isinstance(witnesses, list) or not witnesses or len(witnesses) > 256:
        raise ValueError('Invalid witness set')
    body_locations = {}
    rust = {w for w in witnesses if pin.RUST_TEST.fullmatch(w)}
    candidate = re.compile(r'\bfn\s+(?:' + '|'.join(re.escape(w) for w in sorted(rust)) + r')\s*[(<]') if rust else None
    for name in hashes:
        if name.endswith('.rs') and candidate:
            text = read(root / name).decode()
            if not candidate.search(text):
                continue
            found = pin.rust_witness_hashes(text, name, rust)
            for witness, locations in found.items():
                body_locations.setdefault(witness, []).extend(locations)
    python = pin.py_bodies({w for w in witnesses if pin.PY_TEST.fullmatch(w)}) if any(
        pin.PY_TEST.fullmatch(w) for w in witnesses) else {}
    for witness in witnesses:
        if pin.PY_TEST.fullmatch(witness):
            body_locations[witness] = python.get(witness, [])
        if not body_locations.get(witness):
            raise ValueError('Missing witness body: ' + witness)
    correspondence = 'UNPINNED'
    if rid in manifest.get(pin.ROWS, {}):
        if current_rows[rid] != manifest[pin.ROWS][rid] or any(
                sorted(body_locations[w]) != manifest['witnesses'].get(w) for w in witnesses):
            raise ValueError('Selected contract or witness differs from owner pin')
        if current_contracts.get(rid) != manifest.get(pin.CONTRACTS, {}).get(rid):
            raise ValueError('Selected contract history differs from owner pin')
        correspondence = 'MATCH'
    files = sorted({location.rsplit(':', 1)[0] for v in body_locations.values() for location in v})
    if all(file == 'orchestrator/src/delivery.rs' for file in files):
        recipe = 'delivery'
    elif all(file.startswith('orchestrator/src/') for file in files) and not any('.' in w for w in witnesses):
        recipe = 'orchestrator-unit'
    elif all(file.startswith('common/src/') for file in files) and not any('.' in w for w in witnesses):
        recipe = 'common-unit'
    elif all(file.startswith(('orchestrator/src/', 'common/src/')) for file in files) and not any('.' in w for w in witnesses):
        recipe = 'workspace-unit'
    else:
        recipe = None
    config = configuration()
    body = {'profile': 'sokol.agent.contract-task.v1', 'contract_id': rid, 'source': source,
            'version': contract['version'],
            'statement': contract['statement'], 'witnesses': witnesses, 'witness_files': files,
            'binding': {'owner_signature': 'VERIFIED_AGAINST_SUPPLIED_SIGNERS',
                        'signers_sha256': digest(trust_bytes),
                        'signer_provenance': 'CALLER_SUPPLIED' if signers else 'LOCAL_CHECKOUT',
                        'correspondence': correspondence,
                        'annotations': 'UNSIGNED', 'proposal_acceptance': 'NOT_ESTABLISHED'},
            'snapshot': 'sha256:' + digest(encode(hashes)), 'tracked_files': len(hashes),
            'configuration': config, 'recipe': recipe, 'command': RECIPES.get(recipe),
            'execution': 'UNKNOWN', 'semantic_adequacy': 'NOT_ESTABLISHED',
            'execution_policy': 'REVALIDATE_AND_RUN_HASH_CHECKED_PRIVATE_TRACKED_COPY',
            'edit_rule': 'Fixes start with an assertion-red counterexample. Preserve pinned witnesses; changing a boundary requires an owner proposal and signature.',
            'unknowns': ['Helper completeness and untracked/generated/external inputs are not established.',
                         'A matching signed body does not prove its statement or a kernel/remote effect.',
                         'Recorded reports are unsigned and untrusted; offline verification does not establish execution.',
                         'Execution covers named unit witnesses; Kani, full CI and deployment qualification remain separate.']}
    body['cargo_cache_policy'] = 'SNAPSHOT_CONFIGURATION_NAMESPACE_OR_PRIVATE_TARGET'
    packet = {'id': 'sha256:' + digest(encode(body)), 'body': body}
    if len(encode(packet)) > MAX_PACKET_BYTES:
        raise ValueError('Essential context exceeds packet bound')
    if checkout(root) != hashes or read(trust) != trust_bytes or configuration() != config:
        raise ValueError('Inputs moved during context generation')
    return packet, hashes


