#!/usr/bin/env python3
"""Keep a daily series of the AAA US national-average regular gas price.

Usage:
  python3 strategy/tools/aaa_log.py record   # fetch AAA, store today + yesterday
  python3 strategy/tools/aaa_log.py sd       # daily-change sd from stored prints

Why (RETRO-20261023-1610): the 2026-10-17 rule says an AAA daily-bracket
estimate must cite a daily-change sd computed from >= 15 consecutive AAA
prints. gasprices.aaa.com only shows Current / Yesterday / Week ago / Month
ago / Year ago, so no such series existed and the Oct22 ladder used an
unsourced sd ~0.7c again; the day moved +2.25c and the ladder lost +0.21
dBrier. Running `record` on every FULL cycle builds the series; `sd`
refuses to print a number until n >= 15 consecutive daily changes exist.
"""
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys

URL = "https://gasprices.aaa.com/"
STORE = os.path.join(os.path.dirname(__file__), "..", "aaa-daily.jsonl")
MIN_N = 15


def fetch():
    # urllib is blocked by the same TLS fingerprinting as the CLOB; the
    # 2026-10-21 playbook entry verified curl with a curl UA from the cloud.
    html = subprocess.run(
        ["curl", "-sS", "--max-time", "20", "-A", "curl/8.0", URL],
        capture_output=True, text=True, check=True).stdout
    asof = re.search(r"Price as of (\d{1,2})/(\d{1,2})/(\d{2})", html)
    if not asof:
        raise SystemExit("aaa_log: 'Price as of' date not found")
    m, d, y = (int(x) for x in asof.groups())
    today = dt.date(2000 + y, m, d)
    vals = {}
    for label in ("Current Avg.", "Yesterday Avg."):
        hit = re.search(re.escape(label) + r".*?\$(\d+\.\d{3,4})", html, re.S)
        if not hit:
            raise SystemExit(f"aaa_log: '{label}' row not found")
        vals[label] = float(hit.group(1))
    return {today.isoformat(): vals["Current Avg."],
            (today - dt.timedelta(days=1)).isoformat(): vals["Yesterday Avg."]}


def load():
    rows = {}
    if os.path.exists(STORE):
        for line in open(STORE):
            r = json.loads(line)
            rows[r["date"]] = r["price"]
    return rows


def record():
    rows = load()
    new = {k: v for k, v in fetch().items() if k not in rows}
    if new:
        with open(STORE, "a") as f:
            for k in sorted(new):
                f.write(json.dumps({"date": k, "price": new[k],
                                    "source": URL}) + "\n")
    print(json.dumps({"added": new, "stored": len(rows) + len(new)}))


def sd():
    rows = load()
    dates = sorted(rows)
    # longest run of consecutive calendar days ending at the newest print
    run = dates[-1:] if dates else []
    for a in reversed(dates[:-1]):
        if dt.date.fromisoformat(run[0]) - dt.date.fromisoformat(a) == dt.timedelta(days=1):
            run.insert(0, a)
        else:
            break
    changes = [round((rows[b] - rows[a]) * 100, 2) for a, b in zip(run, run[1:])]
    out = {"n_changes": len(changes), "first": run[0] if run else None,
           "last": run[-1] if run else None}
    if len(changes) < MIN_N:
        out["sd_cents"] = None
        out["verdict"] = f"n<{MIN_N}: record AAA daily rows at the mid as market-agrees"
    else:
        out["sd_cents"] = round(statistics.stdev(changes), 3)
        out["mean_cents"] = round(statistics.mean(changes), 3)
    print(json.dumps(out))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sd"
    {"record": record, "sd": sd}.get(cmd, lambda: sys.exit(__doc__))()
