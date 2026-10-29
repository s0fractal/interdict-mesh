#!/bin/bash
# Rule 3 of ADR-0031 from the package: A = attested candidate ee16318 (archive 03bae666...),
# B = attested main candidate d638c83 (archive 3c17c8c5...), the upgrade and rollback build.
O=/var/lib/sokol-campaigns/rc1-ee16318-rehearsal; mkdir -p $O/a $O/b
cp /var/lib/sokol-campaigns/rc1-ee16318-pkg/usr/local/bin/interdictd $O/a/orchestrator
cp /var/lib/sokol-campaigns/rc1-ee16318-pkg/usr/local/bin/interdict-mon $O/a/monitor
cp /var/lib/sokol-campaigns/rc1-b-d638c83-pkg/usr/local/bin/interdictd $O/b/orchestrator
cp /var/lib/sokol-campaigns/rc1-b-d638c83-pkg/usr/local/bin/interdict-mon $O/b/monitor
sha256sum $O/a/* $O/b/* > $O/inputs.sha256
cd /home/s0fractal.guest/rc1-ee16318-src
bash scripts/runbook-rehearsal.sh $O/a $O/b > $O/rehearsal.txt 2>&1
echo "exit=$? $(date -u +%FT%TZ)" >> $O/rehearsal.txt
