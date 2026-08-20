"""텍스트를 규칙 적용 가능한 단위로 나누고, 건드리면 안 되는 구간을 표시한다."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

PLACEHOLDER = "\x00"

FENCED_CODE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]+`")
MATH_BLOCK = re.compile(r"\\\[.*?\\\]|\$\$.*?\$\$", re.DOTALL)
MATH_INLINE = re.compile(r"\\\([^\n]*?\\\)")
URL = re.compile(r"https?://\S+")
MARKDOWN_LINK_TARGET = re.compile(r"\]\([^)\s]+\)")
TABLE_ROW = re.compile(r"^[ \t]*\|.*$", re.MULTILINE)
HEADING = re.compile(r"^[ \t]*#{1,6} .*$", re.MULTILINE)
DIRECT_QUOTE = re.compile(r"[\"“][^\"”\n]{1,200}[\"”]")

# 숫자 뒤 마침표는 목록 번호나 날짜·버전 표기지 문장 끝이 아니다.
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])(?<![0-9]\.)\s+|\n+")
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
class MaskMap:
    """검출·교정에서 제외할 구간.

    직접 인용을 검출까지 막으면 인용문 안의 AI 패턴을 보고할 수 없으므로
    두 층을 분리한다.
    """

    detect_free: tuple[Span, ...]
    fix_free: tuple[Span, ...]


NON_TEXT = (
    FENCED_CODE,
    INLINE_CODE,
    MATH_BLOCK,
    MATH_INLINE,
    URL,
    MARKDOWN_LINK_TARGET,
)

# 여러 줄에 걸친 축자 구간의 여는·닫는 줄. 이 줄이 든 문단은 흐름을 바꾸면 깨진다.
VERBATIM_OPENER = re.compile(r"^[ \t]*(?:```|\\\[|\\\]|\$\$)", re.MULTILINE)
LAYOUT = (HEADING, TABLE_ROW)


def build_mask(text: str) -> MaskMap:
    """코드와 URL은 애초에 산문이 아니라 어디서도 보지 않는다."""
    detect_free = tuple(
        Span(match.start(), match.end())
        for pattern in NON_TEXT
        for match in pattern.finditer(text)
    )
    # 헤딩 줄 안의 인용은 보호하지 않는다. 남의 말을 고치지 말라는 규칙이지
    # 인용부호가 붙은 제목을 남기라는 뜻이 아니다.
    headings = tuple(Span(m.start(), m.end()) for m in HEADING.finditer(text))
    fix_free = tuple(
        Span(match.start(), match.end())
        for match in DIRECT_QUOTE.finditer(text)
        if not _inside(headings, match.start(), match.end())
    )
    return MaskMap(detect_free=detect_free, fix_free=fix_free)


def _inside(spans: tuple[Span, ...], start: int, end: int) -> bool:
    return any(span.start <= start and end <= span.end for span in spans)


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


def layout_spans(text: str) -> tuple[Span, ...]:
    """헤딩과 표 구간. 문장이 아니라 짜임새다."""
    return tuple(
        Span(match.start(), match.end())
        for pattern in LAYOUT
        for match in pattern.finditer(text)
    )


def protected_spans(text: str, *, layout: bool = True) -> tuple[Span, ...]:
    """교정이 건드리면 안 되는 구간.

    코드·URL과 직접 인용은 언제나 보호한다. 헤딩과 표는 어휘 규칙이 손대야
    하므로 layout=False로 풀 수 있다. 문장부호 규칙에 열어 주면 칸 구분자를
    넘어 매치가 형성되어 표가 깨진다.
    """
    mask = build_mask(text)
    spans = mask.detect_free + mask.fix_free
    if layout:
        spans += layout_spans(text)
    return merge_spans(spans)


def overlaps(spans: tuple[Span, ...], start: int, end: int) -> bool:
    return any(span.start < end and start < span.end for span in spans)


def _split(text: str, boundary: re.Pattern[str]) -> tuple[Segment, ...]:
    segments = []
    cursor = 0
    for match in boundary.finditer(text):
        if _has_prose(text[cursor : match.start()]):
            segments.append(_trimmed(text, cursor, match.start()))
        cursor = match.end()
    if _has_prose(text[cursor:]):
        segments.append(_trimmed(text, cursor, len(text)))
    return tuple(segments)


def _has_prose(chunk: str) -> bool:
    """자리표시자만 남은 조각은 분석 단위로 세지 않는다."""
    return bool(chunk.replace(PLACEHOLDER, "").strip())


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

    헤딩과 표는 두 층으로 갈린다. 어휘 규칙은 거기까지 봐야 한다. '핵심 수익
    구조' 같은 공허한 강조와 굵은 글씨가 헤딩과 표 칸에 몰리기 때문이다.
    반대로 통계 지표와 문장부호 규칙에서는 빼야 한다. 둘 다 문장이 아니고,
    표 칸은 명사구 나열이라 품사 비율을 왜곡한다. 그래서 scrubbed는 둘을
    남기고 prose는 지운다.

    검출과 교정이 같은 함수로 문단을 나누므로 문단 번호가 어긋날 수 없다.
    """

    source: str
    scrubbed: str
    prose: str
    paragraphs: tuple[Segment, ...]

    @classmethod
    def of(cls, text: str) -> Document:
        scrubbed = scrub(text, build_mask(text))
        layout = MaskMap(detect_free=layout_spans(scrubbed), fix_free=())
        return cls(
            source=text,
            scrubbed=scrubbed,
            prose=scrub(scrubbed, layout),
            paragraphs=split_paragraphs(scrubbed),
        )
