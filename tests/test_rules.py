import pytest

from korean_normalizer import metrics
from korean_normalizer.rules import RuleError, build_rule, load_rules

TIER_A = {3, 6, 7, 15, 17, 19, 27, 31, 37}


def test_loads_forty_patterns():
    rules = load_rules()
    assert len(rules) == 40
    assert {rule.id for rule in rules} == set(range(1, 41))


def test_autofix_is_limited_to_tier_a():
    assert {rule.id for rule in load_rules() if rule.has_autofix} == TIER_A


def test_spacing_rules_never_autofix():
    """8~10 자동 교정은 한글 맞춤법 위반을 양산하므로 금지한다."""
    spacing = [rule for rule in load_rules() if rule.category == "spacing"]
    assert spacing and all(not rule.has_autofix for rule in spacing)


def test_every_metric_rule_points_at_a_registered_metric():
    known = set(metrics.registered())
    for rule in load_rules():
        if rule.kind == "metric":
            assert rule.metric in known


def test_every_rule_carries_guidance():
    assert all(rule.guidance.strip() for rule in load_rules())


def test_rejects_unknown_severity():
    with pytest.raises(RuleError, match="unknown severity"):
        build_rule(
            {
                "id": 99,
                "name": "x",
                "severity": "S9",
                "kind": "regex",
                "pattern": "x",
                "guidance": "g",
            },
            "test",
        )


def test_rejects_invalid_regex():
    with pytest.raises(RuleError, match="invalid regex"):
        build_rule(
            {
                "id": 99,
                "name": "x",
                "severity": "S1",
                "kind": "regex",
                "pattern": "(",
                "guidance": "g",
            },
            "test",
        )


def test_rejects_missing_field():
    with pytest.raises(RuleError, match="missing required field"):
        build_rule({"id": 99, "name": "x", "severity": "S1", "kind": "regex"}, "test")


def test_rejects_unknown_scope():
    with pytest.raises(RuleError, match="unknown scope"):
        build_rule(
            {
                "id": 99,
                "name": "x",
                "severity": "S1",
                "kind": "regex",
                "pattern": "x",
                "guidance": "g",
                "threshold": {"scope": "chapter"},
            },
            "test",
        )
