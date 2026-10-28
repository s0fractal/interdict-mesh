#!/usr/bin/env python3
"""Launch a bounded mesh campaign on a disposable systemd VM only (ADR-0031 rule 5).

--profile rc1 (default): a 60 min chaos phase (a restart every 60 s, a cut every 90 s, 180 s
TTL, so blocks outlive the settle and the final agreement is on a non-empty table) and a 120 min plateau phase without restarts (SOAK_PLATEAU=1: RSS and fds must level).
--profile long: the 24 h and 72 h phases RC-2 needs.

The VM's own maintenance is stopped first: apt's timers and unattended-upgrades restarted
the node under test in the 2026-10-20 campaign (needrestart, 6.47 h).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'rc1': [{'name': 'chaos', 'minutes': 60, 'env': {'RESTART_EVERY': '60', 'CUT_EVERY': '90', 'TTL': '180'}},
            {'name': 'plateau', 'minutes': 120,
             'env': {'RESTART_EVERY': '86400', 'CUT_EVERY': '300', 'TTL': '180', 'SOAK_PLATEAU': '1',
                     'SOAK_DISTINCT': '4096'}}],
    'long': [{'name': '24h', 'minutes': 24 * 60, 'env': {}}, {'name': '72h', 'minutes': 72 * 60, 'env': {}}],
}
# Host maintenance that restarts services under test; stopped and masked before a campaign.
QUIET = ('apt-daily.timer', 'apt-daily-upgrade.timer', 'unattended-upgrades.service')


def quiet_host():
    """Stop and mask the VM's own maintenance; return what each unit is now, refuse on failure."""
    done = {}
    for unit in QUIET:
        known = subprocess.run(['systemctl', 'cat', unit], capture_output=True).returncode == 0
        if not known:
            done[unit] = 'absent'; continue
        for verb in ('stop', 'mask'):
            if subprocess.run(['systemctl', verb, unit], capture_output=True).returncode:
                raise SystemExit(f'cannot {verb} {unit}: the campaign would race host maintenance')
        done[unit] = subprocess.run(['systemctl', 'is-enabled', unit], capture_output=True, text=True).stdout.strip()
    return done


def write(path, value):
    staged = path.with_suffix('.staged')
    staged.write_text(json.dumps(value, indent=2) + '\n')
    staged.replace(path)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            value.update(chunk)
    return value.hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(ROOT), *args], cwd=ROOT, text=True).strip()


def plan_of(receipt):
    """The phases to run: the code's profile named in the receipt, never the receipt's own copy (the
    receipt records the plan; an edited one is refused, not run)."""
    plan = PROFILES.get(receipt.get('campaign'))
    return plan if plan is not None and receipt.get('plan') == plan else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--monitor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=sorted(PROFILES), default='rc1')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.geteuid() != 0:
        parser.error('root on a disposable Linux systemd VM is required')
    vm = subprocess.run(['systemd-detect-virt', '--vm'], capture_output=True, text=True)
    if vm.returncode != 0:
        parser.error('a VM must be detected; physical hosts and containers are refused')
    args.binary = args.binary.resolve(strict=True)
    args.monitor = args.monitor.resolve(strict=True)
    args.output = args.output.resolve()
    if not args.worker:
        if git('status', '--porcelain'):
            parser.error('commit the experiment source first')
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        unit = 'sokol-campaign-' + str(time.time_ns())
        plan = PROFILES[args.profile]
        runtime = sum(p['minutes'] for p in plan) * 60 + 1800 * len(plan)
        receipt = {'profile': 'sokol.vm-campaign.v2', 'campaign': args.profile, 'status': 'LAUNCHING', 'unit': unit,
                   'source_commit': git('rev-parse', 'HEAD'),
                   'bench_sha256': digest(ROOT / 'bench/mesh.sh'),
                   'binary_sha256': digest(args.binary), 'monitor_sha256': digest(args.monitor),
                   'vm': vm.stdout.strip(), 'seed': 1729, 'plan': plan,
                   'quieted': quiet_host(),
                   'limits': {'memory_bytes': 4294967296, 'tasks': 256, 'cpu_percent': 200,
                              'tmp_bytes': 4294967296, 'file_bytes': 134217728,
                              'runtime_seconds': runtime},
                   'admission': 'NOT_ADMITTED', 'hardware': 'NOT_QUALIFIED',
                   'scope': 'mesh soak assertions; the plateau phase judges RSS and fds per node',
                   'phases': []}
        write(args.output / 'report.json', receipt)
        command = ['systemd-run', '--unit=' + unit, '--collect',
                   '--property=MemoryMax=4G', '--property=TasksMax=256', '--property=CPUQuota=200%',
                   '--property=RuntimeMaxSec=' + str(runtime),
                   '--property=LimitFSIZE=128M', '--property=PrivateTmp=yes',
                   '--property=TemporaryFileSystem=/tmp:rw,size=4G,mode=1777',
                   sys.executable, str(Path(__file__).resolve()), '--worker',
                   '--binary', str(args.binary), '--monitor', str(args.monitor), '--output', str(args.output)]
        result = subprocess.run(command)
        if result.returncode:
            receipt['status'] = 'LAUNCH_FAILED'; write(args.output / 'report.json', receipt)
        print(json.dumps({'unit': unit, 'report': str(args.output / 'report.json'),
                          'launch_returncode': result.returncode,
                          'status': 'SUBMITTED_TO_SYSTEMD' if not result.returncode else 'LAUNCH_FAILED'}))
        return result.returncode
    path = args.output / 'report.json'
    receipt = json.loads(path.read_text())
    if digest(args.binary) != receipt['binary_sha256'] or digest(args.monitor) != receipt['monitor_sha256']:
        receipt['status'] = 'REFUSED_CHANGED_BINARY'; write(path, receipt); return 1
    plan = plan_of(receipt)
    if plan is None:
        receipt['status'] = 'REFUSED_CHANGED_PLAN'; write(path, receipt); return 1
    # Privileged experiment, not a sandbox for untrusted native code. A hard cgroup kill
    # can prevent this write; a remaining RUNNING receipt then requires systemd readback.
    for step in plan:
        if git('rev-parse', 'HEAD') != receipt['source_commit'] or digest(ROOT / 'bench/mesh.sh') != receipt['bench_sha256']:
            receipt['status'] = 'REFUSED_CHANGED_EXPERIMENT'; write(path, receipt); return 1
        out = args.output / step['name']; out.mkdir(mode=0o700)
        phase = {'name': step['name'], 'minutes': step['minutes'], 'status': 'RUNNING', 'started_unix': time.time()}
        receipt['phases'].append(phase); receipt['status'] = 'RUNNING'; write(path, receipt)
        with (out / 'console.log').open('wb') as log:
            result = subprocess.run(['bash', str(ROOT / 'bench/mesh.sh'), 'soak',
                                     str(args.binary), str(args.monitor), '3', str(step['minutes'])],
                                    cwd=ROOT, env={**os.environ, **step['env'], 'BENCH_OUT': str(out), 'BENCH_SEED': '1729'},
                                    stdout=log, stderr=subprocess.STDOUT)
        phase.update(status='LIMITED_PASS' if result.returncode == 0 else 'FAILED',
                     returncode=result.returncode, finished_unix=time.time())
        write(path, receipt)
        if result.returncode:
            receipt['status'] = 'FAILED'; write(path, receipt); return 1
    receipt['status'] = 'LIMITED_PASS'; write(path, receipt)
    return 0


if __name__ == '__main__': raise SystemExit(main())
