#!/usr/bin/env python3
"""Drive one node's own claims to MAX_KNOWN_CLAIMS over its detector IPC and sample its tick.

The RC-2 condition (ADR-0031, ROADMAP 0a) asks for `interdict_tick_seconds_max` under load with
the block table at its bounds. This sends `SIGNAL#<id>:<source>|<new address>|-|<reason>` lines
in ACK mode over several connections (the node lets each 1 000 lines/s, all together 2 000/s),
one new address each, until the node answers that the known-claims table is full, then keeps
the load on (each further line is refused at the bound) for --hold seconds. Every second it
samples the node's metrics (tick, tick max, kernel blocks) and its RSS.

    sudo python3 drive.py --socket IPC_SOCKET --metrics URL --pid NODE_PID --out DIR \
        [--count 262144] [--conns 4] [--hold 600] [--ttl SECONDS] [--churn retract|retract-oldest]
        [--first 11.0.0.0]

Writes DIR/samples.csv (one row a second), DIR/replies.json (answers by class) and
DIR/latency.json (ACK round trip, percentiles per phase). Measurement only: nothing here is run
by CI or by the node.
"""
from __future__ import annotations

import argparse
import collections
import csv
import ipaddress
import json
import pathlib
import socket
import threading
import time
import urllib.request

SOURCE = "ids"
# The node keeps 200 characters of a reason; this fills them.
REASON = "bounds-" + "r" * 193
FIRST = int(ipaddress.IPv4Address("11.0.0.0"))


def address(i: int) -> str:
    return str(ipaddress.IPv4Address(FIRST + i))


class Shared:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.replies: collections.Counter[str] = collections.Counter()
        self.full_at: float | None = None
        self.latency: dict[str, list[float]] = {"fill": [], "hold": [], "retract": []}
        self.stop = threading.Event()
        self.sent = 0
        # This driver's own claims held by the node: admitted (applied or pending) less lifted.
        self.held = 0


ADMITTED = ("OK applied", "OK pending")


def connection(k: int, conns: int, count: int, ttl: int, churn: str, path: str, sh: Shared,
               hold_until: list[float]) -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(path)
    r = s.makefile("rb")
    s.sendall(b"ACK\n")
    assert r.readline().strip() == b"OK ack"

    def ask(line: str, phase: str) -> str:
        t0 = time.monotonic()
        s.sendall(line.encode())
        reply = r.readline().decode().strip()
        with sh.lock:
            sh.sent += 1
            sh.replies[reply] += 1
            sh.latency[phase].append(time.monotonic() - t0)
        return reply

    mine: list[int] = []   # this connection's admitted signals, newest last
    i = k
    while not sh.stop.is_set():
        with sh.lock:
            full = sh.full_at is not None
        if full and churn in ("retract", "retract-oldest") and mine:
            # Take one of this connection's own claims back (its event id is still remembered:
            # the newest), then signal a new address into the slot it freed. The claims stay
            # at their bound, less the retractions in flight, and the table changes every tick.
            # retract-oldest takes the oldest instead: past the support bound only the first
            # claims have the support a retraction removes, so only they are lifted.
            j = mine.pop(0) if churn == "retract-oldest" else mine.pop()
            reply = ask(f"RETRACT#b{j}:{SOURCE}|{address(j)}\n", "retract")
            if not reply:
                break
            if reply.startswith("OK lifted"):   # a durability warning may follow
                with sh.lock:
                    sh.held -= 1
        head = f"SIGNAL#b{i}" + (f";ttl={ttl}" if ttl else "")
        reply = ask(f"{head}:{SOURCE}|{address(i)}|-|{REASON}\n", "hold" if full else "fill")
        if not reply:
            break
        if reply in ADMITTED:
            mine.append(i)
            with sh.lock:
                sh.held += 1
        with sh.lock:
            if sh.full_at is None and "too many known claims" in reply:   # TOO_MANY_CLAIMS
                sh.full_at = time.monotonic()
                hold_until[0] = sh.full_at + HOLD
        i += conns
        if i >= 4 * count:   # addresses taken back long ago are new to the node again
            i = k
    s.close()


def metrics(url: str) -> dict[str, float]:
    out: dict[str, float] = {}
    with urllib.request.urlopen(url, timeout=5) as resp:
        for raw in resp.read().decode().splitlines():
            if raw.startswith("#") or " " not in raw:
                continue
            name, value = raw.rsplit(" ", 1)
            try:
                out[name] = float(value)
            except ValueError:
                pass
    return out


def rss_kb(pid: int) -> int:
    for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return -1


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]


HOLD = 600.0


def main() -> None:
    global HOLD, FIRST
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=262_144)
    ap.add_argument("--conns", type=int, default=4)
    ap.add_argument("--hold", type=float, default=600.0)
    ap.add_argument("--max-seconds", type=float, default=1800.0)
    # With a TTL shorter than the fill, claims end while new ones arrive: the table stays at
    # its bound and changes every tick, so every tick writes the state.
    ap.add_argument("--ttl", type=int, default=0)
    # retract: once full, each connection takes one of its own claims back before each new
    # signal, so the claims stay at their bound while the table changes.
    ap.add_argument("--churn", choices=["none", "retract", "retract-oldest"], default="none")
    # Where this driver's addresses start: two drivers of two meshed nodes use their own.
    ap.add_argument("--first", default="11.0.0.0")
    a = ap.parse_args()
    HOLD = a.hold
    FIRST = int(ipaddress.IPv4Address(a.first))
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sh = Shared()
    hold_until = [float("inf")]
    threads = [
        threading.Thread(target=connection, args=(k, a.conns, a.count, a.ttl, a.churn, a.socket, sh, hold_until), daemon=True)
        for k in range(a.conns)
    ]
    start = time.monotonic()
    for t in threads:
        t.start()
    keys = [
        "interdict_tick_seconds",
        "interdict_tick_seconds_max",
        'interdict_blocks_active{family="ipv4"}',
        "interdict_blocks_pending",
        "interdict_event_ids_remembered",
        "interdict_strikes_remembered",
    ]
    with open(out / "samples.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["t_s", "sent", "phase", "held", "rss_kb", *keys])
        while True:
            now = time.monotonic()
            if now >= hold_until[0] or now - start > a.max_seconds:
                break
            try:
                m = metrics(a.metrics)
            except OSError:
                m = {}
            with sh.lock:
                sent, held, phase = sh.sent, sh.held, ("fill" if sh.full_at is None else "hold")
            w.writerow([f"{now - start:.1f}", sent, phase, held, rss_kb(a.pid), *[m.get(k, "") for k in keys]])
            fh.flush()
            time.sleep(1.0)
    sh.stop.set()
    for t in threads:
        t.join(timeout=10)
    with sh.lock:
        (out / "replies.json").write_text(json.dumps(dict(sh.replies), indent=1, sort_keys=True) + "\n")
        lat = {
            phase: {"n": len(xs), **{f"p{p}": pct(xs, p) for p in (50, 99, 99.9)}, "max": max(xs, default=float("nan"))}
            for phase, xs in sh.latency.items()
        }
        lat["full_after_s"] = None if sh.full_at is None else sh.full_at - start
        (out / "latency.json").write_text(json.dumps(lat, indent=1) + "\n")
    print(json.dumps(lat))


if __name__ == "__main__":
    main()
