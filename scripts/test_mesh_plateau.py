"""The soak plateau (ADR-0031 rule 5b) passes only on observed samples: an RSS, fd count or
state file the sampler could not read is no measurement, never a zero that levels (Codex
finding d398137c on #76). Replays the sampler and the verdict of bench/mesh.sh as they are,
with /proc of three nodes and `stat -c %s` as fixtures, so it runs on Linux and macOS."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'bench/mesh.sh').read_text()


def block(start_marker, end_marker, after=None):
    start = SOURCE.index(start_marker, SOURCE.index(after) if after else 0)
    return SOURCE[start:SOURCE.index(end_marker, start)]


SAMPLE = block('    sample() {', '\n    fail=0', after='soak)\n')
VERDICT = block('    if [ "${SOAK_PLATEAU:-0}" = 1 ]; then', '\n    echo "samples: $CSV"')


class Plateau(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ['rm', '-rf', str(self.work)])
        self.proc = self.work / 'proc'
        for node in range(1, 4):
            p = self.proc / str(node)
            (p / 'fd').mkdir(parents=True)
            for fd in range(27):
                (p / 'fd' / str(fd)).touch()
            (p / 'stat').write_text(f'{node} (orchestrator) S\n')
            (p / 'status').write_text('VmRSS:\t50000 kB\n')
            (self.work / f'n{node}').mkdir()
            (self.work / f'n{node}/audit.log.blocks.json').write_bytes(b'x' * 4096)
        helpers = self.work / 'bin'
        helpers.mkdir()
        (helpers / 'stat').write_text(f'#!{sys.executable}\nimport os, sys\n'
            'try: print(os.stat(sys.argv[-1]).st_size)\nexcept OSError: sys.exit(1)\n')
        (helpers / 'stat').chmod(0o755)
        self.path = str(helpers) + os.pathsep + os.environ['PATH']

    def replay(self, csv=None):
        if csv is not None:
            (self.work / 'soak.csv').write_text(csv)
        sampled = ('\necho t_s,node,rss_kb,fds,audit_bytes,state_bytes,blocks_active,blocks_pending,tick_max_s,peers > "$CSV"\n'
            'for k in $(seq 0 29); do sample $((1320 + k * 60)); done\n') if csv is None else '\n'
        shell = ('set -eu\nN=3\nNODE_PID=(0 1 2 3)\nDIED=()\nfail=0\nrestarts=0\n'
            "bases='1:28000 2:28000 3:28000'\nTTL=180\nTTL_MAX=720\nSOAK_PLATEAU=1\n"
            'SOAK_RSS_BOUND_KB=536345\nSOAK_STATE_CEILING_BYTES=239039621\nmetric() { echo 0; }\n'
            + SAMPLE.replace('/proc/', f'{self.proc}/') + sampled + VERDICT + '\nexit "$fail"\n')
        return subprocess.run(['bash', '-c', shell], capture_output=True, text=True, timeout=60,
            env={**os.environ, 'PATH': self.path, 'WORK': str(self.work), 'CSV': str(self.work / 'soak.csv')})

    def test_observed_level_samples_pass(self):
        result = self.replay()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS plateau', result.stdout)

    def test_an_unobserved_sample_fails_the_plateau(self):
        unread = {  # what, its soak.csv column, how the read fails
            'state file': (5, lambda node: (self.work / f'n{node}/audit.log.blocks.json').unlink()),
            'RSS': (2, lambda node: (self.proc / str(node) / 'status').unlink()),
            'fds': (3, lambda node: [fd.unlink() for fd in (self.proc / str(node) / 'fd').iterdir()]),
        }
        for what, (column, remove) in unread.items():
            with self.subTest(what):
                self.setUp()
                for node in range(1, 4):
                    remove(node)
                result = self.replay()
                self.assertNotEqual(result.returncode, 0, f'{what} never read, plateau passed:\n{result.stdout}')
                self.assertIn(f'{what} not observed', result.stdout)
                self.assertNotIn('PASS plateau', result.stdout)
                rows = (self.work / 'soak.csv').read_text().splitlines()[1:]
                self.assertEqual({row.split(',')[column] for row in rows}, {''}, f'{what} not read is sampled as a value')

    def test_a_zero_sample_fails_the_plateau(self):
        # By t = 1 320 s a node holds memory, open files and a state file with the saturation's
        # event ids: a zero there is a failed read, not a level.
        for what, column in (('RSS', 2), ('fds', 3), ('state file', 5)):
            with self.subTest(what):
                rows = []
                for k in range(30):
                    for node in range(1, 4):
                        row = [str(1320 + k * 60), str(node), '50000', '27', '0', '4096', '0', '0', '0', '2']
                        if node == 2:
                            row[column] = '0'
                        rows.append(','.join(row))
                result = self.replay('t_s,node\n' + '\n'.join(rows) + '\n')
                self.assertNotEqual(result.returncode, 0, f'{what} 0, plateau passed:\n{result.stdout}')
                self.assertIn(f'node 2 {what} not observed', result.stdout)


if __name__ == '__main__': unittest.main()
