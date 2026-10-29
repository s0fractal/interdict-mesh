#!/bin/bash
# Rule 4 of ADR-0031 on the attested candidate ee16318 (archive 03bae666...), after the campaign.
cd /home/s0fractal.guest/rc1-ee16318-src
B=/var/lib/sokol-campaigns/rc1-ee16318-pkg/usr/local/bin
O=/var/lib/sokol-campaigns/rc1-ee16318-bench; mkdir -p $O
for spec in "reaction 3 20" "unblock 3 20" "recover 3" "restart 3 10" "restart 10 10"; do
  set -- $spec; name=$(echo $spec | tr " " "-")
  echo "== $spec start $(date -u +%FT%TZ)" >> $O/progress.log
  bash bench/mesh.sh $1 $B/interdictd $B/interdict-mon ${@:2} > $O/$name.txt 2>&1
  echo "== $spec exit=$? $(date -u +%FT%TZ)" >> $O/progress.log
done
RESTART_CONTROL=1 bash bench/mesh.sh restart $B/interdictd $B/interdict-mon 3 3 > $O/restart-control.txt 2>&1
echo "== restart-control exit=$? $(date -u +%FT%TZ)" >> $O/progress.log
echo ALL_DONE >> $O/progress.log
