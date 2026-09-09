"""VISTAAR Load-Testing — turns a k6 JSON summary into a short Markdown
report (Phase 20's "result/reporting tooling").

k6's own `handleSummary()` (main.js) writes
reports/summary-<stage>-<timestamp>.json for every run — this script
reads one of those and produces a human-readable pass/fail report
against the thresholds already defined in main.js, without needing any
new dependency (stdlib json only).

Usage:
    python analyze_summary.py summary-smoke-1234567890.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}ms"


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {Path(__file__).name} <summary.json>", file=sys.stderr)
        raise SystemExit(1)

    summary_path = Path(sys.argv[1])
    data = json.loads(summary_path.read_text())
    metrics = data.get("metrics", {})

    lines = [
        f"# VISTAAR Load Test Report — {summary_path.name}",
        "",
        "| Metric | Value |",
        "| :-- | :-- |",
    ]

    for name, metric in sorted(metrics.items()):
        values = metric.get("values", {})
        if "p(95)" in values:
            lines.append(
                f"| `{name}` | p50={_fmt_ms(values.get('med'))} "
                f"p95={_fmt_ms(values.get('p(95)'))} "
                f"p99={_fmt_ms(values.get('p(99)'))} |"
            )
        elif "rate" in values:
            lines.append(f"| `{name}` | rate={values['rate'] * 100:.2f}% |")
        elif "count" in values:
            lines.append(f"| `{name}` | count={values['count']} |")

    lines += ["", "## Threshold results", ""]
    thresholds_failed = False
    for name, metric in sorted(metrics.items()):
        for threshold_expr, result in (metric.get("thresholds") or {}).items():
            status = "PASS" if result.get("ok") else "FAIL"
            if not result.get("ok"):
                thresholds_failed = True
            lines.append(f"- `{name}` {threshold_expr}: **{status}**")

    overall = "FAILED — see failures above" if thresholds_failed else "PASSED"
    lines += ["", f"## Overall: {overall}"]

    report_path = summary_path.with_suffix(".md")
    report_path.write_text("\n".join(lines))
    print(f"Wrote {report_path}")
    if thresholds_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
