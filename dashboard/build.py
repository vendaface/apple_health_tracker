#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vendaface
# Part of apple_health_tracker — https://github.com/vendaface/apple_health_tracker
"""Inline ECharts + data into a single self-contained dashboard HTML file.

Usage:
    python3 build.py [summary.json] [detail.json] [output.html]
Defaults: data/nightly_summary.json  data/nightly_detail.json  sleep-dashboard.html
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
summary_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "nightly_summary.json")
detail_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "data", "nightly_detail.json")
dest = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "sleep-dashboard.html")

tpl = open(os.path.join(HERE, "template.html")).read()
echarts = open(os.path.join(HERE, "vendor", "echarts.min.js")).read()
summary = open(summary_path).read()
detail = open(detail_path).read()

out = (tpl
       .replace("/*__ECHARTS__*/", echarts)
       .replace("/*__SUMMARY__*/", summary)
       .replace("/*__DETAIL__*/", detail))

with open(dest, "w") as f:
    f.write(out)
print(f"Wrote {dest}  ({len(out)/1_048_576:.1f} MB)")
