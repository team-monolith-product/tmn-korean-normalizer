from korean_normalizer.detect import analyze, grade
from korean_normalizer.rules import build_rule


def ids_of(text: str) -> set[int]:
    return {finding.rule_id for finding in analyze(text).findings}


def test_grade_thresholds():
    assert grade({"S1": 0, "S2": 2})[0] == "A"
    assert grade({"S1": 1, "S2": 0})[0] == "B"
    assert grade({"S1": 0, "S2": 3})[0] == "B"
    assert grade({"S1": 3, "S2": 0})[0] == "C"
    assert grade({"S1": 0, "S2": 6})[0] == "C"
    assert grade({"S1": 5, "S2": 8})[0] == "D"


def test_detects_double_passive_once():
    assert 31 in ids_of("이 결과는 신중하게 분석되어집니다.")


def test_paragraph_threshold_needs_repetition():
    once = "이 문제에 대해 논의했습니다."
    twice = "이 문제에 대해 논의하고 저 사안에 대해 검토했습니다."
    assert 25 not in ids_of(once)
    assert 25 in ids_of(twice)


def test_threshold_counts_across_the_whole_document():
    """문단마다 하나씩 흩뿌려도 합쳐서 임계를 넘으면 신호다."""
    text = "이 문제에 대해 논의했습니다.\n\n저 사안에 대해 검토했습니다."
    assert 25 in ids_of(text)


def test_code_block_is_excluded_from_detection():
    text = "설명입니다.\n\n```\n분석되어집니다\n```"
    assert 31 not in ids_of(text)


def test_inline_code_is_excluded_from_detection():
    assert 31 not in ids_of("`분석되어집니다`는 코드 예시입니다.")


def test_exclude_pattern_suppresses_known_terms():
    """정착 용어만 반복되면 39번은 걸리지 않는다."""
    settled = "전략적 파트너십, 전략적 파트너십, 전략적 파트너십을 맺었다."
    assert 39 not in ids_of(settled)


def test_colon_rule_ignores_time_notation():
    assert 7 not in ids_of("회의는 오후 3:30 입니다.")


def test_metric_is_skipped_when_sample_is_small():
    report = analyze("짧다.")
    assert any(item.startswith("1:") for item in report.skipped_metrics)


def test_report_serializes_to_dict():
    payload = analyze("이 결과는 분석되어집니다.").to_dict()
    assert payload["grade"] in {"A", "B", "C", "D"}
    assert payload["findings"][0]["rule_id"] == 31
    assert payload["findings"][0]["samples"]


def test_samples_offsets_point_into_source():
    text = "이 결과는 분석되어집니다."
    finding = next(f for f in analyze(text).findings if f.rule_id == 31)
    sample = finding.samples[0]
    assert text[sample.start : sample.end] == "되어집"


def test_clean_text_grades_a():
    text = (
        "어제 비가 왔다. 우산을 챙겼다.\n\n"
        "길이 많이 막혔다. 지하철로 갈아탔고 그래도 늦었다."
    )
    assert analyze(text).grade == "A"


def test_table_rows_are_not_prose():
    """표 칸은 명사구 나열이라 품사 비율과 쉼표 지표를 왜곡한다."""
    table = "\n".join(
        f"| 1{hour}:00–1{hour}:40 | 항목 반영 — 세부 내용 정리 |" for hour in range(4)
    )
    assert ids_of(f"| 시간 | 내용 |\n|---|---|\n{table}\n") == set()


def test_headings_are_not_prose():
    """헤딩은 마크다운 표시로만 걸리고 문장부호 규칙에는 걸리지 않는다."""
    assert ids_of("## 트랙 A — 자기 학교 학생·단원 맥락 반영\n") == {117}


def test_em_dash_in_prose_is_still_caught():
    assert 6 in ids_of("이 방법은 — 널리 쓰이듯 — 효과가 있다.")


def test_team_rule_catches_indefinite_article_translation():
    assert 101 in ids_of("하나의 완벽한 결과를 냈다. 하나의 방법이 더 있다.")


def test_team_rule_catches_plural_demonstrative():
    assert 102 in ids_of("조각을 만들고 이들을 조합한다.")


def test_team_rule_catches_stacked_passive():
    assert 103 in ids_of("반복되어 사용되는 요소를 하나만 만든다.")


def test_team_rule_catches_absolute_praise():
    assert 104 in ids_of("완벽한 웹 페이지를 만든다.")


def test_team_rules_leave_plain_korean_alone():
    text = "어제 비가 왔다. 우산을 챙겼다.\n\n길이 막혀 지하철로 갈아탔다."
    assert ids_of(text) & {101, 102, 103, 104} == set()


def test_team_rule_catches_hype_spread_across_the_document():
    """패턴 38은 한 문단 군집만 본다. 문서 전체에 흩뿌려진 과장은 105가 잡는다."""
    text = "\n\n".join(
        [
            "이 회사는 독보적인 모델을 갖췄다. 지난 분기에 시장에서 자리를 잡았다.",
            "매출이 폭증했다. 지난해 실적을 크게 넘어서는 숫자를 기록했다.",
            "효율을 극대화했다. 운영 비용을 줄이려고 조직을 다시 짰다.",
            "주가가 급상승했다. 투자자들이 이 종목으로 몰려들기 시작했다.",
            "점유율을 대폭 늘렸다. 같은 기간에 경쟁사를 앞질렀다고 밝혔다.",
            "압도적인 성과를 냈다. 업계 전반이 이 흐름을 주목하고 있다.",
            "다음 분기 계획을 세웠다. 공장 두 곳을 새로 짓기로 결정했다.",
            "채용도 늘린다. 연구 인력을 중심으로 백 명을 더 뽑을 예정이다.",
        ]
    )
    assert 105 in ids_of(text)
    assert 38 not in ids_of(text)


def test_team_rule_catches_every_parenthesis():
    """팀 답변 스타일은 괄호 부연을 예외 없이 금지한다."""
    assert 106 in ids_of("결과가 IPO(상장)로 이어졌다.")
    assert 106 in ids_of("Y Combinator(YC)는 액셀러레이터다.")
    assert 106 in ids_of("전각 괄호（부연）도 잡는다.")


def test_parenthesis_rule_ignores_code_and_link_targets():
    """코드와 링크 타깃의 괄호는 문장부호가 아니다."""
    assert 106 not in ids_of("`function App() {}` 을 정의한다.")
    assert 106 not in ids_of("[문서](https://example.com/a(b))를 보라.")


def test_prose_without_parentheses_is_clean():
    assert 106 not in ids_of("결과가 IPO로 상장하며 이어졌다.")


def test_team_rule_catches_empty_intensifiers():
    assert 108 in ids_of("## 핵심 수익 구조\n\n주요 특징을 정리한다.")


def test_empty_intensifier_rule_reads_headings():
    """공허한 강조는 헤딩에 몰린다. 헤딩이 어휘 규칙에 보여야 잡힌다."""
    assert 108 in ids_of("## 1. 핵심 수익 구조\n\n## 2. 핵심 축\n")


def test_team_rule_catches_negation_parallel_rhetoric():
    """아닌 것을 먼저 말하고 뒤집는 구성. 한 번만 나와도 신호다."""
    assert 109 in ids_of("단순한 자금 투입을 넘어 표준 절차를 결합했다.")
    assert 109 in ids_of("돈만 넣는 데서 그치지 않습니다. 절차도 묶었습니다.")
    assert 109 in ids_of("그 자리에 머무르지 않고 다음 단계로 갔다.")


def test_negation_parallel_rule_leaves_plain_prose_alone():
    assert 109 not in ids_of("어제 비가 와서 우산을 챙겼다. 길이 막혔다.")


def test_contrastive_definition_is_caught_at_first_use():
    """정정도 우회다. 처음부터 맞는 쪽만 말하면 된다."""
    assert 109 in ids_of("철수가 아니라 영희가 왔다.")
    assert 109 not in ids_of("영희가 왔다.")


def test_team_rule_filters_translation_vocabulary_without_exception():
    """catch·close·pillar 직역. 문맥을 가리지 않고 걸러낸다."""
    assert 111 in ids_of("규칙이 패턴을 잡는다.")
    assert 111 in ids_of("글을 평서로 닫는다.")
    assert 111 in ids_of("모델은 네 축으로 나뉜다.")
    assert 111 in ids_of("핵심 축이 넷이다.")


def test_translation_vocabulary_rule_spares_compound_words():
    """축약·구축·압축·건축은 합성어라 대상이 아니다."""
    text = "축약어를 설명하고 인프라를 구축하며 압축 파일을 건축 현장에 옮긴다."
    assert 111 not in ids_of(text)
    assert 111 not in ids_of("비용을 축소하고 경험을 축적한다.")


def test_translation_vocabulary_rule_leaves_plain_prose_alone():
    assert 111 not in ids_of("어제 비가 와서 우산을 챙겼다.")


def test_paragraph_scope_still_works_for_rules_that_want_it():
    """현재 규칙은 전부 문서 스코프지만 문단 단위 판정 기능은 남겨 둔다.

    규칙 14처럼 '같은 단락에 몰릴 때만 신호'가 맞는 것들이 있어 되돌릴 여지를 둔다.
    """
    rule = build_rule(
        {
            "id": 900,
            "name": "테스트용 문단 규칙",
            "severity": "S2",
            "kind": "regex",
            "pattern": "표적",
            "threshold": {"scope": "paragraph", "count": 2},
            "guidance": "g",
        },
        "test",
    )
    spread = "표적 하나입니다.\n\n표적 둘입니다."
    clustered = "표적 하나와 표적 둘입니다.\n\n다른 문단입니다."

    assert analyze(spread, (rule,)).findings == ()
    finding = analyze(clustered, (rule,)).findings[0]
    assert finding.count == 2
    assert finding.location is not None
    assert finding.location.index == 0


def test_empty_intensifier_needs_the_modifier_position():
    """필수의료·주요국은 붙여 쓰는 합성어다. 관형어가 아니다."""
    assert 108 not in ids_of("필수의료 인력이 모자란다. 주요국이 대응에 나섰다.")
    assert 108 not in ids_of("핵심은 구조에 있다. 본질은 다르다.")
    assert 108 in ids_of("핵심 정리를 붙였다.")
    assert 108 in ids_of("핵심적인 위치를 차지한다.")
