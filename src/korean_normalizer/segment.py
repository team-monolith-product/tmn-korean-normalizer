"""텍스트를 규칙 적용 가능한 단위로 나누고, 건드리면 안 되는 구간을 표시한다."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

PLACEHOLDER = "\x00"

FENCED_CODE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]+`")
URL = re.compile(r"https?://\S+")
MARKDOWN_LINK_TARGET = re.compile(r"\]\([^)\s]+\)")
DIRECT_QUOTE = re.compile(r"[\"“][^\"”\n]{1,200}[\"”]")

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|\n+")
PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Span:
    """텍스트 내 구간. end는 배타적이다."""

    start: int
    end: int


@dataclass(frozen=True)
class Segment:
    """문단 또는 문장 하나."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Piece:
    """교정 대상 조각. protected면 원문 그대로 둔다."""

    text: str
    protected: bool


@dataclass(frozen=True)
class MaskMap:
    """검출·교정에서 제외할 구간.

    직접 인용을 검출까지 막으면 인용문 안의 AI 패턴을 보고할 수 없으므로
    두 층을 분리한다.
    """

    detect_free: tuple[Span, ...]
    fix_free: tuple[Span, ...]


def build_mask(text: str) -> MaskMap:
    detect_free = tuple(
        Span(match.start(), match.end())
        for pattern in (FENCED_CODE, INLINE_CODE, URL, MARKDOWN_LINK_TARGET)
        for match in pattern.finditer(text)
    )
    fix_free = tuple(
        Span(match.start(), match.end()) for match in DIRECT_QUOTE.finditer(text)
    )
    return MaskMap(detect_free=detect_free, fix_free=fix_free)


def scrub(text: str, mask: MaskMap) -> str:
    """검출 제외 구간을 자리표시자로 덮되 길이와 줄 구조는 보존한다.

    오프셋이 그대로라 원문에서 스니펫을 다시 잘라낼 수 있다.
    """
    chars = list(text)
    for span in mask.detect_free:
        for index in range(span.start, min(span.end, len(chars))):
            if chars[index] != "\n":
                chars[index] = PLACEHOLDER
    return "".join(chars)


def merge_spans(spans: Iterable[Span]) -> tuple[Span, ...]:
    merged: list[Span] = []
    for span in sorted(spans, key=lambda item: item.start):
        if merged and span.start <= merged[-1].end:
            merged[-1] = Span(merged[-1].start, max(merged[-1].end, span.end))
        else:
            merged.append(span)
    return tuple(merged)


def partition(text: str) -> tuple[Piece, ...]:
    """보호 구간을 기준으로 텍스트를 조각낸다.

    치환을 보호되지 않은 조각 안에서만 수행하면 경계를 넘는 매치가 아예
    만들어지지 않는다. 매치마다 구간이 겹치는지 되묻지 않아도 된다.
    """
    mask = build_mask(text)
    pieces: list[Piece] = []
    cursor = 0
    for span in merge_spans(mask.detect_free + mask.fix_free):
        if cursor < span.start:
            pieces.append(Piece(text[cursor : span.start], protected=False))
        pieces.append(Piece(text[span.start : span.end], protected=True))
        cursor = span.end
    if cursor < len(text):
        pieces.append(Piece(text[cursor:], protected=False))
    return tuple(pieces)


def _split(text: str, boundary: re.Pattern[str]) -> tuple[Segment, ...]:
    segments = []
    cursor = 0
    for match in boundary.finditer(text):
        chunk = text[cursor : match.start()]
        if chunk.strip():
            segments.append(_trimmed(text, cursor, match.start()))
        cursor = match.end()
    if text[cursor:].strip():
        segments.append(_trimmed(text, cursor, len(text)))
    return tuple(segments)


def _trimmed(text: str, start: int, end: int) -> Segment:
    chunk = text[start:end]
    lead = len(chunk) - len(chunk.lstrip())
    trail = len(chunk) - len(chunk.rstrip())
    return Segment(
        start=start + lead, end=end - trail, text=text[start + lead : end - trail]
    )


def split_paragraphs(text: str) -> tuple[Segment, ...]:
    return _split(text, PARAGRAPH_BOUNDARY)


def split_sentences(text: str) -> tuple[Segment, ...]:
    return _split(text, SENTENCE_BOUNDARY)


@dataclass(frozen=True)
class Document:
    """마스킹과 분절이 끝난 텍스트.

    검출과 교정이 같은 함수로 문단을 나누므로 문단 번호가 어긋날 수 없다.
    """

    source: str
    scrubbed: str
    paragraphs: tuple[Segment, ...]

    @classmethod
    def of(cls, text: str) -> Document:
        scrubbed = scrub(text, build_mask(text))
        return cls(
            source=text, scrubbed=scrubbed, paragraphs=split_paragraphs(scrubbed)
        )
