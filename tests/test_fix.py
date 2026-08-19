import pytest

from korean_normalizer.detect import analyze
from korean_normalizer.fix import apply, diff


def fixed(text: str) -> str:
    return apply(text).text


def test_double_passive_becomes_single_or_active():
    assert fixed("결과가 분석되어집니다.") == "결과가 분석됩니다."
    assert fixed("검증되어진 자료") == "검증된 자료"
    assert fixed("결정되어졌다") == "결정됐다"


def test_formal_borrowing_returns_to_eseo():
    assert fixed("현대 사회에 있어서 데이터가 중요하다") == (
        "현대 사회에서 데이터가 중요하다"
    )


def test_demonstrative_is_replaced_after_threshold():
    text = "해당 기능은 해당 결과를 냈다. 해당 방법을 쓴다."
    assert "해당" not in fixed(text)


def test_demonstrative_below_threshold_is_left_alone():
    assert fixed("해당 기능을 켰다.") == "해당 기능을 켰다."


def test_plural_removal_repairs_josa():
    text = "많은 사용자들이 왔고 여러 참가자들을 만났으며 각종 자료들이 쌓였다."
    result = fixed(text)
    assert "사용자가" in result
    assert "참가자를" in result
    assert "자료가" in result


def test_plural_removal_keeps_idiomatic_yeoreobun():
    text = "여러분들 안녕하세요. 여러분들 반갑습니다. 여러분들 고맙습니다."
    assert "여러분들" in fixed(text)


def test_connective_comma_is_removed_after_threshold():
    text = "날씨가 좋아서, 나갔고, 친구를 만나서, 즐거웠다."
    result = fixed(text)
    assert "좋아서 " in result
    assert "만나서 " in result


def test_em_dash_pair_becomes_parentheses():
    assert fixed("이 방법은 — 널리 쓰이듯 — 효과가 있다.") == (
        "이 방법은 (널리 쓰이듯) 효과가 있다."
    )


def test_colon_after_predicate_becomes_period():
    assert (
        fixed("설치 방법은 다음과 같습니다:\n- a")
        == "설치 방법은 다음과 같습니다.\n- a"
    )


def test_label_colon_is_dropped():
    assert fixed("주요 특징:\n1. 속도") == "주요 특징\n1. 속도"


def test_closing_idiom_is_deleted():
    assert fixed("결론적으로, 이 전략은 옳았다.") == "이 전략은 옳았다."


def test_sino_korean_verb_is_simplified():
    text = "회의를 진행하고 점검을 실시하며 검토를 수행한다."
    assert fixed(text) == "회의를 하고 점검을 하며 검토를 한다."


def test_direct_quote_is_never_touched():
    text = '보고서에 "분석되어집니다"라고 적혀 있다. 결과도 검증되어집니다.'
    result = fixed(text)
    assert '"분석되어집니다"' in result
    assert "검증됩니다" in result


def test_anchored_rules_respect_real_line_ends():
    """보호 구간을 기준으로 조각내면 ^ $ 앵커가 조각 끝을 줄 끝으로 착각한다."""
    text = "주요 특징:\n1. 속도\n\n설치 방법은 다음과 같습니다: `npm i` 를 실행하세요."
    result = fixed(text)
    assert "주요 특징\n" in result
    assert "다음과 같습니다: `npm i`" in result


def test_code_block_is_never_touched():
    text = "설명이 필요합니다.\n\n```py\n# 분석되어집니다\n```"
    assert "# 분석되어집니다" in fixed(text)


def test_fix_is_idempotent():
    text = "결과가 분석되어집니다. 현대 사회에 있어서 중요하다."
    once = fixed(text)
    assert fixed(once) == once


def test_changes_are_reported():
    result = apply("결과가 분석되어집니다.")
    assert [change.rule_id for change in result.changes] == [31]
    assert result.replaced == 1
    assert result.to_dict()["replacements"] == 1


def test_untouched_text_reports_no_change():
    result = apply("어제 비가 왔다. 우산을 챙겼다.")
    assert result.changes == ()
    assert result.text == "어제 비가 왔다. 우산을 챙겼다."


def test_diff_renders_unified_format():
    output = diff("가나다\n", "가나라\n", label="sample.md")
    assert "--- a/sample.md" in output
    assert "+가나라" in output


AI_SAMPLES = [
    "결과가 분석되어집니다. 현대 사회에 있어서 데이터가 중요하다.",
    "해당 기능은 해당 결과를 냈다. 해당 방법을 쓴다.",
    "날씨가 좋아서, 나갔고, 친구를 만나서, 즐거웠다.",
    "결론적으로, 많은 사용자들이 여러 기능들을 각종 방법들로 요청했다.",
    "회의를 진행하고 점검을 실시하며 검토를 수행한다.",
    "이 방법은 — 널리 쓰이듯 — 효과가 있다. 설치는 다음과 같습니다:\n- a",
]


@pytest.mark.parametrize("sample", AI_SAMPLES)
def test_fix_never_worsens_the_grade(sample):
    """검출 정규식과 교정 정규식이 어긋나면 여기서 잡힌다."""
    before = analyze(sample).counts
    after = analyze(fixed(sample)).counts
    assert after["S1"] <= before["S1"]
    assert after["S2"] <= before["S2"]


@pytest.mark.parametrize("sample", AI_SAMPLES)
def test_fix_is_idempotent_across_samples(sample):
    once = fixed(sample)
    assert fixed(once) == once


def test_table_row_with_a_time_range_survives():
    """en-dash 시간 범위와 em-dash가 한 줄에 있으면 표가 통째로 깨졌다."""
    row = "| 13:00–13:40 (40분) | 학생 수준 반영 — 우리 반에 맞게 변형 |"
    text = f"설명입니다. 아래 표를 보십시오.\n\n{row}\n"
    assert row in fixed(text)


def test_en_dash_between_numbers_is_not_a_rhetorical_dash():
    text = "행사는 13:00–15:00 에 열린다. 준비는 09:00–10:00 에 한다."
    assert fixed(text) == text


def test_empty_intensifier_is_removed_from_modifier_position():
    text = "## 핵심 수익 구조\n\n주요 특징을 본다. 두 가지 핵심 알고리즘을 쓴다."
    result = fixed(text)
    assert "## 수익 구조" in result
    assert "특징을 본다" in result
    assert "두 가지 알고리즘을 쓴다" in result


def test_empty_intensifier_survives_where_deleting_breaks_the_sentence():
    """'핵심적인 위치'는 형용사가 서술을 떠받치고 '핵심이 된다'는 명사다."""
    text = (
        "핵심적인 위치를 차지한다. 주요 지표를 본다.\n\n"
        "지연 단축의 핵심이 된다. 핵심을 짚었다."
    )
    result = fixed(text)
    assert "핵심적인 위치를 차지한다" in result
    assert "핵심이 된다" in result
    assert "핵심을 짚었다" in result


def test_fix_never_merges_paragraphs():
    """치환 패턴의 꼬리 \\s*가 문단 사이 빈 줄을 먹으면 안 된다.

    문단 스코프 규칙이 없어도 apply의 문단 순회가 이걸 막는다. 지우지 말 것.
    """
    text = "이 전략은 옳았다. 결론적으로,\n\n다음 분기에도 이어간다."
    result = fixed(text)
    assert "결론적으로" not in result
    assert result == "이 전략은 옳았다. \n\n다음 분기에도 이어간다."


def test_rules_that_replace_nothing_are_absent_from_changes():
    result = apply("결과가 분석되어집니다. 핵심 지표와 주요 항목을 본다.")
    assert all(change.replacements > 0 for change in result.changes)
    assert {change.rule_id for change in result.changes} == {31, 108}
