"""명령행 진입점."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import fix as fix_module
from .detect import Finding, Report, analyze
from .rules import load_rules

SEVERITY_ORDER = ("S1", "S2", "S3")


def _read(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    try:
        with Path(path).open(encoding="utf-8", newline="") as stream:
            return stream.read()
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"입력을 읽을 수 없습니다: {path} ({error})") from error


def _render_finding(finding: Finding) -> list[str]:
    where = (
        "문서 전체"
        if finding.location is None
        else f"문단 {finding.location.index + 1}"
    )
    detail = (
        f"지표 {finding.metric_value}"
        if finding.metric_value is not None
        else f"{finding.count}회 (임계 {finding.threshold})"
    )
    marker = " [자동교정]" if finding.autofixable else ""
    return [
        f"[{finding.severity}] 패턴 {finding.rule_id} {finding.name}"
        f" — {where}, {detail}{marker}",
        f"    지침: {finding.guidance}",
        *(f"    · {sample.snippet}" for sample in finding.samples),
    ]


def _render_report(report: Report) -> str:
    lines = [
        f"자연도 등급: {report.grade} — {report.grade_reason}",
        "감지 요약: "
        + ", ".join(
            f"{severity} {report.counts.get(severity, 0)}건"
            for severity in SEVERITY_ORDER
        ),
        "",
    ]
    if not report.findings:
        lines.append("검출된 AI 문체 패턴이 없습니다.")
    for finding in report.findings:
        lines.extend(_render_finding(finding))
    lines.append("")
    if report.grammar.skipped:
        lines.append("비문 검사 건너뜀: kiwipiepy가 필요합니다 (pos 추가 의존성).")
    else:
        counts = report.grammar.counts
        lines.append(
            f"비문 검사: 오류 {counts['error']}건, 검토 후보 {counts['review']}건"
        )
        for finding in report.grammar.findings:
            lines.extend(
                [
                    f"[{finding.severity}] {finding.rule_id} "
                    f"{finding.line}행 {finding.column}열: {finding.text}",
                    f"    이유: {finding.message}",
                    f"    수정 후보: {finding.suggestion}",
                ]
            )
    if report.skipped_metrics:
        lines.append("")
        lines.append(
            "표본 부족 또는 의존성 없음으로 건너뛴 지표: "
            + ", ".join(report.skipped_metrics)
        )
    return "\n".join(lines)


def _detect(args: argparse.Namespace) -> int:
    report = analyze(_read(args.path))
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_render_report(report))
    found = bool(report.findings or report.grammar.findings)
    return 1 if args.fail_on_finding and found else 0


def _fix(args: argparse.Namespace) -> int:
    original = _read(args.path)
    result = fix_module.apply(original)

    if args.diff:
        print(fix_module.diff(original, result.text, args.path or "stdin"), end="")
    elif args.in_place:
        if args.path in (None, "-"):
            raise SystemExit("--in-place는 파일 경로가 필요합니다")
        Path(args.path).write_text(result.text, encoding="utf-8")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.text, end="")
    return 0


def _rules(args: argparse.Namespace) -> int:
    if args.format == "json":
        rows = [
            {
                "id": rule.id,
                "name": rule.name,
                "category": rule.category,
                "severity": rule.severity,
                "kind": rule.kind,
                "tier": rule.tier,
                "autofix": rule.has_autofix,
            }
            for rule in load_rules()
        ]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for rule in load_rules():
        print(
            f"{rule.id:>2} [{rule.severity}] tier {rule.tier}"
            f" {rule.name} ({rule.category}/{rule.kind})"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="korean-normalizer",
        description="한국어 AI 작문 패턴을 규칙으로 검출하고 교정한다.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect", help="패턴 검출과 자연도 등급 산출")
    detect.add_argument("path", nargs="?", help="입력 파일. 생략하면 표준 입력")
    detect.add_argument("--format", choices=("text", "json"), default="text")
    detect.add_argument(
        "--fail-on-finding",
        action="store_true",
        help="검출이 하나라도 있으면 종료 코드 1",
    )
    detect.set_defaults(handler=_detect)

    fix = sub.add_parser("fix", help="Tier A 규칙 자동 교정")
    fix.add_argument("path", nargs="?", help="입력 파일. 생략하면 표준 입력")
    fix.add_argument("--in-place", action="store_true", help="파일을 직접 수정")
    fix.add_argument("--diff", action="store_true", help="교정 결과를 diff로 출력")
    fix.set_defaults(handler=_fix)

    rules = sub.add_parser("rules", help="규칙 목록 출력")
    rules.add_argument("--format", choices=("text", "json"), default="text")
    rules.set_defaults(handler=_rules)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
