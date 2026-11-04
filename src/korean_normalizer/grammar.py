"""형태소 분석에 기반한 비문 검사. 문체 등급과 별도로 오류·검토 후보를 보고한다."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .josa import agree
from .morphology import get_analyzer
from .segment import PLACEHOLDER, Document

if TYPE_CHECKING:
    from kiwipiepy import Kiwi, Token

RULE_IDS = ("G001", "G002", "G003")
PARTICLE_TAGS = {
    "으로": {"JKB"},
    "로": {"JKB"},
    "을": {"JKO"},
    "를": {"JKO"},
    "은": {"JX"},
    "는": {"JX"},
    "이": {"JKS", "JKC"},
    "가": {"JKS", "JKC"},
    "과": {"JC", "JKB"},
    "와": {"JC", "JKB"},
}
NOMINAL_TAGS = {"NNG", "NNP", "NNB", "NP", "NR", "XSN", "ETN"}
PREDICATE_TAGS = {"VV", "VA", "VX", "VCP", "VCN", "XSV", "XSA"}
NEGATIVES = {
    "안": {"MAG"},
    "못": {"MAG"},
    "않": {"VX"},
    "못하": {"VX", "VV", "VA"},
    "없": {"VA", "VV"},
    "아니": {"VCN", "MAG"},
    "모르": {"VV"},
    "말": {"VX"},
}
WORD = re.compile(r"(?<!\w)[가-힣]+(?!\w)")


@dataclass(frozen=True)
class GrammarFinding:
    rule_id: str
    severity: str
    start: int
    end: int
    line: int
    column: int
    text: str
    message: str
    suggestion: str | None


@dataclass(frozen=True)
class GrammarReport:
    findings: tuple[GrammarFinding, ...] = ()
    skipped: bool = False

    @property
    def counts(self) -> dict[str, int]:
        return {
            severity: sum(finding.severity == severity for finding in self.findings)
            for severity in ("error", "review")
        }

    def to_dict(self) -> dict:
        return {
            "status": "skipped" if self.skipped else "checked",
            "rules_checked": [] if self.skipped else list(RULE_IDS),
            "counts": self.counts,
            "findings": [asdict(finding) for finding in self.findings],
        }


@dataclass(frozen=True)
class _Issue:
    rule_id: str
    severity: str
    start: int
    end: int
    message: str
    suggestion: str | None = None


def _tag(token: Token) -> str:
    """Strip Kiwi's regular/irregular conjugation suffixes, e.g. VV-I."""
    return token.tag.split("-", 1)[0]


def _token_end(token: Token) -> int:
    return token.start + token.len


def _check_particles(
    text: str, tokens: list[Token], start: int, end: int, kiwi: Kiwi
) -> Iterator[_Issue]:
    for word in WORD.finditer(text, start, end):
        particle = next(
            (form for form in PARTICLE_TAGS if word[0].endswith(form)), None
        )
        if particle is None or len(word[0]) <= len(particle):
            continue
        particle_start = word.end() - len(particle)
        stem = text[word.start() : particle_start]
        particle_tags = PARTICLE_TAGS[particle]
        expected = agree(stem, particle)
        if particle == expected:
            continue
        # A whole noun or an attributive ending must not be mistaken for a particle.
        if not any(
            _token_end(token) == particle_start and _tag(token) in NOMINAL_TAGS
            for token in tokens
        ):
            continue
        suffix = [
            token for token in tokens if particle_start <= token.start < word.end()
        ]
        if any(_tag(token) in {"XSN", "NNP"} for token in suffix):
            continue
        recognized = any(
            token.start == particle_start
            and _token_end(token) == word.end()
            and _tag(token) in particle_tags
            for token in suffix
        )
        if not recognized:
            standalone = kiwi.tokenize(word[0])
            boundary = len(stem)
            if any(
                token.start < boundary < _token_end(token)
                and _tag(token) in {"NNG", "NNB", "NP", "NR"}
                and kiwi.morpheme(token.id).form == token.form
                for token in standalone
            ):
                # 조사로 분석되지 않은 후보는 단독 분석으로 재확인한다.
                # '비교 + 과'는 등록 명사 '교과'의 내부다. 미등록어의
                # 기본 형태는 빈 문자열이므로 '산로'의 검토 후보는 유지한다.
                continue
            # Ill-formed particles are often tagged as nouns/verbs. Confirm that
            # the corrected surface can be analyzed as a nominal + particle,
            # and retain it only as a review candidate.
            corrected = kiwi.tokenize(stem + expected)
            if not any(
                token.start == len(stem)
                and _token_end(token) == len(stem + expected)
                and _tag(token) in particle_tags
                for token in corrected
            ):
                continue
        yield _Issue(
            "G001",
            "error" if recognized else "review",
            particle_start,
            word.end(),
            f"앞말의 받침에 맞는 조사 형태는 '{expected}'입니다."
            if recognized
            else f"조사 선택을 확인하세요. 조사로 쓰였다면 '{particle}' 대신 "
            f"'{expected}' 형태가 맞습니다.",
            expected,
        )


def _check_bakke(tokens: list[Token]) -> Iterator[_Issue]:
    for index, token in enumerate(tokens):
        if token.form == "밖에" and _tag(token) == "JX":
            tail_start = index + 1
        elif (
            token.form == "밖"
            and _tag(token) == "NNG"
            and index > 0
            and _token_end(tokens[index - 1]) == token.start
            and _tag(tokens[index - 1]) in NOMINAL_TAGS
            and index + 1 < len(tokens)
            and tokens[index + 1].form == "에"
            and _tag(tokens[index + 1]) == "JKB"
        ):
            # A bad positive clause may make Kiwi choose the spatial noun 밖.
            tail_start = index + 2
        else:
            continue
        scope = []
        for position in range(tail_start, len(tokens)):
            current = tokens[position]
            scope.append(current)
            auxiliary_follows = (
                position + 1 < len(tokens) and _tag(tokens[position + 1]) == "VX"
            )
            if _tag(current) == "EF" or (
                _tag(current) == "EC" and not auxiliary_follows
            ):
                break
        if not scope or _tag(scope[-1]) not in {"EF", "EC"}:
            continue
        if not any(_tag(current) in PREDICATE_TAGS for current in scope):
            continue
        if any(
            _tag(current) in NEGATIVES.get(current.form, set()) for current in scope
        ):
            continue
        yield _Issue(
            "G002",
            "review",
            token.start,
            _token_end(scope[-1]),
            "보조사 '밖에'에 호응하는 부정 표현을 확인하세요. "
            "장소를 뜻하는 '밖'이라면 앞말과 띄어 쓰는지 확인하세요.",
            "'…밖에 오지 않았다' 또는 '…만 왔다'처럼 원래 뜻에 맞게 고치세요.",
        )


def _check_goal(tokens: list[Token]) -> Iterator[_Issue]:
    for index, token in enumerate(tokens[:-1]):
        if token.form not in {"목표", "꿈", "소망"} or _tag(token) != "NNG":
            continue
        topic = tokens[index + 1]
        if topic.form not in {"은", "는"} or _tag(topic) != "JX":
            continue
        tail = tokens[index + 2 :]
        predicates = [i for i, item in enumerate(tail) if _tag(item) in PREDICATE_TAGS]
        if not predicates:
            continue
        wish_index = predicates[-1]
        wish = tail[wish_index]
        if wish.form != "싶" or _tag(wish) != "VX" or wish_index < 2:
            continue
        become, connective = tail[wish_index - 2 : wish_index]
        if not (
            become.form == "되"
            and _tag(become) == "VV"
            and connective.form == "고"
            and _tag(connective) == "EC"
        ):
            continue
        # Keep the rule to simple finite clauses: quoted/embedded descriptions
        # such as "되고 싶은 사람이 되는 것이다" have a different structure.
        if any(
            _tag(item) in {"EC", "ETM", "ETN", "JX", "JKS"}
            for item in tail[: wish_index - 1]
        ):
            continue
        ending = tail[wish_index + 1 :]
        if not any(_tag(item) == "EF" for item in ending):
            continue
        if any(_tag(item) not in {"EP", "EF", "SF"} for item in ending):
            continue
        yield _Issue(
            "G003",
            "review",
            token.start,
            _token_end(next(item for item in ending if _tag(item) == "EF")),
            f"'{token.form}{topic.form} … 되고 싶다' 구문의 "
            "주어·서술어 호응을 확인하세요.",
            f"'{token.form}{topic.form} …이/가 되는 것이다' 또는 "
            "'나는 …이/가 되고 싶다'처럼 "
            "의도에 맞게 서술하세요.",
        )


def analyze(text: str) -> GrammarReport:
    return analyze_document(Document.of(text))


def analyze_document(document: Document) -> GrammarReport:
    analyzer = get_analyzer()
    if analyzer is None:
        return GrammarReport(skipped=True)
    text = document.source
    masked = document.scrubbed.replace(PLACEHOLDER, " ")
    line_starts = [0, *(match.end() for match in re.finditer(r"\r\n?|\n", text))]
    findings = []
    # 목록이나 다음 문단이 앞줄의 부정 표현·서술어를 대신하지 않게 한다.
    for line in re.finditer(r"[^\r\n]+", masked):
        if not line[0].strip():
            continue
        original_line = text[line.start() : line.end()]
        for sentence in analyzer.split_into_sents(line[0], return_tokens=True):
            tokens = sentence.tokens
            issues = list(
                _check_particles(
                    line[0], tokens, sentence.start, sentence.end, analyzer
                )
            )
            syntax_text = line[0][sentence.start : sentence.end]
            has_mask = syntax_text != original_line[sentence.start : sentence.end]
            if (
                not has_mask
                and not any(mark in syntax_text for mark in "?\uff1f")
                and not any(_tag(token) in {"SSO", "SSC"} for token in tokens)
            ):
                issues.extend(_check_bakke(tokens))
                issues.extend(_check_goal(tokens))
            for issue in issues:
                start = line.start() + issue.start
                end = line.start() + issue.end
                line_number = bisect_right(line_starts, start)
                findings.append(
                    GrammarFinding(
                        rule_id=issue.rule_id,
                        severity=issue.severity,
                        start=start,
                        end=end,
                        line=line_number,
                        column=start - line_starts[line_number - 1] + 1,
                        text=text[start:end],
                        message=issue.message,
                        suggestion=issue.suggestion,
                    )
                )
    return GrammarReport(
        tuple(sorted(findings, key=lambda item: (item.start, item.rule_id)))
    )
