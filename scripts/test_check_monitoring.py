"""scripts/check-monitoring.sh: the alert rules and the dashboard select series the node exports.

The check compared metric names only. A label value an alert selects on
(`interdict_xdp_mode{mode="generic"}`, `interdict_mesh_broadcasts_dropped_total{class="urgent"}`)
could be renamed in the exporter and the check, the metrics tests and promtool's own rule
tests (which feed synthetic series) all stayed green, while the alert could never fire.

    python3 scripts/test_check_monitoring.py
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    'scripts/check-monitoring.sh',
    'deploy/prometheus/interdict-alerts.yml',
    'deploy/grafana/interdict-dashboard.json',
    'orchestrator/src/metrics.rs',
    'orchestrator/src/detections.rs',
    'orchestrator/src/p2p.rs',
    'orchestrator/src/block_table.rs',
    'common/src/lib.rs',
]


class Monitoring(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        for f in FILES:
            (self.dir / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, self.dir / f)

    def mutate(self, rel, old, new):
        path = self.dir / rel
        text = path.read_text()
        self.assertIn(old, text, f'mutation anchor missing in {rel}')
        path.write_text(text.replace(old, new))

    def run_check(self):
        return subprocess.run([str(self.dir / 'scripts/check-monitoring.sh')],
                              capture_output=True, text=True)

    def test_the_repository_passes(self):
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_renamed_metric_fails(self):
        self.mutate('orchestrator/src/metrics.rs', 'interdict_claims_waiting', 'interdict_claims_queued')
        self.assertNotEqual(self.run_check().returncode, 0)

    def test_a_renamed_label_value_an_alert_selects_fails(self):
        for rel, old, new in [
            ('orchestrator/src/metrics.rs', '{ "native" } else { "generic" }',
             '{ "native" } else { "skb" }'),
            ('orchestrator/src/metrics.rs', 'class=\\"urgent\\"', 'class=\\"decision\\"'),
            ('orchestrator/src/detections.rs', '"enforced", "pending"', '"enforced", "queued"'),
        ]:
            with self.subTest(new):
                self.setUp()
                self.mutate(rel, old, new)
                r = self.run_check()
                self.assertNotEqual(
                    r.returncode, 0,
                    f'{old} -> {new}: an alert now selects a series nobody exports, '
                    f'and the check passed: {r.stdout.strip()}')

    def test_a_test_only_item_before_the_labels_does_not_end_the_scan(self):
        # 0e6f15f put test-only constants under a top-level #[cfg(test)] above the label literals;
        # a scan that stopped at the first such attribute missed every label after it.
        self.mutate('orchestrator/src/metrics.rs', 'use std::fmt::Write;\n',
                    'use std::fmt::Write;\n\n#[cfg(test)]\nconst FIXTURE_ONLY: u8 = 0;\n')
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_label_value_rendered_only_in_the_test_module_fails(self):
        self.mutate('orchestrator/src/metrics.rs', '{ "native" } else { "generic" }', '{ "native" } else { "skb" }')
        self.mutate('orchestrator/src/metrics.rs', '#[cfg(test)]\nmod tests {\n',
                    '#[cfg(test)]\nmod tests {\n    const RENDERED_ONLY_HERE: &str = "generic";\n')
        r = self.run_check()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('label value "generic" is selected but not rendered', r.stdout)


if __name__ == '__main__':
    unittest.main()
