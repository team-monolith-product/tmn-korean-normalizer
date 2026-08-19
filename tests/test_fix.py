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
    assert fixed("설치 방법은 다음과 같습니다:\n- a").startswith(
        "설치 방법은 다음과 같습니다."
    )


def test_label_colon_is_dropped():
    """콜론과 함께 공허한 관형어 '주요'도 지워진다."""
    assert fixed("주요 특징:\n1. 속도") == "특징. 속도"


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
    assert result.startswith("특징. 속도")
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
    text = "핵심 수익 구조를 본다.\n\n주요 특징을 본다. 두 가지 핵심 알고리즘을 쓴다."
    result = fixed(text)
    assert result.startswith("수익 구조를 본다.")
    assert "특징을 본다" in result
    assert "두 가지 알고리즘을 쓴다" in result


def test_empty_intensifier_covers_all_seven_words():
    text = (
        "핵심 정리를 붙였다. 근본 이유를 찾는다.\n\n"
        "본질적으로 다르다. 필수 조건이다. 궁극 목표는 하나다. 총체적 난국이다."
    )
    result = fixed(text)
    for word in ("핵심", "근본", "본질", "필수", "궁극", "총체"):
        assert word not in result
    assert "정리를 붙였다" in result
    assert "이유를 찾는다" in result


def test_empty_intensifier_spares_compounds_and_head_nouns():
    """필수의료는 고유 용어고 '핵심은 X다'의 핵심은 주어다."""
    text = "필수의료 인력이 모자란다. 주요국이 나섰다.\n\n핵심은 구조에 있다."
    result = fixed(text)
    assert "필수의료 인력" in result
    assert "주요국이" in result
    assert "핵심은 구조에" in result


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


def test_work_titles_get_proper_brackets():
    """영화·노래 제목은 홑화살괄호를 쓴다. 아스키 꺾쇠는 문장부호가 아니다."""
    assert fixed("<로망스>를 들었다.") == "〈로망스〉를 들었다."
    assert fixed("영화 <금지된 장난>을 봤다.") == "영화 〈금지된 장난〉을 봤다."


def test_html_tags_are_not_work_titles():
    text = "설명입니다.\n\n<div>내용</div> 과 <https://a.b> 를 남긴다."
    assert "<div>" in fixed(text)
    assert "<https://a.b>" in fixed(text)


def test_closing_label_line_is_deleted():
    text = "본문입니다.\n\n한 줄 요약\n\n로망스는 사랑 이야기입니다.\n"
    result = fixed(text)
    assert "한 줄 요약" not in result
    assert "로망스는 사랑 이야기입니다." in result


def test_closing_label_with_content_after_it_survives():
    """'요약: 비교표'처럼 뒤에 내용이 붙으면 표제가 아니라 지우지 않는다."""
    text = "본문입니다.\n\n요약: 비교표를 실었습니다.\n\n내용입니다.\n"
    assert "요약: 비교표를 실었습니다." in fixed(text)


def test_announcement_paragraph_is_deleted():
    """무엇을 하겠다고 예고하지 말고 바로 한다."""
    text = (
        "로망스는 맥락에 따라 다릅니다.\n\n"
        "세 영역을 정리해 드릴게요.\n\n"
        "첫째는 문학입니다."
    )
    result = fixed(text)
    assert "정리해 드릴게요" not in result
    assert "로망스는 맥락에 따라 다릅니다." in result
    assert "첫째는 문학입니다." in result


def test_announcement_inside_a_longer_paragraph_survives():
    """문단 안에 섞인 문장은 실제 약속일 수 있어 사람이 판단한다."""
    text = (
        "문의를 받았습니다.\n\n"
        "담당자가 확인 후 정리해 드리겠습니다. 접수 순서대로 처리합니다."
    )
    assert "정리해 드리겠습니다" in fixed(text)


MARKDOWN_HEAVY = (
    "## 1. 핵심 정리\n\n"
    "- **첫째**: 내용이 있다\n- **둘째**: 내용이 있다\n- **셋째**: 내용이 있다\n\n"
    "---\n\n## 2. 다음\n\n- **넷째**: 내용이 있다\n- **다섯째**: 내용이 있다\n"
)


def test_markdown_markers_are_stripped():
    result = fixed(MARKDOWN_HEAVY)
    for marker in ("**", "## ", "---", "- "):
        assert marker not in result
    assert "첫째: 내용이 있다" in result


def test_symbol_bullets_and_numbering_are_stripped():
    text = (
        "핵심 정리를 붙였다.\n\n"
        "① 원문자 항목\n• 불릿 항목\n※ 참고 항목\n"
        "> 인용문이다\n💡 이모지 항목\n2) 번호 항목\n"
    )
    result = fixed(text)
    for marker in ("①", "•", "※", "> ", "💡", "2) "):
        assert marker not in result
    assert "원문자 항목" in result
    assert "번호 항목" in result


def test_year_is_not_mistaken_for_a_list_number():
    """번호 표시는 두 자리까지다. 2026. 은 연도다."""
    text = "핵심 정리를 붙였다.\n\n2026. 3. 5. 회의가 있었다. 다음 문장이다."
    assert "2026. 3. 5." in fixed(text)


def test_headings_go_even_in_a_mostly_prose_document():
    """표시 하나면 지운다. 밀도로 재던 시절에는 이런 글에 헤딩이 남았다."""
    text = (
        "## 제목\n\n"
        "전세 제도가 한국에만 있는 이유는 금융 환경에 있다.\n"
        "은행 대출이 어렵던 시절 집주인이 세입자 보증금을 사금융처럼 썼다.\n"
        "이 구조는 집값이 오를 때만 굴러가고 내릴 때 무너진다.\n"
        "최근 사고가 반복되는 것도 같은 이유다.\n"
        "보증금을 돌려줄 현금이 없는 집주인이 늘었다.\n"
    )
    result = fixed(text)
    assert "제목" not in result
    assert result.startswith("전세 제도가")


def test_headings_are_deleted_with_their_text():
    """기호만 떼면 서술 없는 한 줄이 남아 비문이 된다. 줄째로 지운다."""
    text = "## 콘웨이 법칙\n\n조직 구조가 설계에 드러납니다.\n"
    assert fixed(MARKDOWN_HEAVY + "\n" + text).endswith(
        "조직 구조가 설계에 드러납니다.\n"
    )


def test_list_items_become_one_paragraph():
    result = fixed(MARKDOWN_HEAVY)
    assert "첫째: 내용이 있다. 둘째: 내용이 있다. 셋째: 내용이 있다" in result
    assert "\n첫째" not in result


def test_tables_keep_their_line_structure():
    text = MARKDOWN_HEAVY + "\n| 구분 | 값 |\n| --- | --- |\n| 가 | 나 |\n"
    result = fixed(text)
    assert "| 구분 | 값 |\n| --- | --- |\n| 가 | 나 |" in result


TABLE = "| 항목 | 값 |\n| --- | --- |\n| **굵게** | 13:00–13:40 (40분) — 비고 |\n"


def test_bold_inside_table_cells_is_stripped():
    assert "**" not in fixed(MARKDOWN_HEAVY + "\n" + TABLE)


def test_punctuation_rules_still_leave_tables_alone():
    """줄표 규칙이 칸 구분자를 넘으면 표가 깨진다."""
    text = "글이 길다 — 그래서 나눈다. " * 6 + "\n\n" + TABLE
    assert "13:00–13:40 (40분) — 비고" in fixed(text)
