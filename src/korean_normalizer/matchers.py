"""형태소 경계가 필요한 구문을 원문 구간으로 검출한다."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from .morphology import get_analyzer

if TYPE_CHECKING:
    from kiwipiepy import Kiwi

DOT = re.compile("[·ㆍ∙•]")
WORD = re.compile(r"\w+(?:[-/]\w+)*(?:\([^()\n]*\))?")
CLAUSE_ENDINGS = {"EC", "EF"}
PHRASE_BOUNDARIES = {"JKS", "JKC", "JKO", "JKB", "JX", "JC", "MAJ"}


def _tags(word: str, analyzer: Kiwi) -> set[str]:
    return {token.tag.split("-", 1)[0] for token in analyzer.tokenize(word)}


def _is_item(text: str, analyzer: Kiwi) -> bool:
    """구분점 사이에 조사로 연결된 다음 구문이나 문장이 끼었는지 본다."""
    words = list(WORD.finditer(text))
    if not words:
        return False
    cursor = 0
    for word in words:
        if text[cursor : word.start()].strip(" \t"):
            return False
        cursor = word.end()
    if text[cursor:].strip(" \t"):
        return False
    for token in analyzer.tokenize(text):
        tag = token.tag.split("-", 1)[0]
        if tag in CLAUSE_ENDINGS:
            return False
        if tag in PHRASE_BOUNDARIES and token.start < words[-1].start():
            return False
    return True


def _left_edge(text: str, analyzer: Kiwi) -> int | None:
    words = list(WORD.finditer(text))
    if not words or text[words[-1].end() :].strip(" \t"):
        return None
    start = words[-1].start()
    cursor = words[-1].end()
    for word in reversed(words):
        if text[word.end() : cursor].strip(" \t"):
            break
        if _tags(word[0], analyzer) & (PHRASE_BOUNDARIES | CLAUSE_ENDINGS):
            break
        start = word.start()
        cursor = word.start()
    return start


def _right_edge(text: str, analyzer: Kiwi) -> int | None:
    end = None
    for word in WORD.finditer(text):
        if text[end or 0 : word.start()].strip(" \t"):
            break
        tags = _tags(word[0], analyzer)
        if end is not None and tags & (CLAUSE_ENDINGS | {"MAJ"}):
            break
        end = word.end()
        if tags & (PHRASE_BOUNDARIES | CLAUSE_ENDINGS):
            break
    return end


def middle_dot_enumerations(text: str) -> list[tuple[int, int]] | None:
    analyzer = get_analyzer()
    if analyzer is None:
        return None
    dots = []
    for dot in DOT.finditer(text):
        left, right = dot.start() - 1, dot.end()
        while left >= 0 and text[left] in " \t":
            left -= 1
        while right < len(text) and text[right] in " \t":
            right += 1
        if (
            left >= 0
            and right < len(text)
            and (text[left].isalnum() or text[left] in "_)")
            and (text[right].isalnum() or text[right] == "_")
        ):
            dots.append(dot)
    spans = []
    first = 0
    for index, dot in enumerate(dots):
        next_dot = dots[index + 1] if index + 1 < len(dots) else None
        if next_dot and _is_item(text[dot.end() : next_dot.start()], analyzer):
            continue
        if index > first:
            left_bound = dots[first - 1].end() if first else 0
            right_bound = next_dot.start() if next_dot else len(text)
            start = _left_edge(text[left_bound : dots[first].start()], analyzer)
            end = _right_edge(text[dot.end() : right_bound], analyzer)
            if start is not None and end is not None:
                spans.append((left_bound + start, dot.end() + end))
        first = index + 1
    return spans


Matcher = Callable[[str], list[tuple[int, int]] | None]
MATCHERS: dict[str, Matcher] = {"middle_dot_enumeration": middle_dot_enumerations}
