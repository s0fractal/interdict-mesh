"""scripts/contract-store.py: the store agrees with the tiers' signatures (ADR-0033).

An acceptance `carry` files is a record anyone can write: it counts only when the manifest and the
SSH signature it names verify and pin exactly the version it accepts. Needs warrant-graph (CI).

    python3 scripts/test_contract_store.py
"""
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


class ContractStore(unittest.TestCase):
    def setUp(self):
        from warrant import keys as K
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copytree(ROOT / '.warrant', self.root / '.warrant')
        # A migrator of this fixture's own: the real seeds never enter a test.
        self.key = K.Key.generate()
        (self.root.parent / (self.root.name + '.seed')).write_text(self.key.seed_hex())
        v3 = json.loads((self.root / '.warrant/v3.json').read_text())
        v3['trust']['keys']['claude'] = sorted(v3['trust']['keys']['claude'] + [self.key.public])
        (self.root / '.warrant/v3.json').write_text(json.dumps(v3))
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def tearDown(self):
        (self.root.parent / (self.root.name + '.seed')).unlink(missing_ok=True)
        self.temp.cleanup()

    def run_store(self, *args):
        return subprocess.run([sys.executable, 'scripts/contract-store.py', *args], cwd=self.root,
                              capture_output=True, text=True, timeout=120)

    def pin(self):
        spec = importlib.util.spec_from_file_location('wp', self.root / 'scripts/witness-pin.py')
        pin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pin)
        pin.configure_root(self.root)
        return pin

    def leaf(self):
        return self.pin().load_contracts(self.root)['IPC-A1']['version']

    def forge(self, manifest, signature, earlier=False):
        """An owner acceptance carried with the given manifest and signature bytes, vouched for by the
        fixture's migrator: of IPC-A1's leaf, or of a version some later version replaced."""
        from warrant import records as R
        from warrant.repo import Repo
        pin = self.pin()
        leaf = self.leaf()
        if earlier:
            leaf = sorted(r['lineage'] for r in pin.store_records(self.root).values() if r.get('lineage'))[0]
        repo = Repo(self.root)
        m, s = repo.store.put_blob(manifest), repo.store.put_blob(signature)
        body = {'target': leaf, 'verdict': 'accept', 'tier': 'owner', 'carried': True, 'manifest': m, 'signature': s}
        r = R.record('attest', 's0fractal', 1800000000, body, refs=[leaf, m, s])
        repo.store.add_lines([R.line(r)[1]])
        mapping = json.dumps({'map': [[R.rid(r), [m, s], []]]}).encode()
        h = repo.store.put_blob(mapping)
        repo.file('claude', self.key, [R.record('attest', 'claude', 0, {'target': h, 'verdict': 'migrated', 'records': 1},
                                                 R.MIGRATION, refs=[h])])

    def test_the_migrated_store_passes(self):
        r = self.run_store('check')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('80 contract lineages', r.stdout)

    def test_a_carried_acceptance_without_a_verifying_signature_is_refused(self):
        # A manifest that does pin the leaf, so only the signature can refuse it.
        doc = json.loads((self.root / 'docs/witness-manifest.json').read_text())
        doc.setdefault('contracts_v2', {})['IPC-A1'] = self.leaf()
        self.forge(json.dumps(doc).encode(), b'-----BEGIN SSH SIGNATURE-----\nnot one\n-----END SSH SIGNATURE-----\n')
        r = self.run_store('check')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('by s0fractal: no owner signature under witness-signers pins its version', r.stdout)

    def test_a_real_signature_over_a_manifest_that_pins_another_version_is_refused(self):
        # The owner's current signature verifies, but its manifest pins each contract's leaf, not the
        # earlier version accepted here: a valid signature accepts nothing it does not name.
        self.forge((self.root / 'docs/witness-manifest.json').read_bytes(),
                   (self.root / 'docs/witness-manifest.json.sig').read_bytes(), earlier=True)
        r = self.run_store('check')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('by s0fractal: no owner signature', r.stdout)

if __name__ == '__main__':
    unittest.main()
