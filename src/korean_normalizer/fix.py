"""Tier A 자동 교정. 의미 판단이 필요 없는 규칙만 적용한다.

교정은 검출이 실제로 임계를 넘긴 자리에서만 일어난다. 임계를 무시하고
전역 치환하면 1회 등장이 자연스러운 표현까지 건드리게 된다.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .detect import analyze
from .josa import agree
from .rules import AutoFix, Rule, load_rules
from .segment import build_mask, scrub, split_paragraphs


@dataclass(frozen=True)
class Change:
    rule_id: int
    name: str
    replacements: int


@dataclass(frozen=True)
class FixResult:
    text: str
    changes: tuple[Change, ...]

    @property
    def replaced(self) -> int:
        return sum(change.replacements for change in self.changes)

    def to_dict(self) -> dict:
        return {
            "replacements": self.replaced,
            "changes": [
                {
                    "rule_id": change.rule_id,
                    "name": change.name,
                    "replacements": change.replacements,
                }
                for change in self.changes
            ],
        }


def _expand(entry: AutoFix, match) -> str:
    head = match.expand(entry.replacement)
    if entry.josa_group is None:
        return head
    josa = match.group(entry.josa_group) or ""
    return head + agree(head, josa)


def _apply_entry(text: str, entry: AutoFix) -> tuple[str, int]:
    """보호 구간을 건너뛰며 한 번 치환한다.

    sub는 입력 문자열 기준 오프셋을 주므로 같은 문자열에서 만든 마스크와
    좌표계가 일치한다.
    """
    mask = build_mask(text)
    replaced = 0

    def substitute(match) -> str:
        nonlocal replaced
        if mask.is_fix_free(match.start(), match.end()):
            return match.group(0)
        replaced += 1
        return _expand(entry, match)

    return entry.pattern.sub(substitute, text), replaced


MAX_PASSES = 3


def _apply_rules(text: str, rules: list[Rule]) -> tuple[str, dict[int, int]]:
    """한 규칙의 교정이 다른 규칙의 대상을 만들 수 있어 안정될 때까지 돈다."""
    counts: dict[int, int] = {}
    current = text
    for _ in range(MAX_PASSES):
        before = current
        for rule in rules:
            for entry in rule.autofix:
                current, replaced = _apply_entry(current, entry)
                if replaced:
                    counts[rule.id] = counts.get(rule.id, 0) + replaced
        if current == before:
            break
    return current, counts


def _triggered(text: str, rules: tuple[Rule, ...]):
    """검출 결과를 문서 단위와 문단 단위 규칙 집합으로 나눈다."""
    report = analyze(text, rules)
    document: set[int] = set()
    paragraph: dict[int, set[int]] = {}
    for finding in report.findings:
        if not finding.autofixable:
            continue
        if finding.paragraph_index is None:
            document.add(finding.rule_id)
        else:
            paragraph.setdefault(finding.paragraph_index, set()).add(finding.rule_id)
    return document, paragraph


def apply(text: str, rules: tuple[Rule, ...] | None = None) -> FixResult:
    rules = rules if rules is not None else load_rules()
    by_id = {rule.id: rule for rule in rules}
    document, per_paragraph = _triggered(text, rules)

    segments = split_paragraphs(scrub(text, build_mask(text)))
    totals: dict[int, int] = {}
    pieces: list[str] = []
    cursor = 0

    for index, segment in enumerate(segments):
        pieces.append(text[cursor : segment.start])
        active = sorted(document | per_paragraph.get(index, set()))
        chunk, counts = _apply_rules(
            text[segment.start : segment.end], [by_id[rule_id] for rule_id in active]
        )
        pieces.append(chunk)
        for rule_id, count in counts.items():
            totals[rule_id] = totals.get(rule_id, 0) + count
        cursor = segment.end

    pieces.append(text[cursor:])
    changes = tuple(
        Change(rule_id=rule_id, name=by_id[rule_id].name, replacements=count)
        for rule_id, count in sorted(totals.items())
    )
    return FixResult(text="".join(pieces), changes=changes)


def diff(before: str, after: str, label: str = "text") -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
        )
    )
