"""scripts/campaign.py: the VM's own maintenance is stopped before a campaign (ADR-0031 rule 5).

The 2026-10-20 campaign on candidate 776861e was cut at 6.47 h by apt-daily-upgrade.timer
restarting the node under test (needrestart). Each case replaces systemctl with a recorder.

    python3 scripts/test_campaign.py
"""
import importlib.util
from pathlib import Path
import re
import subprocess
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('campaign', HERE / 'campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)
MESH = (HERE.parent / 'bench/mesh.sh').read_text()


def rust_constants():
    """The bounds as the code states them: `pub const NAME: usize = <expr>;` in block_table.rs,
    with BLOCKLIST_CAPACITY from common and FORGET_GRACE in seconds."""
    common = (HERE.parent / 'common/src/lib.rs').read_text()
    table = (HERE.parent / 'orchestrator/src/block_table.rs').read_text()
    names = {'BLOCKLIST_CAPACITY': int(re.search(r'pub const BLOCKLIST_CAPACITY: u32 = ([\d_]+);', common).group(1))}
    for name, expr in re.findall(r'^pub const (MAX_\w+): usize = ([^;]+);', table, re.M):
        # Literals (Python reads 65_536 too), names of earlier constants and products only.
        names[name] = eval(expr.replace('common::', '').replace(' as usize', ''), {'__builtins__': {}}, dict(names))
    names['FORGET_GRACE_SECS'] = int(re.search(r'pub const FORGET_GRACE: Duration = Duration::from_secs\((\d+)\);', table).group(1))
    return names


class Systemctl:
    """Answers `systemctl cat|stop|mask|is-enabled UNIT` for a set of known units."""

    def __init__(self, known, failing=()):
        self.known, self.failing, self.calls = set(known), set(failing), []

    def __call__(self, argv, **_):
        verb, unit = argv[1], argv[2]
        self.calls.append((verb, unit))
        code = 0 if unit in self.known and (verb, unit) not in self.failing else 1
        out = 'masked\n' if verb == 'is-enabled' and ('mask', unit) in self.calls else ''
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr='')


class QuietHost(unittest.TestCase):
    def test_every_known_maintenance_unit_is_stopped_and_masked(self):
        fake = Systemctl(campaign.QUIET)
        with mock.patch.object(campaign.subprocess, 'run', fake):
            done = campaign.quiet_host()
        self.assertEqual(done, {unit: 'masked' for unit in campaign.QUIET})
        for unit in campaign.QUIET:
            self.assertLess(fake.calls.index(('stop', unit)), fake.calls.index(('mask', unit)))

    def test_an_absent_unit_is_recorded_not_touched(self):
        fake = Systemctl({'apt-daily.timer'})
        with mock.patch.object(campaign.subprocess, 'run', fake):
            done = campaign.quiet_host()
        self.assertEqual(done['unattended-upgrades.service'], 'absent')
        self.assertNotIn(('mask', 'unattended-upgrades.service'), fake.calls)

    def test_a_unit_that_cannot_be_masked_refuses_the_campaign(self):
        fake = Systemctl(campaign.QUIET, failing={('mask', 'apt-daily-upgrade.timer')})
        with mock.patch.object(campaign.subprocess, 'run', fake):
            with self.assertRaises(SystemExit):
                campaign.quiet_host()


class Profiles(unittest.TestCase):
    def test_rc1_judges_a_plateau_only_in_a_phase_without_restarts(self):
        chaos, plateau = campaign.PROFILES['rc1']
        self.assertNotIn('SOAK_PLATEAU', chaos['env'])
        self.assertEqual(plateau['env']['SOAK_PLATEAU'], '1')
        self.assertGreater(int(plateau['env']['RESTART_EVERY']), plateau['minutes'] * 60)

    def test_rc1_blocks_outlive_the_settle_so_the_final_agreement_is_not_on_an_empty_table(self):
        # bench/mesh.sh soak settles 90 s, then looks for agreement for up to 30 s.
        for phase in campaign.PROFILES['rc1']:
            self.assertGreater(int(phase['env']['TTL']), 90 + 30, phase['name'])

    def test_the_plateau_drives_the_event_memory_past_its_bound(self):
        # The event memory keeps every new event id 24 h, up to MAX_EVENTS: at the soak's 5
        # signals/s on 3 nodes it fills in about 11 h, so the plateau saturates it first, and the
        # bench checks every node evicted.
        env = campaign.PROFILES['rc1'][1]['env']
        self.assertGreater(int(env['SOAK_SATURATE']), rust_constants()['MAX_EVENTS'])

    def test_the_plateau_is_judged_after_every_record_can_be_forgotten_with_six_samples_a_third(self):
        # bench/mesh.sh judges from max(TTL, TTL_MAX) + FORGET_GRACE on, one sample a minute.
        plateau = campaign.PROFILES['rc1'][1]
        env = plateau['env']
        self.assertEqual(int(re.search(r'FORGET_GRACE_S=(\d+)', MESH).group(1)), rust_constants()['FORGET_GRACE_SECS'])
        settled = max(int(env['TTL']), int(env['TTL_MAX'])) + rust_constants()['FORGET_GRACE_SECS']
        self.assertGreaterEqual((plateau['minutes'] * 60 - settled) // 60, 3 * 6)
        # The cycled targets are all signalled several times before the judged window begins.
        self.assertLess(int(env['SOAK_DISTINCT']) / 5 * 3, settled)

    def test_the_measurement_was_taken_at_the_bounds_the_code_has(self):
        self.assertEqual(campaign.MEMORY['bounds'], {k: rust_constants()[k] for k in campaign.MEMORY['bounds']})

    def test_the_plateau_ceilings_are_the_measured_bounds_plus_each_peers_replay_memory(self):
        env, memory = campaign.PROFILES['rc1'][1]['env'], campaign.MEMORY
        peers = campaign.NODES - 1
        self.assertGreaterEqual(int(env['SOAK_RSS_BOUND_KB']) * 1024,
                                memory['all_bounds']['rss_kb'] * 1024 + peers * memory['replay_guard_bytes_per_peer'])
        self.assertLess(int(env['SOAK_RSS_BOUND_KB']) - 1, memory['all_bounds']['rss_kb'] + peers * memory['replay_guard_bytes_per_peer'] / 1024)
        floors = memory['bounds']['MAX_MESH_FLOORS'] * memory['state_bytes_per_entry']['mesh floor']
        self.assertEqual(int(env['SOAK_STATE_CEILING_BYTES']), memory['all_bounds']['state_bytes'] + floors)

    def test_long_keeps_the_24_and_72_hour_phases(self):
        self.assertEqual([p['minutes'] for p in campaign.PROFILES['long']], [24 * 60, 72 * 60])


class Plan(unittest.TestCase):
    def test_the_worker_runs_the_profile_the_receipt_names(self):
        receipt = {'campaign': 'rc1', 'plan': campaign.PROFILES['rc1']}
        self.assertIs(campaign.plan_of(receipt), campaign.PROFILES['rc1'])

    def test_an_edited_plan_in_the_receipt_is_refused_not_run(self):
        edited = [dict(step, env={**step['env'], 'BENCH_OUT': '/elsewhere'}) for step in campaign.PROFILES['rc1']]
        self.assertIsNone(campaign.plan_of({'campaign': 'rc1', 'plan': edited}))
        self.assertIsNone(campaign.plan_of({'campaign': 'other', 'plan': campaign.PROFILES['rc1']}))


if __name__ == '__main__':
    unittest.main()
