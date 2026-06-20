#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vendaface
# Part of apple_health_tracker — https://github.com/vendaface/apple_health_tracker
"""
Apple Health export -> sleep + pulmonary dashboard data.

Streams export.xml (constant memory) and extracts only the record types needed
for the sleep visualizer. Groups sleep into nights, deduplicates overlapping
sources (prefers Apple Watch staged data), bins overnight vitals, and writes a
compact JSON dataset the dashboard inlines.

Usage:
    python3 etl.py [path/to/export.xml] [out_dir]
Defaults: ../export.xml  ->  ./data/
"""

import sys, os, json, datetime as dt
from collections import defaultdict
from xml.etree.ElementTree import iterparse

HERE = os.path.dirname(os.path.abspath(__file__))
XML_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "export.xml")
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "data")
os.makedirs(OUT_DIR, exist_ok=True)

# ---- record types we care about -------------------------------------------
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
VITALS = {
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2",       # 0-1 -> %
    "HKQuantityTypeIdentifierRespiratoryRate": "resp",        # count/min
    "HKQuantityTypeIdentifierHeartRate": "hr",                # count/min
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",# ms
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "wristtemp",  # degF
}
# whole-night single-value metrics (kept separately)
NIGHT_METRICS = {
    "HKQuantityTypeIdentifierAppleSleepingBreathingDisturbances": "breathing",  # count
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
}

STAGE_MAP = {
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",  # unstaged
    "HKCategoryValueSleepAnalysisInBed": "inbed",
}
ASLEEP_STAGES = {"core", "deep", "rem", "asleep"}   # counts as sleep time
STAGED = {"core", "deep", "rem", "awake"}           # implies a staged source


def parse_dt(s):
    # "2024-09-28 22:47:52 -0400"
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def night_key(d):
    """Map a datetime to the night it belongs to (noon-to-noon rule)."""
    return (d - dt.timedelta(hours=12)).date().isoformat()


def is_watch(source):
    s = source.lower()
    return "watch" in s


# ---- streaming pass --------------------------------------------------------
# Sleep segments grouped by night.  Vitals stored flat (assigned to nights after).
sleep_by_night = defaultdict(list)          # night -> [ {start,end,stage,source} ]
vitals = {k: [] for k in ("spo2", "resp", "hr", "hrv", "wristtemp")}  # [(ts, val)]
night_metrics = defaultdict(dict)           # night -> {breathing:.., resting_hr:..}

count = 0
kept = 0
print(f"Parsing {XML_PATH} ...", flush=True)

ctx = iterparse(XML_PATH, events=("end",))
for _, el in ctx:
    if el.tag != "Record":
        el.clear()
        continue
    count += 1
    if count % 1_000_000 == 0:
        print(f"  ...{count:,} records scanned, {kept:,} kept", flush=True)

    t = el.get("type")
    try:
        if t == SLEEP:
            stage = STAGE_MAP.get(el.get("value"))
            if stage:
                start = parse_dt(el.get("startDate"))
                end = parse_dt(el.get("endDate"))
                sleep_by_night[night_key(start)].append({
                    "start": start, "end": end, "stage": stage,
                    "source": el.get("sourceName", ""),
                })
                kept += 1
        elif t in VITALS:
            key = VITALS[t]
            start = parse_dt(el.get("startDate"))
            val = float(el.get("value"))
            if key == "spo2":
                val *= 100.0  # 0-1 -> %
            vitals[key].append((start, val))
            kept += 1
        elif t in NIGHT_METRICS:
            key = NIGHT_METRICS[t]
            start = parse_dt(el.get("startDate"))
            val = float(el.get("value"))
            nk = night_key(start)
            # keep the largest breathing value / typical resting hr for the night
            if key not in night_metrics[nk]:
                night_metrics[nk][key] = val
            elif key == "breathing":
                night_metrics[nk][key] = max(night_metrics[nk][key], val)
            kept += 1
    except (TypeError, ValueError):
        pass
    el.clear()

print(f"Done scanning: {count:,} records, {kept:,} kept. "
      f"{len(sleep_by_night):,} candidate nights.", flush=True)

# Sort vitals once by timestamp for fast windowed lookups, and precompute the
# parallel timestamp arrays once (NOT per call) for bisect.
import bisect
vitals_ts = {}
for k in vitals:
    vitals[k].sort(key=lambda x: x[0])
    vitals_ts[k] = [x[0] for x in vitals[k]]


def vitals_in_window(key, lo, hi):
    ts = vitals_ts[key]
    i = bisect.bisect_left(ts, lo)
    j = bisect.bisect_right(ts, hi)
    return vitals[key][i:j]


def downsample(points, bucket_min):
    """Average values into fixed time buckets -> [(iso_ts, val)]."""
    if not points:
        return []
    out = []
    bucket = dt.timedelta(minutes=bucket_min)
    start = points[0][0]
    cur_end = start + bucket
    acc, n = 0.0, 0
    cur_ts = start
    for ts, v in points:
        if ts >= cur_end:
            if n:
                out.append([cur_ts.isoformat(), round(acc / n, 2)])
            while ts >= cur_end:
                cur_ts = cur_end
                cur_end += bucket
            acc, n = 0.0, 0
        acc += v; n += 1
    if n:
        out.append([cur_ts.isoformat(), round(acc / n, 2)])
    return out


# ---- build per-night records ----------------------------------------------
nights = []
for nk in sorted(sleep_by_night.keys()):
    segs = sleep_by_night[nk]
    # choose source set: if any staged source present, keep only watch segments
    has_staged = any(s["stage"] in STAGED for s in segs)
    if has_staged:
        watch = [s for s in segs if is_watch(s["source"])]
        chosen = watch if watch else segs
        staged = True
    else:
        # duration-only era: prefer the single source with most coverage
        by_src = defaultdict(float)
        for s in segs:
            by_src[s["source"]] += (s["end"] - s["start"]).total_seconds()
        best = max(by_src, key=by_src.get)
        chosen = [s for s in segs if s["source"] == best]
        staged = False

    chosen.sort(key=lambda s: s["start"])
    # merge overlaps for total-sleep math; keep raw segs for hypnogram
    stage_secs = defaultdict(float)
    for s in chosen:
        stage_secs[s["stage"]] += (s["end"] - s["start"]).total_seconds()

    asleep_secs = sum(v for k, v in stage_secs.items() if k in ASLEEP_STAGES)
    if asleep_secs < 30 * 60:          # ignore naps / fragments < 30 min
        continue

    bed = min(s["start"] for s in chosen)
    wake = max(s["end"] for s in chosen)
    in_bed_secs = (wake - bed).total_seconds()

    rec = {
        "night": nk,
        "staged": staged,
        "bedtime": bed.isoformat(),
        "wake": wake.isoformat(),
        "tib_min": round(in_bed_secs / 60),
        "asleep_min": round(asleep_secs / 60),
        "efficiency": round(100 * asleep_secs / in_bed_secs, 1) if in_bed_secs else None,
        "stages_min": {k: round(v / 60) for k, v in stage_secs.items()},
        # hypnogram segments (compact: start,end,stage)
        "segments": [[s["start"].isoformat(), s["end"].isoformat(), s["stage"]]
                     for s in chosen],
    }

    # overnight vitals within the sleep window
    summary = {}
    detail = {}
    for key, label in (("spo2", "spo2"), ("resp", "resp"),
                       ("hr", "hr"), ("hrv", "hrv"), ("wristtemp", "wristtemp")):
        pts = vitals_in_window(key, bed, wake)
        if not pts:
            continue
        vals = [v for _, v in pts]
        summary[key] = {
            "avg": round(sum(vals) / len(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "n": len(vals),
        }
        # detail series only for the rich metrics shown in the overlay
        if key in ("spo2", "resp", "hr"):
            detail[key] = downsample(pts, 5)
    rec["vitals"] = summary
    rec["detail"] = detail

    nm = night_metrics.get(nk, {})
    if "breathing" in nm:
        rec["breathing"] = round(nm["breathing"], 2)
    if "resting_hr" in nm:
        rec["resting_hr"] = round(nm["resting_hr"], 1)

    nights.append(rec)

print(f"Built {len(nights):,} valid sleep nights "
      f"({sum(1 for n in nights if n['staged']):,} staged).", flush=True)

# ---- split output: light summary + per-night detail ------------------------
summary_rows = []
for n in nights:
    summary_rows.append({k: n[k] for k in (
        "night", "staged", "bedtime", "wake", "tib_min", "asleep_min",
        "efficiency", "stages_min") if k in n}
        | {"vitals": n.get("vitals", {}),
           **({"breathing": n["breathing"]} if "breathing" in n else {}),
           **({"resting_hr": n["resting_hr"]} if "resting_hr" in n else {})})

detail_index = {n["night"]: {"segments": n["segments"], "detail": n["detail"]}
                for n in nights}

with open(os.path.join(OUT_DIR, "nightly_summary.json"), "w") as f:
    json.dump({"generated": night_key(parse_dt("2026-06-20 12:00:00 -0400")),
               "nights": summary_rows}, f, separators=(",", ":"))
with open(os.path.join(OUT_DIR, "nightly_detail.json"), "w") as f:
    json.dump(detail_index, f, separators=(",", ":"))

# quick stats file for validation
staged_nights = [n for n in nights if n["staged"]]
stats = {
    "total_nights": len(nights),
    "staged_nights": len(staged_nights),
    "date_range": [nights[0]["night"], nights[-1]["night"]] if nights else None,
    "nights_with_spo2": sum(1 for n in nights if "spo2" in n.get("vitals", {})),
    "nights_with_resp": sum(1 for n in nights if "resp" in n.get("vitals", {})),
    "nights_with_breathing": sum(1 for n in nights if "breathing" in n),
}
with open(os.path.join(OUT_DIR, "stats.json"), "w") as f:
    json.dump(stats, f, indent=2)
print("STATS:", json.dumps(stats, indent=2), flush=True)
print(f"Wrote data to {OUT_DIR}", flush=True)
