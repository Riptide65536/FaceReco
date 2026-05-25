from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _status_text(ok: bool | None) -> str:
    if ok is None:
        return "N/A"
    return "PASS" if ok else "FAIL"


def _extract_perf_error(stage4: dict[str, Any] | None) -> str | None:
    if not stage4:
        return None
    for step in stage4.get("steps", []):
        cmd = str(step.get("cmd", ""))
        if "perf_check.py" in cmd and int(step.get("code", 0)) != 0:
            stderr = str(step.get("stderr", "")).strip()
            stdout = str(step.get("stdout", "")).strip()
            return stderr or stdout or "perf step failed"
    return None


def build_markdown(
    stage4: dict[str, Any] | None,
    blackbox: dict[str, Any] | None,
    whitebox: dict[str, Any] | None,
    perf: dict[str, Any] | None,
) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    stage4_ok = stage4.get("passed") if stage4 else None
    blackbox_ok = blackbox.get("passed") if blackbox else None
    whitebox_ok = whitebox.get("passed") if whitebox else None
    perf_ok = None
    perf_error = None
    if perf:
        perf_ok = perf.get("pass_single_response_le_1000ms")
        if perf_ok is None and "error" not in perf:
            perf_ok = True
    else:
        perf_error = _extract_perf_error(stage4)

    lines: list[str] = []
    lines.append("# Stage 4 验收报告")
    lines.append("")
    lines.append(f"- 生成时间: {now}")
    lines.append(f"- 总体验收: {_status_text(bool(stage4_ok) if stage4_ok is not None else None)}")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| 检查项 | 状态 | 备注 |")
    lines.append("|---|---|---|")
    lines.append(
        f"| stage4_check 总流程 | {_status_text(stage4_ok)} | "
        f"{(str(stage4.get('failed_count', 'N/A')) + ' failed') if stage4 else '未提供 stage4 json'} |"
    )
    lines.append(
        f"| 黑盒业务场景 | {_status_text(blackbox_ok)} | "
        f"{(str(blackbox.get('passed_count', 0)) + '/' + str(blackbox.get('scenario_count', 0)) + ' passed') if blackbox else '未执行或未生成报告'} |"
    )
    lines.append(
        f"| 白盒并发巡检 | {_status_text(whitebox_ok)} | "
        f"{('errors=' + str(whitebox.get('error_count', 'N/A')) + ', mem=' + str(whitebox.get('memory_growth_mb', 'N/A')) + 'MB') if whitebox else '未执行或未生成报告'} |"
    )
    lines.append(
        f"| 性能检查 | {_status_text(perf_ok)} | "
        f"{('fps=' + str(round(float(perf.get('effective_fps', 0.0)), 2)) + ', max=' + str(round(float(perf.get('max_latency_ms', 0.0)), 2)) + 'ms') if perf and 'max_latency_ms' in perf else ('稳定性模式或未执行' if perf else ('失败: ' + perf_error[:80]) if perf_error else '未执行或未生成报告')} |"
    )
    lines.append("")

    lines.append("## 详细结果")
    lines.append("")
    if stage4:
        lines.append("### stage4_check")
        lines.append("")
        lines.append(f"- step_count: {stage4.get('step_count')}")
        lines.append(f"- failed_count: {stage4.get('failed_count')}")
        for idx, step in enumerate(stage4.get("steps", []), start=1):
            lines.append(f"- Step {idx}: code={step.get('code')} cmd=`{step.get('cmd', '')}`")
        lines.append("")

    if blackbox:
        lines.append("### 黑盒检查")
        lines.append("")
        for item in blackbox.get("details", []):
            mark = "PASS" if item.get("passed") else "FAIL"
            lines.append(f"- {mark} {item.get('name')}: {item.get('message')}")
        lines.append("")

    if whitebox:
        lines.append("### 白盒检查")
        lines.append("")
        lines.append(f"- threads: {whitebox.get('threads')}")
        lines.append(f"- loops_per_thread: {whitebox.get('loops_per_thread')}")
        lines.append(f"- timed_out: {whitebox.get('timed_out')}")
        lines.append(f"- error_count: {whitebox.get('error_count')}")
        lines.append(f"- memory_growth_mb: {whitebox.get('memory_growth_mb')}")
        lines.append("")

    if perf:
        lines.append("### 性能检查")
        lines.append("")
    elif perf_error:
        lines.append("### 性能检查")
        lines.append("")
        lines.append(f"- 失败原因: {perf_error}")
        lines.append("")
        if "error" in perf:
            lines.append(f"- error: {perf.get('error')}")
        else:
            if "effective_fps" in perf:
                lines.append(f"- effective_fps: {perf.get('effective_fps')}")
            if "avg_effective_fps" in perf:
                lines.append(f"- avg_effective_fps: {perf.get('avg_effective_fps')}")
            if "max_latency_ms" in perf:
                lines.append(f"- max_latency_ms: {perf.get('max_latency_ms')}")
            if "worst_max_latency_ms" in perf:
                lines.append(f"- worst_max_latency_ms: {perf.get('worst_max_latency_ms')}")
            if "p95_latency_ms" in perf:
                lines.append(f"- p95_latency_ms: {perf.get('p95_latency_ms')}")
            if "worst_p95_latency_ms" in perf:
                lines.append(f"- worst_p95_latency_ms: {perf.get('worst_p95_latency_ms')}")
            if "pass_single_response_le_1000ms" in perf:
                lines.append(f"- pass_single_response_le_1000ms: {perf.get('pass_single_response_le_1000ms')}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate stage-4 acceptance markdown report")
    parser.add_argument("--stage4-json", default=str(ROOT / "reports" / "stage4_check_report.json"))
    parser.add_argument("--blackbox-json", default=str(ROOT / "reports" / "blackbox_check_report.json"))
    parser.add_argument("--whitebox-json", default=str(ROOT / "reports" / "whitebox_check_report.json"))
    parser.add_argument("--perf-json", default=str(ROOT / "reports" / "perf_stage4.json"))
    parser.add_argument("--output-md", default=str(ROOT / "reports" / "stage4_acceptance_report.md"))
    args = parser.parse_args()

    stage4 = _load_json(Path(args.stage4_json))
    blackbox = _load_json(Path(args.blackbox_json))
    whitebox = _load_json(Path(args.whitebox_json))
    perf = _load_json(Path(args.perf_json))

    md = build_markdown(stage4, blackbox, whitebox, perf)
    out = Path(args.output_md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"[stage4-report] markdown saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
