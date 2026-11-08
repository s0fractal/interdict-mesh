#!/usr/bin/env bash
# Two nodes on one host, meshed over loopback: node A (measured) and its peer B. Root, Linux, lab
# VM only. Measurement only: nothing here is run by CI or by the node.
#   sudo docs/measurements/2026-11-07-tick-at-every-bound/run-mesh.sh BINARY OUT_DIR [HOLD [CONNS [CHURN_A [CHURN_B]]]]
#
# B's detector fills B's own claims (from 12.0.0.0) and, once B is full, retracts its oldest and
# replaces them (drive.py --churn retract-oldest: only claims within the support bound can be
# lifted); B sends every claim, retraction and lease to A. A takes them all (the whole
# peer share, MAX_KNOWN_CLAIMS - OWN_RESERVE, from this one peer, every one enforced or waiting
# for the kernel map), while A's own detector fills A's own room, its event ids, strikes and
# support. A's tick, its RSS and its metrics are sampled every second; both state files are
# summarised at the end. Each retraction's answer waits for the disk, and answers waiting together
# share one copy of the state, so CONNS connections a node retract about CONNS / 0.4 s claims a second.
set -euo pipefail
BIN=$(realpath "$1"); OUT=$(realpath -m "$2"); HOLD=${3:-600}; CONNS=${4:-16}; CHURN_A=${5:-retract-oldest}; CHURN_B=${6:-retract-oldest}
HERE=$(dirname "$(realpath "$0")")
DRIVE="$HERE/../2026-11-06-tick-at-bounds/drive.py"
rm -rf "$OUT"; mkdir -p "$OUT/a" "$OUT/b"
ip link add ima0 type veth peer name ima1
ip link add imb0 type veth peer name imb1
PIDS=()
cleanup() {
    for p in "${PIDS[@]}"; do kill -INT "$p" 2>/dev/null || true; done
    sleep 3
    for p in "${PIDS[@]}"; do kill -9 "$p" 2>/dev/null || true; done
    ip link del ima0 2>/dev/null || true; ip link del imb0 2>/dev/null || true
}
trap cleanup EXIT
for l in ima0 ima1 imb0 imb1; do ip link set "$l" up; done
"$BIN" --version >"$OUT/version.txt"
A_PUB=$("$BIN" --key-file "$OUT/a/node.key" --print-public-key)
B_PUB=$("$BIN" --key-file "$OUT/b/node.key" --print-public-key)
printf '[{"node_id": 2, "public_key": "%s"}]' "$B_PUB" >"$OUT/a/peers.json"
printf '[{"node_id": 1, "public_key": "%s"}]' "$A_PUB" >"$OUT/b/peers.json"
# The whole peer share for B: 262144 - 65536.
SHARE=196608
RUST_LOG=warn "$BIN" --interface ima0 --node-id 1 --state-file "$OUT/a/state.json" \
    --db-path "$OUT/a/events.sntl" --key-file "$OUT/a/node.key" --peers-file "$OUT/a/peers.json" \
    --p2p-bind 127.0.0.1:7951 --metrics-bind 127.0.0.1:9471 \
    --peer-max-known "$SHARE" --peer-max-active "$SHARE" \
    --control-socket "$OUT/a/control.sock" --ipc-socket "$OUT/a/ipc.sock" >"$OUT/a/node.log" 2>&1 &
A=$!; PIDS+=("$A")
RUST_LOG=warn "$BIN" --interface imb0 --node-id 2 --state-file "$OUT/b/state.json" \
    --db-path "$OUT/b/events.sntl" --key-file "$OUT/b/node.key" --peers-file "$OUT/b/peers.json" \
    --p2p-bind 127.0.0.1:7952 --seed-peer 127.0.0.1:7951 --metrics-bind 127.0.0.1:9472 \
    --control-socket "$OUT/b/control.sock" --ipc-socket "$OUT/b/ipc.sock" >"$OUT/b/node.log" 2>&1 &
B=$!; PIDS+=("$B")
metric() { curl -s "http://127.0.0.1:$1/metrics" | awk -v m="$2" '$1 == m { print $2 }'; }
for _ in $(seq 1 100); do [ "$(metric 9471 interdict_p2p_active_peers)" = 1 ] && break; sleep 0.2; done
[ "$(metric 9471 interdict_p2p_active_peers)" = 1 ] || { echo "the nodes did not mesh" >&2; exit 1; }
# A's sampler: drive.py with no connections only samples, for at most --max-seconds.
python3 "$DRIVE" --socket "$OUT/a/ipc.sock" --metrics http://127.0.0.1:9471/metrics --pid "$A" \
    --out "$OUT/a/sampled" --conns 0 --max-seconds "$((HOLD + 400))" &
SAMPLER=$!
python3 "$DRIVE" --socket "$OUT/b/ipc.sock" --metrics http://127.0.0.1:9472/metrics --pid "$B" \
    --out "$OUT/b/driven" --hold "$HOLD" --churn "$CHURN_B" --conns "$CONNS" --first 12.0.0.0 &
DRIVE_B=$!
python3 "$DRIVE" --socket "$OUT/a/ipc.sock" --metrics http://127.0.0.1:9471/metrics --pid "$A" \
    --out "$OUT/a/driven" --hold "$HOLD" --churn "$CHURN_A" --conns "$CONNS"
wait "$DRIVE_B"
kill "$SAMPLER" 2>/dev/null || true; wait "$SAMPLER" 2>/dev/null || true
curl -s http://127.0.0.1:9471/metrics >"$OUT/a/final-metrics.txt"
curl -s http://127.0.0.1:9472/metrics >"$OUT/b/final-metrics.txt"
for n in a b; do
    python3 - "$OUT/$n/state.json" >"$OUT/$n/state-summary.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in s.items()}, indent=1, sort_keys=True))
PY
done
ls -l "$OUT"/a/state.json "$OUT"/b/state.json >"$OUT/state-files.txt"
