"""scripts/contract-store.py: the store agrees with the tiers' signatures (ADR-0033).

An acceptance `carry` files is a record anyone can write: it counts only when the manifest and the
SSH signature it names verify and pin exactly the version it accepts. The two refusals below are the
witnesses of a contract and run on the base gate, so they use the standard library and ssh-keygen
only; `test_the_migrated_store_passes` needs warrant-graph (CI).

    python3 scripts/test_contract_store.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ['scripts/witness-pin.py', 'scripts/contract-store.py', '.github/witness-signers',
         'docs/witness-manifest.json', 'docs/witness-manifest.json.sig', 'docs/INVARIANTS.md']
NOT_A_SIGNATURE = b'-----BEGIN SSH SIGNATURE-----\nnot one\n-----END SSH SIGNATURE-----\n'


class ContractStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name).resolve()
        self.root = base / 'repo'
        for name in FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copytree(ROOT / '.warrant', self.root / '.warrant')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        # An owner key of this fixture's own, trusted by a signers file of its own: the real keys
        # never enter a test, and what the fixture signs is all that can verify.
        self.key = base / 'owner'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'fixture owner', '-f', str(self.key)],
                       check=True, stdin=subprocess.DEVNULL)
        self.signers = base / 'signers'
        self.signers.write_text('owner namespaces="sokol-witness" ' + (base / 'owner.pub').read_text())

    def tearDown(self):
        self.temp.cleanup()

    def run_store(self, *args):
        return subprocess.run([sys.executable, 'scripts/contract-store.py', *args], cwd=self.root,
                              capture_output=True, text=True, timeout=120)

    def store(self):
        spec = importlib.util.spec_from_file_location('contract_store', self.root / 'scripts/contract-store.py')
        store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(store)
        store.pin.configure_root(self.root)
        return store

    def sign(self, manifest):
        """The fixture owner's SSH signature over these manifest bytes."""
        path = self.key.with_name('manifest')
        path.write_bytes(manifest)
        subprocess.run(['ssh-keygen', '-q', '-Y', 'sign', '-f', str(self.key), '-n', 'sokol-witness', str(path)],
                       check=True, stdin=subprocess.DEVNULL)
        signature = path.with_name('manifest.sig')
        data = signature.read_bytes()
        signature.unlink()
        return data

    def carry(self, target, manifest, signature):
        """An owner acceptance of `target` as `carry` files it: the attest line and its two blobs. Its id."""
        store = self.store()
        names = []
        for data in (manifest, signature):
            name = hashlib.sha256(data).hexdigest()
            (self.root / '.warrant/blobs' / name).write_bytes(data)
            names.append(name)
        body = {'target': target, 'verdict': 'accept', 'tier': 'owner', 'carried': True,
                'manifest': names[0], 'signature': names[1]}
        record = {'warrant': '3', 'kind': 'attest', 'actor': 's0fractal', 'at': 1800000000, 'prev': None,
                  'schema': None, 'lineage': None, 'refs': [names[0], names[1], target], 'guard': None, 'body': body}
        with (self.root / '.warrant/records.jsonl').open('a') as lines:
            lines.write(json.dumps({'record': record, 'sig': None}, sort_keys=True) + '\n')
        return store.pin.record_id(record)

    def refusals(self, acceptance):
        """What carried_problems says about one acceptance, under the fixture's signers."""
        return [p for p in self.store().carried_problems(self.signers) if p.startswith('acceptance ' + acceptance[:12])]

    def refused(self, acceptance):
        return [f'acceptance {acceptance[:12]} by s0fractal: no owner signature under {self.signers.name} pins its version']

    def test_the_migrated_store_passes(self):
        r = self.run_store('check')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f'{len(self.store().pin.load_contracts(self.root))} contract lineages', r.stdout)

    def test_a_carried_acceptance_without_a_verifying_signature_is_refused(self):
        # One manifest pinning the leaf, carried twice: only the signature tells the two apart.
        leaf = self.store().pin.load_contracts(self.root)['IPC-A1']['version']
        manifest = json.dumps({'contracts_v2': {'IPC-A1': leaf}}).encode()
        signed = self.carry(leaf, manifest, self.sign(manifest))
        forged = self.carry(leaf, manifest, NOT_A_SIGNATURE)
        self.assertEqual(self.refusals(signed), [])
        self.assertEqual(self.refusals(forged), self.refused(forged))

    def test_a_real_signature_over_a_manifest_that_pins_another_version_is_refused(self):
        # A verifying signature over a manifest that pins a contract's leaf accepts that leaf, and not
        # the earlier version some later version replaced: a signature accepts nothing it does not name.
        store = self.store()
        records = store.pin.store_records(self.root)
        earlier = sorted(r['lineage'] for r in records.values() if r.get('schema') == store.pin.SCHEMA and r['lineage'])[0]
        rid = records[earlier]['body']['id']
        leaf = store.pin.load_contracts(self.root)[rid]['version']
        manifest = json.dumps({'contracts_v2': {rid: leaf}}).encode()
        signature = self.sign(manifest)
        named = self.carry(leaf, manifest, signature)
        other = self.carry(earlier, manifest, signature)
        self.assertEqual(self.refusals(named), [])
        self.assertEqual(self.refusals(other), self.refused(other))


if __name__ == '__main__':
    unittest.main()
