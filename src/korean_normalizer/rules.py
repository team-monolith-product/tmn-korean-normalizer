"""규칙 정의를 로드하고 검증한다.

1~40번은 DaleSeo/korean-skills humanizer 스킬에서 왔고 101번부터는 팀이
실사용에서 찾아 덧붙였다. 출처만 다를 뿐 둘 다 자유롭게 고친다.

정규식 규칙과 통계 규칙은 필요한 필드가 겹치지 않는다. 한 클래스에 담고
kind 문자열로 갈라 쓰면 절반이 항상 None이 되므로 타입을 나눈다.
그 덕에 통계 규칙은 자동 교정을 가질 수 없다는 사실이 구조로 강제된다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from . import metrics

SEVERITIES = ("S1", "S2", "S3")
SCOPES = ("document", "paragraph")
COMPARATORS = {
    "gt": lambda value, limit: value > limit,
    "gte": lambda value, limit: value >= limit,
    "lt": lambda value, limit: value < limit,
    "lte": lambda value, limit: value <= limit,
}
RULE_FILES = (
    "punctuation.json",
    "spacing.json",
    "vocabulary.json",
    "structure.json",
    "translation.json",
    "extra.json",
)


class RuleError(ValueError):
    """규칙 정의가 스키마를 위반했을 때."""


@dataclass(frozen=True)
class Bound:
    """지표 경계. 연산자를 로드 시점에 검증해 오타가 조용히 통과하지 못하게 한다."""

    operator: str
    limit: float

    def breached_by(self, value: float) -> bool:
        return COMPARATORS[self.operator](value, self.limit)


@dataclass(frozen=True)
class AutoFix:
    """Tier A 규칙의 결정적 치환.

    josa_group이 있으면 그 그룹을 치환 결과 뒤에 붙이되 받침에 맞춰 교체한다.
    """

    pattern: re.Pattern[str]
    replacement: str
    josa_group: int | None = None


@dataclass(frozen=True)
class BaseRule:
    id: int
    name: str
    category: str
    severity: str
    guidance: str

    @property
    def has_autofix(self) -> bool:
        return False


@dataclass(frozen=True)
class RegexRule(BaseRule):
    pattern: re.Pattern[str]
    scope: str = "document"
    count: int = 1
    exclude: re.Pattern[str] | None = None
    autofix: tuple[AutoFix, ...] = ()

    @property
    def has_autofix(self) -> bool:
        return bool(self.autofix)

    @property
    def tier(self) -> str:
        """A는 자동 교정, C는 형태소 분석기 필요, B는 검출만."""
        return "A" if self.autofix else "B"

    @property
    def kind(self) -> str:
        """표시·직렬화용 이름. 분기는 타입으로 한다."""
        return "regex"


@dataclass(frozen=True)
class MetricRule(BaseRule):
    metric: str
    bound: Bound

    @property
    def tier(self) -> str:
        return "C" if metrics.needs_analyzer(self.metric) else "B"

    @property
    def kind(self) -> str:
        return "metric"


Rule = RegexRule | MetricRule


def _compile(value: str, field_name: str, rule_id: object) -> re.Pattern[str]:
    try:
        return re.compile(value, re.MULTILINE)
    except re.error as error:
        raise RuleError(
            f"rule {rule_id}: invalid regex in {field_name}: {error}"
        ) from error


def _compile_optional(
    value: str | None, field_name: str, rule_id: object
) -> re.Pattern[str] | None:
    return None if value is None else _compile(value, field_name, rule_id)


def _require(raw: dict, field_name: str, rule_id: object):
    if field_name not in raw:
        raise RuleError(f"rule {rule_id}: missing required field '{field_name}'")
    return raw[field_name]


def _common(raw: dict, category: str, rule_id: object) -> dict:
    severity = _require(raw, "severity", rule_id)
    if severity not in SEVERITIES:
        raise RuleError(f"rule {rule_id}: unknown severity '{severity}'")
    return {
        "id": int(_require(raw, "id", rule_id)),
        "name": _require(raw, "name", rule_id),
        "category": category,
        "severity": severity,
        "guidance": _require(raw, "guidance", rule_id),
    }


def _regex_rule(raw: dict, common: dict, rule_id: object) -> RegexRule:
    threshold = raw.get("threshold", {})
    scope = threshold.get("scope", "document")
    if scope not in SCOPES:
        raise RuleError(f"rule {rule_id}: unknown scope '{scope}'")
    autofix = tuple(
        AutoFix(
            pattern=_compile(entry["pattern"], "autofix.pattern", rule_id),
            replacement=entry["replacement"],
            josa_group=entry.get("josa_group"),
        )
        for entry in raw.get("autofix", [])
    )
    return RegexRule(
        **common,
        pattern=_compile(_require(raw, "pattern", rule_id), "pattern", rule_id),
        scope=scope,
        count=int(threshold.get("count", 1)),
        exclude=_compile_optional(raw.get("exclude"), "exclude", rule_id),
        autofix=autofix,
    )


def _bound(raw: dict, rule_id: object) -> Bound:
    bound = _require(raw, "bound", rule_id)
    if len(bound) != 1:
        raise RuleError(f"rule {rule_id}: bound must hold exactly one comparison")
    operator, limit = next(iter(bound.items()))
    if operator not in COMPARATORS:
        raise RuleError(f"rule {rule_id}: unknown bound operator '{operator}'")
    return Bound(operator=operator, limit=float(limit))


def _metric_rule(raw: dict, common: dict, rule_id: object) -> MetricRule:
    name = _require(raw, "metric", rule_id)
    if name not in metrics.registered():
        raise RuleError(f"rule {rule_id}: unknown metric '{name}'")
    return MetricRule(**common, metric=name, bound=_bound(raw, rule_id))


def build_rule(raw: dict, category: str) -> Rule:
    rule_id = raw.get("id", "<unknown>")
    common = _common(raw, category, rule_id)
    kind = _require(raw, "kind", rule_id)
    if kind == "regex":
        return _regex_rule(raw, common, rule_id)
    if kind == "metric":
        return _metric_rule(raw, common, rule_id)
    raise RuleError(f"rule {rule_id}: unknown kind '{kind}'")


@lru_cache(maxsize=1)
def load_rules() -> tuple[Rule, ...]:
    """패키지에 담긴 규칙 전부를 id 순으로 반환한다."""
    rules: list[Rule] = []
    package = resources.files("korean_normalizer") / "rules"
    for filename in RULE_FILES:
        category = filename.removesuffix(".json")
        raw = json.loads((package / filename).read_text(encoding="utf-8"))
        rules.extend(build_rule(entry, category) for entry in raw)

    counted = Counter(rule.id for rule in rules)
    duplicates = [rule_id for rule_id, seen in counted.items() if seen > 1]
    if duplicates:
        raise RuleError(f"duplicate rule ids: {sorted(duplicates)}")
    return tuple(sorted(rules, key=lambda rule: rule.id))
