"""규칙 엔진. 텍스트를 받아 패턴 검출 결과와 자연도 등급을 낸다."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from . import metrics
from .grammar import GrammarReport
from .grammar import analyze_document as check_grammar
from .matchers import MATCHERS
from .rules import MetricRule, RegexRule, Rule, SpanRule, load_rules
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
    grammar: GrammarReport
    skipped_metrics: tuple[str, ...] = ()
    skipped_rules: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "grade": self.grade,
            "grade_reason": self.grade_reason,
            "counts": self.counts,
            "skipped_metrics": list(self.skipped_metrics),
            "skipped_rules": list(self.skipped_rules),
            "findings": [asdict(finding) for finding in self.findings],
            "grammar": self.grammar.to_dict(),
        }


def _snippet(source: str, start: int, end: int) -> str:
    left = max(0, start - SNIPPET_PAD)
    right = min(len(source), end + SNIPPET_PAD)
    return " ".join(source[left:right].split())


def _matches_in(
    rule: RegexRule | SpanRule, haystack: str, offset: int
) -> list[tuple[int, int]] | None:
    """매치 구간을 원문 좌표로 옮겨 반환한다."""
    if isinstance(rule, SpanRule):
        spans = MATCHERS[rule.matcher](haystack)
        if spans is None:
            return None
        return [(start + offset, end + offset) for start, end in spans]
    return [
        (match.start() + offset, match.end() + offset)
        for match in rule.pattern.finditer(haystack)
        if not (rule.exclude and rule.exclude.search(match.group(0)))
    ]


def _haystack(rule: RegexRule | SpanRule, document: Document) -> str:
    """규칙의 레이아웃 포함 여부에 따라 검출 문자열을 고른다."""
    return document.scrubbed if rule.sees_layout else document.prose


def _pattern_findings(
    rule: RegexRule | SpanRule, document: Document
) -> list[Finding] | None:
    haystack = _haystack(rule, document)
    if rule.scope == "document":
        spans = _matches_in(rule, haystack, 0)
        if spans is None:
            return None
        if len(spans) < rule.count:
            return []
        return [_matched_finding(rule, document.source, spans, None)]

    findings = []
    for index, paragraph in enumerate(document.paragraphs):
        chunk = haystack[paragraph.start : paragraph.end]
        spans = _matches_in(rule, chunk, paragraph.start)
        if spans is None:
            return None
        if len(spans) >= rule.count:
            location = Location(index=index, start=paragraph.start, end=paragraph.end)
            findings.append(_matched_finding(rule, document.source, spans, location))
    return findings


def _matched_finding(
    rule: RegexRule | SpanRule,
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
        autofixable=rule.has_autofix,
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
    context = metrics.context_of(document.prose)

    findings: list[Finding] = []
    skipped: list[str] = []
    skipped_rules: list[str] = []
    for rule in rules:
        if isinstance(rule, (RegexRule, SpanRule)):
            matched = _pattern_findings(rule, document)
            if matched is None:
                skipped_rules.append(f"{rule.id}:{rule.matcher}")
            else:
                findings.extend(matched)
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
        grammar=check_grammar(document),
        skipped_metrics=tuple(skipped),
        skipped_rules=tuple(skipped_rules),
    )
