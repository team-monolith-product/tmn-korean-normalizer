from korean_normalizer.josa import agree, has_batchim


def test_detects_batchim():
    assert has_batchim("학생") is True
    assert has_batchim("사용자") is False


def test_returns_none_for_non_hangul():
    assert has_batchim("") is None
    assert has_batchim("API") is None


def test_agrees_after_vowel():
    assert agree("사용자", "이") == "가"
    assert agree("사용자", "은") == "는"
    assert agree("사용자", "을") == "를"


def test_agrees_after_batchim():
    assert agree("학생", "가") == "이"
    assert agree("학생", "는") == "은"
    assert agree("학생", "로") == "으로"


def test_keeps_unknown_or_unjudgeable_josa():
    assert agree("사용자", "에서") == "에서"
    assert agree("API", "이") == "이"
    assert agree("사용자", "") == ""
