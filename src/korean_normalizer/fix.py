"""Tier A 자동 교정. 의미 판단이 필요 없는 규칙만 적용한다.

교정은 검출이 실제로 임계를 넘긴 자리에서만 일어난다. 임계를 무시하고
전역 치환하면 1회 등장이 자연스러운 표현까지 건드리게 된다.
"""

from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass

from .detect import analyze
from .josa import agree
from .rules import AutoFix, Rule, load_rules
from .segment import Document, partition

MAX_PASSES = 3


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
            "changes": [asdict(change) for change in self.changes],
        }


def _expand(entry: AutoFix, match) -> str:
    head = match.expand(entry.replacement)
    if entry.josa_group is None:
        return head
    return head + agree(head, match.group(entry.josa_group) or "")


def _substitute(text: str, entry: AutoFix) -> tuple[str, int]:
    replaced = 0

    def render(match) -> str:
        nonlocal replaced
        replaced += 1
        return _expand(entry, match)

    return entry.pattern.sub(render, text), replaced


def _run(text: str, rules: list[Rule], counts: dict[int, int]) -> str:
    """한 규칙의 교정이 다른 규칙의 대상을 만들 수 있어 안정될 때까지 돈다."""
    current = text
    for _ in range(MAX_PASSES):
        before = current
        for rule in rules:
            for entry in rule.autofix:
                current, replaced = _substitute(current, entry)
                if replaced:
                    counts[rule.id] = counts.get(rule.id, 0) + replaced
        if current == before:
            break
    return current


def _fix_chunk(chunk: str, rules: list[Rule], counts: dict[int, int]) -> str:
    """보호 조각은 그대로 두고 나머지에만 규칙을 적용한다."""
    return "".join(
        piece.text if piece.protected else _run(piece.text, rules, counts)
        for piece in partition(chunk)
    )


def _autofix_targets(text: str, rules: tuple[Rule, ...]):
    """자동 교정 규칙을 문서 단위와 문단 단위로 나눈다."""
    document: set[int] = set()
    paragraph: dict[int, set[int]] = {}
    for finding in analyze(text, rules).findings:
        if not finding.autofixable:
            continue
        if finding.location is None:
            document.add(finding.rule_id)
        else:
            paragraph.setdefault(finding.location.index, set()).add(finding.rule_id)
    return document, paragraph


def apply(text: str, rules: tuple[Rule, ...] | None = None) -> FixResult:
    rules = rules if rules is not None else load_rules()
    by_id = {rule.id: rule for rule in rules}
    document_rules, paragraph_rules = _autofix_targets(text, rules)

    counts: dict[int, int] = {}
    pieces: list[str] = []
    cursor = 0

    for index, paragraph in enumerate(Document.of(text).paragraphs):
        active = sorted(document_rules | paragraph_rules.get(index, set()))
        pieces.append(text[cursor : paragraph.start])
        pieces.append(
            _fix_chunk(
                text[paragraph.start : paragraph.end],
                [by_id[rule_id] for rule_id in active],
                counts,
            )
        )
        cursor = paragraph.end
    pieces.append(text[cursor:])

    changes = tuple(
        Change(rule_id=rule_id, name=by_id[rule_id].name, replacements=count)
        for rule_id, count in sorted(counts.items())
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
