"""scripts/campaign.py: the VM's own maintenance is stopped before a campaign (ADR-0031 rule 5).

The 2026-10-20 campaign on candidate 776861e was cut at 6.47 h by apt-daily-upgrade.timer
restarting the node under test (needrestart). Each case replaces systemctl with a recorder.

    python3 scripts/test_campaign.py
"""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('campaign', HERE / 'campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


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

    def test_long_keeps_the_24_and_72_hour_phases(self):
        self.assertEqual([p['minutes'] for p in campaign.PROFILES['long']], [24 * 60, 72 * 60])


if __name__ == '__main__':
    unittest.main()
