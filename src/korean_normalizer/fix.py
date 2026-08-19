"""Tier A 자동 교정. 의미 판단이 필요 없는 규칙만 적용한다.

교정은 검출이 실제로 임계를 넘긴 자리에서만 일어난다. 임계를 무시하고
전역 치환하면 1회 등장이 자연스러운 표현까지 건드리게 된다.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import asdict, dataclass

from .detect import analyze_document
from .josa import agree
from .rules import AutoFix, Rule, load_rules
from .segment import Document, overlaps, protected_spans

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
    """보호 구간과 겹치는 매치를 건너뛰며 한 번 치환한다.

    보호 구간을 기준으로 텍스트를 미리 조각내면 안 된다. 조각 경계를
    ^ $ 앵커가 줄 끝으로 착각해 줄 중간의 콜론까지 고친다.
    sub는 입력 문자열 기준 오프셋을 주므로 같은 문자열에서 뜬 구간과
    좌표계가 맞는다. 패스가 끝나면 구간을 다시 뜬다.
    """
    protected = protected_spans(text)
    replaced = 0

    def render(match) -> str:
        nonlocal replaced
        if overlaps(protected, match.start(), match.end()):
            return match.group(0)
        replaced += 1
        return _expand(entry, match)

    return entry.pattern.sub(render, text), replaced


def _run(text: str, rules: list[Rule]) -> tuple[str, Counter[int]]:
    """한 규칙의 교정이 다른 규칙의 대상을 만들 수 있어 안정될 때까지 돈다."""
    counts: Counter[int] = Counter()
    current = text
    for _ in range(MAX_PASSES):
        before = current
        for rule in rules:
            for entry in rule.autofix:
                current, replaced = _substitute(current, entry)
                counts[rule.id] += replaced
        if current == before:
            break
    return current, Counter({rule_id: n for rule_id, n in counts.items() if n})


def _autofix_targets(document: Document, rules: tuple[Rule, ...]):
    """자동 교정 규칙을 문서 단위와 문단 단위로 나눈다."""
    everywhere: set[int] = set()
    per_paragraph: dict[int, set[int]] = {}
    for finding in analyze_document(document, rules).findings:
        if not finding.autofixable:
            continue
        if finding.location is None:
            everywhere.add(finding.rule_id)
        else:
            per_paragraph.setdefault(finding.location.index, set()).add(finding.rule_id)
    return everywhere, per_paragraph


def apply(text: str, rules: tuple[Rule, ...] | None = None) -> FixResult:
    r"""문단 하나씩 교정하고 사이의 빈 줄은 손대지 않고 붙인다.

    문단을 나누지 않으면 치환 패턴의 꼬리 `\s*`가 문단 사이 빈 줄을 먹는다.
    '결론적으로,\n\n다음'에서 결말 관용구를 지우면 두 문단이 한 문단으로
    합쳐진다. 문단 스코프 규칙이 하나도 없어도 이 순회는 지울 수 없다.
    """
    rules = rules if rules is not None else load_rules()
    by_id = {rule.id: rule for rule in rules}
    document = Document.of(text)
    document_rules, paragraph_rules = _autofix_targets(document, rules)

    counts: Counter[int] = Counter()
    pieces: list[str] = []
    cursor = 0

    for index, paragraph in enumerate(document.paragraphs):
        active = sorted(document_rules | paragraph_rules.get(index, set()))
        fixed, chunk_counts = _run(
            text[paragraph.start : paragraph.end],
            [by_id[rule_id] for rule_id in active],
        )
        pieces.extend((text[cursor : paragraph.start], fixed))
        counts += chunk_counts
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
