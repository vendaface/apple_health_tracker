#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vendaface
# Part of apple_health_tracker — https://github.com/vendaface/apple_health_tracker
"""
Generate SYNTHETIC sleep data in the dashboard's schema — for demos/screenshots
without exposing any real health data. Output matches etl.py so build.py can
turn it straight into a dashboard HTML.

Usage:
    python3 sample_data.py [summary.json] [detail.json] [nights]
Defaults: ../docs/sample_summary.json ../docs/sample_detail.json 150
"""
import sys, os, json, math, random
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
SUMMARY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "docs", "sample_summary.json")
DETAIL = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "docs", "sample_detail.json")
N = int(sys.argv[3]) if len(sys.argv) > 3 else 150

random.seed(42)  # deterministic — same demo every build
os.makedirs(os.path.dirname(SUMMARY), exist_ok=True)

# Walk backwards from a fixed reference date (no real "today" leaks in).
END = dt.date(2025, 12, 31)
STAGE_CYCLE = ["core", "deep", "core", "rem", "core", "deep", "rem", "core", "rem"]


def iso(d):
    return d.replace(microsecond=0).isoformat()


def build_night(day):
    """One synthetic staged night with overnight vitals."""
    # bedtime 22:15–23:45
    bed = dt.datetime.combine(day, dt.time(22, 0)) + dt.timedelta(minutes=random.randint(15, 105))
    total_min = random.randint(380, 480)          # ~6.3–8 h in bed
    wake = bed + dt.timedelta(minutes=total_min)

    # build stage segments across the night in rough sleep cycles
    segments, stage_min = [], {"core": 0, "deep": 0, "rem": 0, "awake": 0}
    t = bed
    ci = 0
    # brief settling awake at start
    while t < wake:
        remaining = (wake - t).total_seconds() / 60
        if remaining < 5:
            break
        # occasional brief awakening
        if random.random() < 0.12:
            seg = min(remaining, random.randint(3, 9))
            stage = "awake"
        else:
            stage = STAGE_CYCLE[ci % len(STAGE_CYCLE)]
            ci += 1
            base = {"core": 28, "deep": 22, "rem": 20}[stage]
            seg = min(remaining, max(6, random.gauss(base, 7)))
        e = t + dt.timedelta(minutes=seg)
        if e > wake:
            e = wake
        segments.append([iso(t), iso(e), stage])
        stage_min[stage] += round((e - t).total_seconds() / 60)
        t = e

    asleep = stage_min["core"] + stage_min["deep"] + stage_min["rem"]
    tib = round((wake - bed).total_seconds() / 60)

    # overnight vitals (downsampled series, like etl.py's 5-min bins)
    # a few nights get a desaturation event for visual interest
    desat_night = random.random() < 0.18
    spo2, resp, hr = [], [], []
    n_steps = max(1, tib // 5)
    spo2_min = 100.0
    for k in range(n_steps):
        ts = bed + dt.timedelta(minutes=5 * k)
        frac = k / n_steps
        # SpO2 ~ 96–98 baseline, dips mid-night, optional desat
        s = 97 + math.sin(frac * math.pi * 3) * 0.8 + random.gauss(0, 0.6)
        if desat_night and 0.35 < frac < 0.6:
            s -= random.uniform(4, 8)
        s = max(86, min(100, s))
        spo2_min = min(spo2_min, s)
        if k % 6 == 0:           # SpO2 sampled less often
            spo2.append([iso(ts), round(s, 1)])
        # respiratory rate ~ 13–18
        resp.append([iso(ts), round(14.5 + math.sin(frac * 6) * 1.6 + random.gauss(0, 0.7), 1)])
        # heart rate ~ 50–68, lower in deep sleep early
        hr.append([iso(ts), round(58 - 6 * math.cos(frac * math.pi) + random.gauss(0, 2.5), 0)])

    def stat(series, i=1):
        vals = [p[i] for p in series]
        return {"avg": round(sum(vals) / len(vals), 1), "min": round(min(vals), 1),
                "max": round(max(vals), 1), "n": len(vals)}

    night = day.isoformat()
    summary = {
        "night": night, "staged": True,
        "bedtime": iso(bed), "wake": iso(wake),
        "tib_min": tib, "asleep_min": asleep,
        "efficiency": round(100 * asleep / tib, 1),
        "stages_min": stage_min,
        "vitals": {"spo2": stat(spo2), "resp": stat(resp), "hr": stat(hr)},
        "breathing": round(abs(random.gauss(1.2, 0.9)) + (2.5 if desat_night else 0), 2),
        "resting_hr": round(random.gauss(60, 4), 1),
    }
    detail = {"segments": segments, "detail": {"spo2": spo2, "resp": resp, "hr": hr}}
    return summary, detail


nights, detail_index = [], {}
for i in range(N):
    day = END - dt.timedelta(days=N - 1 - i)
    if random.random() < 0.08:      # a few missing nights, like real wear gaps
        continue
    s, d = build_night(day)
    nights.append(s)
    detail_index[s["night"]] = d

with open(SUMMARY, "w") as f:
    json.dump({"generated": END.isoformat(), "nights": nights}, f, separators=(",", ":"))
with open(DETAIL, "w") as f:
    json.dump(detail_index, f, separators=(",", ":"))
print(f"Wrote {len(nights)} synthetic nights -> {SUMMARY}, {DETAIL}")
