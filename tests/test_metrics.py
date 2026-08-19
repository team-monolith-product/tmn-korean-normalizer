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
    early = "가, 나다라마바사아자차카타파하입니다."
    late = "가나다라마바사아자차카타파하, 입니다."
    assert value_of("comma_relative_position", early) < value_of(
        "comma_relative_position", late
    )


def test_comma_relative_position_needs_a_comma():
    assert value_of("comma_relative_position", "쉼표가 없습니다.") is None


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


def test_pos_metrics_are_skipped_without_kiwipiepy(monkeypatch):
    monkeypatch.setattr(metrics, "_kiwi_tags", lambda text: None)
    assert value_of("noun_ratio", "명사 비율을 잰다.") is None
    assert value_of("verb_adjective_ratio", "명사 비율을 잰다.") is None
    assert value_of("pos_trigram_diversity", "명사 비율을 잰다.") is None


def test_pos_metrics_use_tags_when_available(monkeypatch):
    tags = ["NNG", "JKO", "VV", "EF", "NNG", "NNP", "VA"] * 10
    monkeypatch.setattr(metrics, "_kiwi_tags", lambda text: tags)
    assert value_of("noun_ratio", "무시됨") == pytest.approx(3 / 5)
    assert value_of("verb_adjective_ratio", "무시됨") == pytest.approx(2 / 5)
    assert value_of("pos_trigram_diversity", "무시됨") < 0.2


def test_pos_metrics_skip_short_text(monkeypatch):
    """짧은 글은 비율이 요동치므로 판정하지 않는다."""
    tags = ["NNG", "JKO", "VV", "EF"]
    monkeypatch.setattr(metrics, "_kiwi_tags", lambda text: tags)
    assert value_of("noun_ratio", "무시됨") is None
    assert value_of("verb_adjective_ratio", "무시됨") is None
    assert value_of("pos_trigram_diversity", "무시됨") is None


def test_hype_density_separates_marketing_prose_from_plain_prose():
    hyped = "압도적인 성장과 독보적인 기술로 매출이 폭증하며 효율을 극대화한다. " * 12
    plain = "어제 비가 와서 우산을 챙겼다. 길이 막혀 지하철로 갈아탔다. " * 12
    assert value_of("hype_density", hyped) > 1.5
    assert value_of("hype_density", plain) == 0.0


def test_hype_density_skips_short_text():
    assert value_of("hype_density", "압도적인 성장이다.") is None
