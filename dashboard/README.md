# Sleep & Respiratory Dashboard

A self-contained, interactive dashboard built from the Apple Health export, focused on
sleep and the respiratory metrics relevant to a **pulmonary specialist** (blood oxygen,
respiratory rate, Apple's sleeping breathing-disturbance index).

## How to view / share

Open **`sleep-dashboard.html`** by double-clicking it — it's a single self-contained file
(~11 MB) with all data and charts embedded. No internet or server needed. To share with
your specialist, just send them that one file (or open it and use **Print / PDF**).

## What's inside

- **Single-night detail** — hypnogram (Deep/Core/REM/Awake) with SpO₂, respiratory rate
  and heart rate overlaid on a shared, zoomable timeline. SpO₂ shows a 90% threshold line.
- **Sleep calendar** — every night shaded by hours slept; click a day to open it above.
- **Trends over time** — nightly sleep, avg SpO₂, respiratory rate, breathing-disturbance
  index, with a zoom slider.
- **Sleep-stage composition** — stacked stage minutes per night.
- **Breathing-disturbance focus** — the watchOS 11 apnea-related signal over time.
- **Summary cards** that recompute for the selected date range (3 mo / 6 mo / 1 yr / All /
  custom).

## Rebuilding from a fresh export

If you re-export your Apple Health data, regenerate the dashboard:

```bash
cd dashboard
python3 etl.py        # streams ../export.xml -> data/*.json  (a few minutes)
python3 build.py      # inlines ECharts + data -> sleep-dashboard.html
```

## Files

| File | Purpose |
|---|---|
| `sleep-dashboard.html` | **The shareable dashboard** (open this) |
| `etl.py` | Streaming parser: `export.xml` → `data/*.json` |
| `build.py` | Inlines ECharts + data into the single HTML |
| `template.html` | Dashboard markup + chart code (pre-inlining) |
| `data/` | Extracted JSON (nightly summary + per-night detail + stats) |
| `vendor/echarts.min.js` | Charting library (Apache ECharts, inlined at build) |

## Notes on the data

- Staged sleep (Deep/Core/REM) begins **Sep 2022** (Apple Watch). Earlier nights are
  duration-only and shown in the long-range trends/calendar.
- Overlapping data sources are deduplicated (Apple Watch preferred) so sleep time isn't
  double-counted.
- The dashboard presents data only — clinical interpretation is for your specialist.
