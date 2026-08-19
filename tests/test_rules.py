import pytest

from korean_normalizer import metrics
from korean_normalizer import rules as rules_module
from korean_normalizer.rules import MetricRule, RuleError, build_rule, load_rules

TIER_A = {3, 6, 7, 15, 17, 19, 27, 31, 37, 108, 112, 113, 114}
BORROWED_IDS = set(range(1, 41)) - {38}
TEAM_IDS = {101, 102, 103, 104, 105, 106, 108, 109, 111, 112, 113, 114, 115, 116, 117}


def test_rule_set_is_complete():
    assert {rule.id for rule in load_rules()} == BORROWED_IDS | TEAM_IDS


def test_team_rules_live_in_their_own_file():
    """출처를 구분하려고 번호대와 파일을 나눴다. 양쪽 다 자유롭게 고친다."""
    assert all(rule.category == "extra" for rule in load_rules() if rule.id >= 101)


def test_autofix_is_limited_to_tier_a():
    assert {rule.id for rule in load_rules() if rule.has_autofix} == TIER_A


def test_spacing_rules_never_autofix():
    """8~10 자동 교정은 한글 맞춤법 위반을 양산하므로 금지한다."""
    spacing = [rule for rule in load_rules() if rule.category == "spacing"]
    assert spacing
    assert all(not rule.has_autofix for rule in spacing)


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


def test_rejects_unknown_kind():
    with pytest.raises(RuleError, match="unknown kind"):
        build_rule(
            {
                "id": 99,
                "name": "x",
                "severity": "S1",
                "kind": "vibes",
                "guidance": "g",
            },
            "test",
        )


def test_rejects_duplicate_ids(monkeypatch):
    load_rules.cache_clear()
    monkeypatch.setattr(rules_module, "RULE_FILES", ("punctuation.json",) * 2)
    with pytest.raises(RuleError, match="duplicate rule ids"):
        load_rules()
    load_rules.cache_clear()


def test_metric_rules_cannot_carry_autofix():
    """통계 규칙은 자동 교정 필드를 갖지 못하는 것이 타입으로 보장된다."""
    metric_rules = [rule for rule in load_rules() if isinstance(rule, MetricRule)]
    assert metric_rules
    assert all(not hasattr(rule, "autofix") for rule in metric_rules)


def test_kind_is_derived_from_the_type():
    kinds = {rule.kind for rule in load_rules()}
    assert kinds == {"regex", "metric"}


@pytest.mark.parametrize(
    "bound",
    [{"gtt": 0.4}, {}, {"gt": 0.4, "lt": 0.9}],
    ids=["typo", "empty", "two-operators"],
)
def test_rejects_malformed_bound(bound):
    """연산자 오타나 빈 bound가 통과하면 그 규칙이 모든 문서에서 발화한다."""
    with pytest.raises(RuleError):
        build_rule(
            {
                "id": 99,
                "name": "x",
                "severity": "S2",
                "kind": "metric",
                "metric": "comma_sentence_ratio",
                "bound": bound,
                "guidance": "g",
            },
            "test",
        )


def test_rejects_unknown_metric_at_load_time():
    with pytest.raises(RuleError, match="unknown metric"):
        build_rule(
            {
                "id": 99,
                "name": "x",
                "severity": "S2",
                "kind": "metric",
                "metric": "vibes_per_sentence",
                "bound": {"gt": 0.4},
                "guidance": "g",
            },
            "test",
        )


def test_tier_matches_the_documented_taxonomy():
    by_tier: dict[str, set[int]] = {}
    for rule in load_rules():
        by_tier.setdefault(rule.tier, set()).add(rule.id)
    assert by_tier["A"] == TIER_A
    assert by_tier["C"] == {11, 12, 13}
    assert by_tier["B"] == (BORROWED_IDS | TEAM_IDS) - TIER_A - {11, 12, 13}


def test_every_regex_rule_counts_across_the_document():
    """문단마다 하나씩 흩뿌리는 글이 흔해 임계를 문서 단위로 통일했다."""
    assert all(
        rule.scope == "document" for rule in load_rules() if rule.kind == "regex"
    )


def test_hype_rule_is_not_duplicated():
    """38번 hype 군집은 105번 밀도 규칙으로 합쳤다."""
    assert 38 not in {rule.id for rule in load_rules()}
    assert 105 in {rule.id for rule in load_rules()}
