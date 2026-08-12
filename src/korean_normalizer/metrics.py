"""통계 기반 패턴의 지표 계산.

정규식으로 셀 수 없는 패턴만 여기서 다룬다. 표본이 모자라면 None을 반환해
판정을 건너뛴다. 없는 근거로 등급을 매기지 않기 위해서다.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from .segment import Segment, split_sentences

MIN_SENTENCES = 3
MIN_SENTENCES_FOR_RHYTHM = 4
MIN_SENTENCES_FOR_ENDING = 5
MIN_SPACING_SAMPLES = 5
MIN_CONTENT_WORDS = 30
MIN_TOKENS_FOR_NGRAM = 50

DEPENDENT_NOUN = re.compile(r"[가-힣](\s?)(?:것|수|등|뿐|만큼)(?![가-힣])")
AUXILIARY_VERB = re.compile(r"(?:고|어|아)(\s?)(?:있|주|보)(?=[다습어었는고을])")
CONJUNCTION_OPENING = re.compile(
    r"^(?:그러나|그리고|또한|따라서|게다가|하지만|그러므로|즉|또는|그래서|더불어)"
)
SUBJECT_OPENING = re.compile(r"^([가-힣]{1,10}[은는])\s")

FORMAL = re.compile(r"(?:습니다|ㅂ니다|입니다)[.!?]?$")
POLITE = re.compile(r"(?:어요|아요|에요|예요|해요|죠|요)[.!?]?$")
PLAIN = re.compile(r"(?:[는ㄴ]?다|이다|었다|았다|한다)[.!?]?$")


@dataclass(frozen=True)
class MetricContext:
    text: str
    sentences: tuple[Segment, ...]


Metric = Callable[[MetricContext], float | None]
_REGISTRY: dict[str, Metric] = {}


def metric(name: str) -> Callable[[Metric], Metric]:
    def register(function: Metric) -> Metric:
        _REGISTRY[name] = function
        return function

    return register


def compute(name: str, context: MetricContext) -> float | None:
    if name not in _REGISTRY:
        raise KeyError(f"unknown metric: {name}")
    return _REGISTRY[name](context)


def registered() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


ANALYZER_METRICS = frozenset(
    {"noun_ratio", "verb_adjective_ratio", "pos_trigram_diversity"}
)


def needs_analyzer(name: str) -> bool:
    """형태소 분석기가 있어야 계산되는 지표인지. Tier 판정의 유일한 근거다."""
    return name in ANALYZER_METRICS


@metric("comma_sentence_ratio")
def _comma_sentence_ratio(context: MetricContext) -> float | None:
    if len(context.sentences) < MIN_SENTENCES:
        return None
    with_comma = sum(1 for sentence in context.sentences if "," in sentence.text)
    return with_comma / len(context.sentences)


@metric("comma_relative_position")
def _comma_relative_position(context: MetricContext) -> float | None:
    positions = [
        index / (len(sentence.text) - 1)
        for sentence in context.sentences
        if len(sentence.text) > 1
        for index, char in enumerate(sentence.text)
        if char == ","
    ]
    if not positions:
        return None
    return statistics.fmean(positions)


def _spacing_uniformity(pattern: re.Pattern[str], text: str) -> float | None:
    gaps = [match.group(1) for match in pattern.finditer(text)]
    if len(gaps) < MIN_SPACING_SAMPLES:
        return None
    return sum(1 for gap in gaps if gap) / len(gaps)


@metric("dependent_noun_spacing_uniformity")
def _dependent_noun_spacing(context: MetricContext) -> float | None:
    return _spacing_uniformity(DEPENDENT_NOUN, context.text)


@metric("auxiliary_verb_spacing_uniformity")
def _auxiliary_verb_spacing(context: MetricContext) -> float | None:
    return _spacing_uniformity(AUXILIARY_VERB, context.text)


@metric("sentence_length_cv")
def _sentence_length_cv(context: MetricContext) -> float | None:
    lengths = [len(sentence.text) for sentence in context.sentences]
    if len(lengths) < MIN_SENTENCES_FOR_RHYTHM:
        return None
    mean = statistics.fmean(lengths)
    if mean == 0:
        return None
    return statistics.stdev(lengths) / mean


@metric("conjunction_sentence_ratio")
def _conjunction_sentence_ratio(context: MetricContext) -> float | None:
    if len(context.sentences) < MIN_SENTENCES:
        return None
    opened = sum(
        1 for sentence in context.sentences if CONJUNCTION_OPENING.match(sentence.text)
    )
    return opened / len(context.sentences)


@metric("ending_uniformity")
def _ending_uniformity(context: MetricContext) -> float | None:
    styles = [_ending_style(sentence.text) for sentence in context.sentences]
    known = [style for style in styles if style]
    if len(known) < MIN_SENTENCES_FOR_ENDING:
        return None
    return Counter(known).most_common(1)[0][1] / len(known)


def _ending_style(sentence: str) -> str | None:
    stripped = sentence.rstrip()
    for name, pattern in (("formal", FORMAL), ("polite", POLITE), ("plain", PLAIN)):
        if pattern.search(stripped):
            return name
    return None


@metric("repeated_subject_runs")
def _repeated_subject_runs(context: MetricContext) -> float | None:
    subjects = [_subject_of(sentence.text) for sentence in context.sentences]
    longest = 0
    run = 0
    previous = None
    for subject in subjects:
        if subject and subject == previous:
            run += 1
        else:
            run = 1 if subject else 0
        previous = subject
        longest = max(longest, run)
    return float(longest)


def _subject_of(sentence: str) -> str | None:
    match = SUBJECT_OPENING.match(sentence)
    return match.group(1) if match else None


@lru_cache(maxsize=1)
def _kiwi():
    """형태소 분석기는 로딩이 무거워 한 번만 만든다. 없으면 None."""
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        return None
    return Kiwi()


def _kiwi_tags(text: str) -> list[str] | None:
    """kiwipiepy가 설치돼 있을 때만 품사 태그를 반환한다."""
    analyzer = _kiwi()
    if analyzer is None:
        return None
    return [token.tag for token in analyzer.tokenize(text)]


CONTENT_TAGS = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "VX", "MAG", "MAJ", "MM")
NOUN_TAGS = ("NNG", "NNP", "NNB", "NR")
PREDICATE_TAGS = ("VV", "VA", "VX")


def _content_tags(text: str) -> list[str] | None:
    """내용어 태그. 표본이 적으면 비율이 요동치므로 None을 돌려준다."""
    tags = _kiwi_tags(text)
    if tags is None:
        return None
    content = [tag for tag in tags if tag.split("-")[0] in CONTENT_TAGS]
    return content if len(content) >= MIN_CONTENT_WORDS else None


@metric("noun_ratio")
def _noun_ratio(context: MetricContext) -> float | None:
    tags = _content_tags(context.text)
    if not tags:
        return None
    return sum(1 for tag in tags if tag.split("-")[0] in NOUN_TAGS) / len(tags)


@metric("verb_adjective_ratio")
def _verb_adjective_ratio(context: MetricContext) -> float | None:
    tags = _content_tags(context.text)
    if not tags:
        return None
    return sum(1 for tag in tags if tag.split("-")[0] in PREDICATE_TAGS) / len(tags)


@metric("pos_trigram_diversity")
def _pos_trigram_diversity(context: MetricContext) -> float | None:
    tags = _kiwi_tags(context.text)
    if not tags or len(tags) < MIN_TOKENS_FOR_NGRAM:
        return None
    trigrams = [tuple(tags[index : index + 3]) for index in range(len(tags) - 2)]
    return len(set(trigrams)) / len(trigrams)


def context_of(text: str) -> MetricContext:
    return MetricContext(text=text, sentences=split_sentences(text))
