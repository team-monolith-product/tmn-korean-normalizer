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

from .segment import PLACEHOLDER, Segment, split_sentences

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
HYPE_WORD = re.compile(
    r"혁신적|획기적|압도적|치명적|전례\s*없는|강력한|파격적|엄청|놀라운"
    r"|독보적|극대화|극단적|폭증|급상승|급증|대폭|비약적|기하급수적"
    r"|가장\s*[가-힣]{2,4}적|최상위|초격차|무궁무진|막대한|어마어마|눈부신"
)
MIN_WORDS_FOR_DENSITY = 60
MIN_PROSE_SENTENCES = 5
SHORT_SENTENCE = 25

# 목록 항목·가로줄·인용 부호는 산문 문장이 아니다. 원래 짧은 단위라
# 문장 길이 통계에 넣으면 글이 잘게 끊긴 것처럼 보인다.
NON_PROSE_LINE = re.compile(r"^[ \t]*(?:[-*+•]\s|\d+[.)]\s|[-=_]{3,}[ \t]*$|>)")
MARKUP = re.compile(r"[*_`#>|]")
INTENSIFIER = re.compile(
    r"완전히|매우|정말로?|아주|굉장히|너무나?|훨씬|확실히|반드시|무조건"
    r"|되게|꽤나?|상당히|한층|더욱더?|극도로|철저히"
)

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


@metric("hype_density")
def _hype_density(context: MetricContext) -> float | None:
    """어절 100개당 과장 어휘 수.

    패턴 38은 한 문단에 몰린 군집을 본다. 과장 어휘는 문서 전체에 하나씩
    흩뿌려지는 쪽이 더 흔해 밀도로 따로 센다.
    """
    words = context.text.split()
    if len(words) < MIN_WORDS_FOR_DENSITY:
        return None
    return len(HYPE_WORD.findall(context.text)) / len(words) * 100


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


def prose_sentences(context: MetricContext) -> list[str]:
    """목록과 장식 줄을 뺀 산문 문장만 고른다."""
    out = []
    for line in context.text.split("\n"):
        if NON_PROSE_LINE.match(line):
            continue
        clean = MARKUP.sub("", line.replace(PLACEHOLDER, "")).strip()
        if not clean:
            continue
        out.extend(
            sentence.text.strip()
            for sentence in split_sentences(clean)
            if len(sentence.text.strip()) >= 2
        )
    return out


@metric("short_sentence_ratio")
def _short_sentence_ratio(context: MetricContext) -> float | None:
    """산문 문장 중 짧은 것의 비율.

    평균 길이는 잘 갈리지 않는다. 아주 짧은 문장과 아주 긴 문장을 섞어 쓰면
    평균이 가운데로 모이기 때문이다. 짧은 쪽 비율이 끊김을 더 잘 드러낸다.
    """
    lengths = [len(s) for s in prose_sentences(context)]
    if len(lengths) < MIN_PROSE_SENTENCES:
        return None
    return sum(1 for n in lengths if n < SHORT_SENTENCE) / len(lengths)


@metric("intensifier_density")
def _intensifier_density(context: MetricContext) -> float | None:
    """어절 100개당 강조 부사 수. 완전히·매우·정말 따위다."""
    words = context.text.split()
    if len(words) < MIN_WORDS_FOR_DENSITY:
        return None
    return len(INTENSIFIER.findall(context.text)) / len(words) * 100


def context_of(text: str) -> MetricContext:
    return MetricContext(text=text, sentences=split_sentences(text))
