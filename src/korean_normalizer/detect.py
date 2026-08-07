"""규칙 엔진. 텍스트를 받아 패턴 검출 결과와 자연도 등급을 낸다."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import metrics
from .rules import Rule, load_rules
from .segment import build_mask, scrub, split_paragraphs

MAX_SAMPLES = 5
SNIPPET_PAD = 12


@dataclass(frozen=True)
class Sample:
    start: int
    end: int
    snippet: str


@dataclass(frozen=True)
class Finding:
    rule_id: int
    name: str
    category: str
    severity: str
    scope: str
    count: int
    threshold: int
    guidance: str
    autofixable: bool
    paragraph_index: int | None = None
    metric_value: float | None = None
    samples: tuple[Sample, ...] = ()


@dataclass(frozen=True)
class Report:
    grade: str
    grade_reason: str
    counts: dict[str, int]
    findings: tuple[Finding, ...]
    skipped_metrics: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict:
        return {
            "grade": self.grade,
            "grade_reason": self.grade_reason,
            "counts": self.counts,
            "skipped_metrics": list(self.skipped_metrics),
            "findings": [asdict(finding) for finding in self.findings],
        }


def _snippet(source: str, start: int, end: int) -> str:
    left = max(0, start - SNIPPET_PAD)
    right = min(len(source), end + SNIPPET_PAD)
    return " ".join(source[left:right].split())


def _samples(source: str, spans: list[tuple[int, int]]) -> tuple[Sample, ...]:
    return tuple(
        Sample(start=start, end=end, snippet=_snippet(source, start, end))
        for start, end in spans[:MAX_SAMPLES]
    )


def _matches_in(rule: Rule, haystack: str, offset: int) -> list[tuple[int, int]]:
    """매치 구간을 원문 좌표로 옮겨 반환한다."""
    assert rule.pattern is not None
    return [
        (match.start() + offset, match.end() + offset)
        for match in rule.pattern.finditer(haystack)
        if not (rule.exclude and rule.exclude.search(match.group(0)))
    ]


def _regex_findings(rule: Rule, source: str, scrubbed: str) -> list[Finding]:
    if rule.scope == "document":
        matches = _matches_in(rule, scrubbed, 0)
        if len(matches) < rule.count:
            return []
        return [_finding(rule, source, matches, None)]

    findings = []
    for index, paragraph in enumerate(split_paragraphs(scrubbed)):
        matches = _matches_in(rule, paragraph.text, paragraph.start)
        if len(matches) >= rule.count:
            findings.append(_finding(rule, source, matches, index))
    return findings


def _finding(
    rule: Rule,
    source: str,
    spans: list[tuple[int, int]],
    paragraph_index: int | None,
) -> Finding:
    return Finding(
        rule_id=rule.id,
        name=rule.name,
        category=rule.category,
        severity=rule.severity,
        scope=rule.scope,
        count=len(spans),
        threshold=rule.count,
        guidance=rule.guidance,
        autofixable=rule.has_autofix,
        paragraph_index=paragraph_index,
        samples=_samples(source, spans),
    )


_COMPARATORS = {
    "gt": lambda value, bound: value > bound,
    "gte": lambda value, bound: value >= bound,
    "lt": lambda value, bound: value < bound,
    "lte": lambda value, bound: value <= bound,
}


def _breaches(value: float, bound: dict[str, float]) -> bool:
    return all(
        _COMPARATORS[operator](value, limit)
        for operator, limit in bound.items()
        if operator in _COMPARATORS
    )


def _metric_finding(
    rule: Rule, context: metrics.MetricContext
) -> tuple[Finding | None, bool]:
    assert rule.metric is not None and rule.metric_bound is not None
    value = metrics.compute(rule.metric, context)
    if value is None:
        return None, True
    if not _breaches(value, rule.metric_bound):
        return None, False
    return (
        Finding(
            rule_id=rule.id,
            name=rule.name,
            category=rule.category,
            severity=rule.severity,
            scope="document",
            count=1,
            threshold=1,
            guidance=rule.guidance,
            autofixable=False,
            metric_value=round(value, 4),
        ),
        False,
    )


def grade(counts: dict[str, int]) -> tuple[str, str]:
    """SKILL.md의 자연도 등급 정의를 그대로 옮긴다."""
    s1 = counts.get("S1", 0)
    s2 = counts.get("S2", 0)
    if s1 >= 5 and s2 >= 8:
        return "D", f"S1 {s1}건과 S2 {s2}건이 겹쳐 다중 카테고리 위반"
    if s1 >= 3 or s2 >= 6:
        return "C", f"S1 {s1}건, S2 {s2}건으로 AI 흔적이 뚜렷함"
    if s1 >= 1 or s2 >= 3:
        return "B", f"S1 {s1}건, S2 {s2}건으로 사소한 AI 흔적이 남음"
    return "A", f"S1 0건, S2 {s2}건으로 자연스러움"


def analyze(text: str, rules: tuple[Rule, ...] | None = None) -> Report:
    rules = rules if rules is not None else load_rules()
    scrubbed = scrub(text, build_mask(text))
    context = metrics.context_of(scrubbed)

    findings: list[Finding] = []
    skipped: list[str] = []
    for rule in rules:
        if rule.kind == "regex":
            findings.extend(_regex_findings(rule, text, scrubbed))
            continue
        finding, was_skipped = _metric_finding(rule, context)
        if was_skipped:
            skipped.append(f"{rule.id}:{rule.metric}")
        elif finding is not None:
            findings.append(finding)

    findings.sort(key=lambda item: (item.severity, item.rule_id))
    counts = {
        severity: sum(1 for item in findings if item.severity == severity)
        for severity in ("S1", "S2", "S3")
    }
    label, reason = grade(counts)
    return Report(
        grade=label,
        grade_reason=reason,
        counts=counts,
        findings=tuple(findings),
        skipped_metrics=tuple(skipped),
    )
