from korean_normalizer.detect import analyze, grade


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


def test_threshold_counts_per_paragraph_not_document():
    """단락마다 1회씩이면 임계 2를 넘지 않는다."""
    text = "이 문제에 대해 논의했습니다.\n\n저 사안에 대해 검토했습니다."
    assert 25 not in ids_of(text)


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
