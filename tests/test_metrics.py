import pytest

from korean_normalizer import metrics
from korean_normalizer.metrics import compute, context_of, registered


def value_of(name: str, text: str) -> float | None:
    return compute(name, context_of(text))


def test_unknown_metric_raises():
    with pytest.raises(KeyError):
        value_of("nope", "아무 글")


def test_registry_exposes_every_metric():
    assert "comma_sentence_ratio" in registered()


def test_comma_sentence_ratio_counts_sentences_with_commas():
    text = "가나다, 라마바입니다. 사아자입니다. 차카타, 파하입니다. 갸냐댜입니다."
    assert value_of("comma_sentence_ratio", text) == 0.5


def test_comma_sentence_ratio_skips_short_input():
    assert value_of("comma_sentence_ratio", "짧습니다.") is None


def test_comma_relative_position_is_higher_when_commas_sit_late():
    early = "가나다, 라마바 사아자 차카타 파하 가나다 라마바입니다."
    late = "가나다 라마바 사아자 차카타 파하 가나다, 라마바입니다."
    assert value_of("comma_relative_position", early) < value_of(
        "comma_relative_position", late
    )


def test_comma_relative_position_counts_comma_free_sentences_as_zero():
    """논문 정의다. 쉼표 없는 문장을 빼면 값이 0.45 근처로 몰려 갈리지 않는다."""
    assert (
        value_of("comma_relative_position", "쉼표가 없습니다. 하나 더 없습니다.") == 0.0
    )


def test_dependent_noun_spacing_uniformity_flags_perfect_consistency():
    text = "할 수 있는 것, 하는 것, 가는 것, 오는 것, 먹는 것"
    assert value_of("dependent_noun_spacing_uniformity", text) == 1.0


def test_dependent_noun_spacing_uniformity_drops_when_mixed():
    text = "할 수 있는것, 하는 것, 가는것, 오는 것, 먹는 것"
    assert value_of("dependent_noun_spacing_uniformity", text) < 1.0


def test_dependent_noun_spacing_needs_enough_samples():
    assert value_of("dependent_noun_spacing_uniformity", "하는 것") is None


def test_auxiliary_verb_spacing_uniformity():
    text = "가고 있다 보고 있다 먹고 있다 자고 있다 읽고 있다"
    assert value_of("auxiliary_verb_spacing_uniformity", text) == 1.0


def test_sentence_length_cv_is_low_for_uniform_sentences():
    sentence = "가나다라마바사입니다."
    assert value_of("sentence_length_cv", " ".join([sentence] * 4)) < 0.15


def test_sentence_length_cv_needs_four_sentences():
    assert value_of("sentence_length_cv", "하나. 둘. 셋.") is None


def test_conjunction_sentence_ratio():
    text = "비가 왔다. 그러나 나갔다. 따라서 젖었다. 그리고 감기에 걸렸다."
    assert value_of("conjunction_sentence_ratio", text) == 0.75


def test_conjunction_sentence_ratio_skips_short_input():
    assert value_of("conjunction_sentence_ratio", "짧다.") is None


def test_ending_uniformity_is_one_when_style_never_varies():
    text = "하나입니다. 둘입니다. 셋입니다. 넷입니다. 다섯입니다."
    assert value_of("ending_uniformity", text) == 1.0


def test_ending_uniformity_drops_when_style_varies():
    text = "하나입니다. 둘이에요. 셋입니다. 넷입니다. 다섯입니다."
    assert value_of("ending_uniformity", text) == 0.8


def test_ending_uniformity_needs_five_classified_sentences():
    assert value_of("ending_uniformity", "하나입니다. 둘입니다.") is None


def test_repeated_subject_runs_counts_the_longest_streak():
    text = "나는 일어났다. 나는 커피를 마셨다. 나는 출근했다. 그는 잤다."
    assert value_of("repeated_subject_runs", text) == 3.0


def test_repeated_subject_runs_is_low_when_subjects_alternate():
    text = "철수는 갔다. 영희는 왔다. 철수는 잤다."
    assert value_of("repeated_subject_runs", text) == 1.0


def test_hype_density_separates_marketing_prose_from_plain_prose():
    hyped = "압도적인 성장과 독보적인 기술로 매출이 폭증하며 효율을 극대화한다. " * 12
    plain = "어제 비가 와서 우산을 챙겼다. 길이 막혀 지하철로 갈아탔다. " * 12
    assert value_of("hype_density", hyped) > 1.5
    assert value_of("hype_density", plain) == 0.0


def test_hype_density_skips_short_text():
    assert value_of("hype_density", "압도적인 성장이다.") is None


CHOPPY = (
    "김치찌개는 쉽다.\n신김치가 필수다.\n안 시면 맛이 안 난다.\n"
    "고기는 목살이 낫다.\n기름이 있어야 한다.\n볶는 게 핵심이다.\n"
)
FLOWING = (
    "김치찌개를 맛있게 끓이려면 신김치가 있어야 하고, 안 시면 감칠맛이 나지 않는다.\n"
    "고기는 지방이 붙은 목살이 국물 맛을 내는 데 유리하며 삼겹살로 대신해도 괜찮다.\n"
    "김치를 기름에 볶아야 신맛이 날아가고 감칠맛이 올라오므로 건너뛰면 안 된다.\n"
    "물을 붓고 센불로 끓인 뒤 중불로 낮춰 스무 해쯤 두면 국물이 진해진다.\n"
    "두부와 양파는 마지막에 넣어야 형태가 유지되고 대파는 불을 끄기 직전에 올린다.\n"
)


def test_short_sentence_ratio_separates_choppy_from_flowing():
    assert value_of("short_sentence_ratio", CHOPPY) > 0.30
    assert value_of("short_sentence_ratio", FLOWING) < 0.30


def test_short_sentence_ratio_ignores_list_items():
    """목록 항목은 원래 짧은 단위라 문장 통계에 넣지 않는다."""
    listed = FLOWING + "\n".join(f"- 항목 {n}" for n in range(8))
    assert value_of("short_sentence_ratio", listed) < 0.30


def test_short_sentence_ratio_needs_enough_prose():
    assert value_of("short_sentence_ratio", "짧다.\n또 짧다.") is None


def test_intensifier_density_counts_emphasis_adverbs():
    hyped = "이건 완전히 다르고 매우 중요하며 정말 아주 굉장히 좋은 선택이다. " * 12
    plain = "어제 비가 와서 우산을 챙겼다. 길이 막혀 지하철로 갈아탔다. " * 12
    assert value_of("intensifier_density", hyped) > 0.6
    assert value_of("intensifier_density", plain) == 0.0


def test_comma_metrics_need_the_analyzer(monkeypatch):
    """형태소 분석기가 없으면 쉼표 지표는 판정하지 않는다."""
    monkeypatch.setattr(metrics, "_tokens_per_sentence", lambda text: None)
    for name in (
        "comma_relative_position",
        "comma_morpheme_rate",
        "comma_segment_length",
    ):
        assert value_of(name, "쉼표가, 있는, 문장입니다.") is None
