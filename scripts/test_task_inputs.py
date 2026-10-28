"""scripts/task_inputs.py: bounded inputs, and a contract context that matches only the owner's pins.

    python3 scripts/test_task_inputs.py
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('task_inputs', ROOT / 'scripts/task_inputs.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class TaskInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        sources = ['scripts/witness-pin.py', 'scripts/task_inputs.py', 'docs/INVARIANTS.md',
                   'docs/witness-manifest.json', 'docs/witness-manifest.json.sig', '.github/witness-signers',
                   '.warrant/records.jsonl', '.warrant/v3.json']
        # Every Rust source: a witness may live in any module.
        sources += subprocess.run(['git', 'ls-files', '*.rs'], cwd=ROOT, capture_output=True,
                                  text=True, check=True).stdout.split()
        for name in sources:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def context(self):
        return tool.prepare(self.root, 'IPC-A1')

    def test_context_names_the_leaf_version_and_never_claims_execution(self):
        packet, _ = self.context()
        body = packet['body']
        self.assertEqual(body['source'], '.warrant/records.jsonl')
        self.assertRegex(body['version'], r'\A[0-9a-f]{64}\Z')
        self.assertEqual(body['execution'], 'UNKNOWN')
        self.assertEqual(packet, self.context()[0])

    def test_changed_witness_is_refused_but_helper_change_only_changes_snapshot(self):
        first, _ = self.context()
        source = self.root / 'orchestrator/src/delivery.rs'
        source.write_text(source.read_text() + '\nfn unsigned_helper() {}\n')
        second, _ = self.context()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['body']['binding']['correspondence'], first['body']['binding']['correspondence'])
        source.write_text(source.read_text().replace('fn an_unterminated_ack_does_not_retire_the_signal()',
                                                  'fn dropped_pinned_witness()'))
        with self.assertRaisesRegex(ValueError, 'Missing witness body'):
            self.context()

    def test_symlink_and_oversized_inputs_fail_before_projection(self):
        source = self.root / 'orchestrator/src/delivery.rs'
        source.unlink()
        source.symlink_to(ROOT / 'orchestrator/src/delivery.rs')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.context()
        source.unlink()
        source.write_bytes(b'x' * (tool.MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'byte bound'):
            self.context()

    def test_an_unknown_contract_and_a_bad_id_are_refused(self):
        for rid in ('NOPE-X9', '../IPC-A1', 'ipc-a1'):
            with self.assertRaises(ValueError):
                tool.prepare(self.root, rid)

    def test_executable_mode_changes_the_inventory(self):
        before = tool.checkout(self.root)
        (self.root / 'orchestrator/src/delivery.rs').chmod(0o755)
        self.assertNotEqual(before, tool.checkout(self.root))

    def test_process_output_bound_accepts_equality_refuses_overflow_and_reaps(self):
        command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(b"x" * 32)']
        self.assertEqual(tool.run_bounded(self.root, command, bound=32), (0, b'x' * 32))
        pid_file = self.root / 'overflow.pid'
        code = 'import os,time; from pathlib import Path; Path("overflow.pid").write_text(str(os.getpid())); os.write(1,b"x"*33); time.sleep(60)'
        with self.assertRaisesRegex(ValueError, 'output bound'):
            tool.run_bounded(self.root, [sys.executable, '-c', code], bound=32)
        pid = int(pid_file.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_a_silent_or_pipe_closed_process_still_has_a_deadline(self):
        for code in ('import time; time.sleep(60)', 'import os,time; os.close(1); os.close(2); time.sleep(60)'):
            start = time.monotonic()
            with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                tool.run_bounded(self.root, [sys.executable, '-c', code], timeout=.1)
            self.assertLess(time.monotonic() - start, 2)


if __name__ == '__main__':
    unittest.main()
