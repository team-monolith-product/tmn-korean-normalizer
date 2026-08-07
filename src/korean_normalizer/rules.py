"""규칙 정의를 로드하고 검증한다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

SEVERITIES = ("S1", "S2", "S3")
KINDS = ("regex", "metric")
SCOPES = ("document", "paragraph")
RULE_FILES = (
    "punctuation.json",
    "spacing.json",
    "pos.json",
    "vocabulary.json",
    "structure.json",
    "translation.json",
)


class RuleError(ValueError):
    """규칙 정의가 스키마를 위반했을 때."""


@dataclass(frozen=True)
class AutoFix:
    """Tier A 규칙의 결정적 치환.

    josa_group이 있으면 그 그룹을 치환 결과 뒤에 붙이되 받침에 맞춰 교체한다.
    """

    pattern: re.Pattern[str]
    replacement: str
    josa_group: int | None = None


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    category: str
    severity: str
    kind: str
    scope: str
    count: int
    guidance: str
    pattern: re.Pattern[str] | None = None
    exclude: re.Pattern[str] | None = None
    metric: str | None = None
    metric_bound: dict[str, float] | None = None
    autofix: tuple[AutoFix, ...] = ()

    @property
    def has_autofix(self) -> bool:
        return bool(self.autofix)


def _compile(value: str | None, field: str, rule_id: object) -> re.Pattern[str] | None:
    if value is None:
        return None
    try:
        return re.compile(value, re.MULTILINE)
    except re.error as error:
        raise RuleError(f"rule {rule_id}: invalid regex in {field}: {error}") from error


def _require(raw: dict, field: str, rule_id: object):
    if field not in raw:
        raise RuleError(f"rule {rule_id}: missing required field '{field}'")
    return raw[field]


def build_rule(raw: dict, category: str) -> Rule:
    rule_id = raw.get("id", "<unknown>")
    severity = _require(raw, "severity", rule_id)
    if severity not in SEVERITIES:
        raise RuleError(f"rule {rule_id}: unknown severity '{severity}'")
    kind = _require(raw, "kind", rule_id)
    if kind not in KINDS:
        raise RuleError(f"rule {rule_id}: unknown kind '{kind}'")

    threshold = raw.get("threshold", {})
    scope = threshold.get("scope", "document")
    if scope not in SCOPES:
        raise RuleError(f"rule {rule_id}: unknown scope '{scope}'")

    if kind == "regex":
        pattern = _compile(_require(raw, "pattern", rule_id), "pattern", rule_id)
        metric = None
        metric_bound = None
    else:
        pattern = None
        metric = _require(raw, "metric", rule_id)
        metric_bound = _require(raw, "bound", rule_id)

    autofix = tuple(
        AutoFix(
            pattern=_compile(entry["pattern"], "autofix.pattern", rule_id),
            replacement=entry["replacement"],
            josa_group=entry.get("josa_group"),
        )
        for entry in raw.get("autofix", [])
    )

    return Rule(
        id=int(_require(raw, "id", rule_id)),
        name=_require(raw, "name", rule_id),
        category=category,
        severity=severity,
        kind=kind,
        scope=scope,
        count=int(threshold.get("count", 1)),
        guidance=_require(raw, "guidance", rule_id),
        pattern=pattern,
        exclude=_compile(raw.get("exclude"), "exclude", rule_id),
        metric=metric,
        metric_bound=metric_bound,
        autofix=autofix,
    )


@lru_cache(maxsize=1)
def load_rules() -> tuple[Rule, ...]:
    """패키지에 포함된 40개 규칙을 id 순으로 반환한다."""
    rules: list[Rule] = []
    package = resources.files("korean_normalizer") / "rules"
    for filename in RULE_FILES:
        category = filename.removesuffix(".json")
        raw = json.loads((package / filename).read_text(encoding="utf-8"))
        rules.extend(build_rule(entry, category) for entry in raw)

    seen = [rule.id for rule in rules]
    duplicates = {rule_id for rule_id in seen if seen.count(rule_id) > 1}
    if duplicates:
        raise RuleError(f"duplicate rule ids: {sorted(duplicates)}")
    return tuple(sorted(rules, key=lambda rule: rule.id))
