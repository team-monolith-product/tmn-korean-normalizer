"""규칙 엔진. 텍스트를 받아 패턴 검출 결과와 자연도 등급을 낸다."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from . import metrics
from .rules import MetricRule, RegexRule, Rule, load_rules
from .segment import Document

MAX_SAMPLES = 5
SNIPPET_PAD = 12


@dataclass(frozen=True)
class Sample:
    start: int
    end: int
    snippet: str


@dataclass(frozen=True)
class Location:
    """검출이 일어난 문단. index는 0부터 세고 start/end는 원문 오프셋이다."""

    index: int
    start: int
    end: int


@dataclass(frozen=True)
class Finding:
    rule_id: int
    name: str
    category: str
    severity: str
    guidance: str
    autofixable: bool
    location: Location | None = None
    count: int | None = None
    threshold: int | None = None
    metric_value: float | None = None
    samples: tuple[Sample, ...] = ()


@dataclass(frozen=True)
class Report:
    grade: str
    grade_reason: str
    counts: dict[str, int]
    findings: tuple[Finding, ...]
    skipped_metrics: tuple[str, ...] = ()

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


def _matches_in(rule: RegexRule, haystack: str, offset: int) -> list[tuple[int, int]]:
    """매치 구간을 원문 좌표로 옮겨 반환한다."""
    return [
        (match.start() + offset, match.end() + offset)
        for match in rule.pattern.finditer(haystack)
        if not (rule.exclude and rule.exclude.search(match.group(0)))
    ]


def _regex_findings(rule: RegexRule, document: Document) -> list[Finding]:
    if rule.scope == "document":
        spans = _matches_in(rule, document.scrubbed, 0)
        if len(spans) < rule.count:
            return []
        return [_regex_finding(rule, document.source, spans, None)]

    findings = []
    for index, paragraph in enumerate(document.paragraphs):
        spans = _matches_in(rule, paragraph.text, paragraph.start)
        if len(spans) >= rule.count:
            location = Location(index=index, start=paragraph.start, end=paragraph.end)
            findings.append(_regex_finding(rule, document.source, spans, location))
    return findings


def _regex_finding(
    rule: RegexRule,
    source: str,
    spans: list[tuple[int, int]],
    location: Location | None,
) -> Finding:
    return Finding(
        rule_id=rule.id,
        name=rule.name,
        category=rule.category,
        severity=rule.severity,
        guidance=rule.guidance,
        autofixable=rule.has_autofix,
        location=location,
        count=len(spans),
        threshold=rule.count,
        samples=tuple(
            Sample(start=start, end=end, snippet=_snippet(source, start, end))
            for start, end in spans[:MAX_SAMPLES]
        ),
    )


def _metric_finding(rule: MetricRule, value: float) -> Finding:
    return Finding(
        rule_id=rule.id,
        name=rule.name,
        category=rule.category,
        severity=rule.severity,
        guidance=rule.guidance,
        autofixable=False,
        metric_value=round(value, 4),
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
    return analyze_document(Document.of(text), rules)


def analyze_document(
    document: Document, rules: tuple[Rule, ...] | None = None
) -> Report:
    """이미 분절된 문서를 분석한다. 교정 쪽에서 문서를 두 번 만들지 않도록 나눴다."""
    rules = rules if rules is not None else load_rules()
    context = metrics.context_of(document.scrubbed)

    findings: list[Finding] = []
    skipped: list[str] = []
    for rule in rules:
        if isinstance(rule, RegexRule):
            findings.extend(_regex_findings(rule, document))
            continue
        value = metrics.compute(rule.metric, context)
        if value is None:
            skipped.append(f"{rule.id}:{rule.metric}")
        elif rule.bound.breached_by(value):
            findings.append(_metric_finding(rule, value))

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
