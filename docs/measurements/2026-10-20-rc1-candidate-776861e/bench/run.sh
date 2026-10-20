#!/bin/bash
cd /home/s0fractal.linux/rc1b-src
for spec in "reaction 3 20" "unblock 3 20" "recover 3" "restart 3 10" "restart 10 10"; do
  set -- $spec; name=$(echo $spec | tr " " "-")
  echo "== $spec start $(date -u +%FT%TZ)" >> /var/lib/sokol-campaigns/rc1-776861e-bench/progress.log
  bash bench/mesh.sh $1 /var/lib/sokol-campaigns/rc1-776861e-candidate/usr/local/bin/sokol-orchestrator /var/lib/sokol-campaigns/rc1-776861e-candidate/usr/local/bin/sokol-monitor ${@:2} > /var/lib/sokol-campaigns/rc1-776861e-bench/$name.txt 2>&1
  echo "== $spec exit=$? $(date -u +%FT%TZ)" >> /var/lib/sokol-campaigns/rc1-776861e-bench/progress.log
done
RESTART_CONTROL=1 bash bench/mesh.sh restart /var/lib/sokol-campaigns/rc1-776861e-candidate/usr/local/bin/sokol-orchestrator /var/lib/sokol-campaigns/rc1-776861e-candidate/usr/local/bin/sokol-monitor 3 3 > /var/lib/sokol-campaigns/rc1-776861e-bench/restart-control.txt 2>&1
echo "== restart-control exit=$? $(date -u +%FT%TZ)" >> /var/lib/sokol-campaigns/rc1-776861e-bench/progress.log
echo ALL_DONE >> /var/lib/sokol-campaigns/rc1-776861e-bench/progress.log
