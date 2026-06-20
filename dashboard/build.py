#!/usr/bin/env python3
"""Inline ECharts + data into a single self-contained dashboard HTML file."""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
tpl = open(os.path.join(HERE, "template.html")).read()
echarts = open(os.path.join(HERE, "vendor", "echarts.min.js")).read()
summary = open(os.path.join(HERE, "data", "nightly_summary.json")).read()
detail = open(os.path.join(HERE, "data", "nightly_detail.json")).read()

out = (tpl
       .replace("/*__ECHARTS__*/", echarts)
       .replace("/*__SUMMARY__*/", summary)
       .replace("/*__DETAIL__*/", detail))

dest = os.path.join(HERE, "sleep-dashboard.html")
with open(dest, "w") as f:
    f.write(out)
print(f"Wrote {dest}  ({len(out)/1_048_576:.1f} MB)")
