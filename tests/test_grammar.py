import pytest

from korean_normalizer import grammar
from korean_normalizer.grammar import analyze

POSITIVE = {
    "사과을 먹었다.": ("G001", "를"),
    "책를 읽었다.": ("G001", "을"),
    "사과은 맛있다.": ("G001", "는"),
    "학생는 웃었다.": ("G001", "은"),
    "학생가 왔다.": ("G001", "이"),
    "사과과 배를 샀다.": ("G001", "와"),
    "꽃와 나무가 있다.": ("G001", "과"),
    "학교으로 갔다.": ("G001", "로"),
    "길으로 걸었다.": ("G001", "로"),
    "산로 갔다.": ("G001", "으로"),
    "그 사람밖에 왔다.": ("G002", None),
    "민수밖에 왔고 영희는 안 왔다.": ("G002", None),
    "민수밖에 오고 싶다.": ("G002", None),
    "내 목표는 개발자가 되고 싶다.": ("G003", None),
    "제 꿈은 의사가 되고 싶습니다.": ("G003", None),
    "내 소망은 선생님이 되고 싶었다.": ("G003", None),
}
NEGATIVE = [
    "사과를 먹었다.",
    "책을 읽었다.",
    "사과는 맛있다.",
    "학생은 웃었다.",
    "학생이 왔다.",
    "사과와 배를 샀다.",
    "꽃과 나무가 있다.",
    "학교로 갔다.",
    "길로 걸었다.",
    "산으로 갔다.",
    "나는 학교에 간다.",
    "가는 길은 멀다.",
    "그는 웃는 사람이다.",
    "먹는 사람도 있고 웃는 사람도 있다.",
    "나는 자는 사람을 봤다.",
    "그 사람밖에 오지 않았다.",
    "그 사람밖에 안 왔다.",
    "밥밖에 못 먹었다.",
    "너밖에 사랑할 사람이 없다.",
    "할 수밖에 없다.",
    "민수밖에 없어서 돌아왔다.",
    "그 밖에 할 일이 많다.",
    "집 밖에 나갔다.",
    "밖에 나갔다.",
    "민수밖에 누가 왔겠니?",
    "그는 민수밖에 모른다.",
    "그의 목표는 개발자가 되는 것이다.",
    "나는 개발자가 되고 싶다.",
    "내 꿈은 이루고 싶다.",
    "내 목표는 내가 되고 싶은 사람이 되는 것이다.",
    "내 목표는 개발자가 되고 싶다는 친구를 돕는 것이다.",
    "먹었다.",
    "내 꿈은 의사",
    "API를 호출했다.",
    "3을 더했다.",
    "기계과에 입학했다.",
    '"내 목표는 개발자가 되고 싶다"라고 썼다.',
    "“그 사람밖에 왔다”라는 문장을 읽었다.",
    "`사과을 먹었다`라고 썼다.",
    "``책를 읽었다. `사과을` 먹었다.``",
    "```python\n책를 읽었다.\n```\n책을 읽었다.",
    "~~~\n내 목표는 개발자가 되고 싶다.\n~~~~\n사과를 먹었다.",
    "````python\n```\n사과을 먹었다.\n````\n책을 읽었다.",
    "```\n사과을 먹었다.",
    "    사과을 먹었다.\n사과를 먹었다.",
    "\t책를 읽었다.",
    "https://example.com/사과을",
    "",
]


@pytest.mark.parametrize(("text", "expected"), POSITIVE.items())
def test_detects_grammar_errors_and_candidates(text, expected):
    rule_id, suggestion = expected
    report = analyze(text)
    matches = [finding for finding in report.findings if finding.rule_id == rule_id]
    assert matches
    if suggestion is not None:
        assert matches[0].suggestion == suggestion


@pytest.mark.parametrize("text", NEGATIVE)
def test_accepts_normal_expressions_and_excludes_code(text):
    assert analyze(text).findings == ()


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_positions_reconstruct_unicode_source(newline):
    text = f"첫 줄입니다.{newline}🙂 책를 읽었다.{newline}내 목표는 개발자가 되고 싶다."
    findings = analyze(text).findings
    assert [finding.rule_id for finding in findings] == ["G001", "G003"]
    assert (findings[0].line, findings[0].column) == (2, 4)
    for finding in findings:
        assert text[finding.start : finding.end] == finding.text


def test_reports_missing_analyzer_explicitly(monkeypatch):
    monkeypatch.setattr(grammar, "get_analyzer", lambda: None)
    result = analyze("책를 읽었다.")
    assert result.skipped
    assert result.findings == ()
    assert result.to_dict()["status"] == "skipped"
    assert result.to_dict()["rules_checked"] == []


def test_separates_errors_from_review_candidates():
    result = analyze("책를 읽었다. 사과을 먹었다. 그 사람밖에 왔다.")
    assert result.counts == {"error": 1, "review": 2}
    assert result.to_dict()["status"] == "checked"
    assert result.to_dict()["rules_checked"] == ["G001", "G002", "G003"]


def test_masks_math_and_markdown_link_targets():
    text = "\\[책를 읽었다.\\]\n[안내](사과을)\n\\(사과을 먹었다.\\)"
    assert analyze(text).findings == ()


def test_does_not_join_scopes_across_masked_code():
    assert analyze("그 사람밖에 `아무 표현` 왔다.").findings == ()


def test_does_not_borrow_negation_from_another_line():
    assert [
        finding.rule_id
        for finding in analyze("민수밖에 왔다.\n영희는 안 왔다.").findings
    ] == ["G002"]
