from korean_normalizer.segment import (
    PLACEHOLDER,
    Document,
    Span,
    build_mask,
    merge_spans,
    overlaps,
    protected_spans,
    scrub,
    split_paragraphs,
    split_sentences,
)


def test_splits_paragraphs_on_blank_lines():
    paragraphs = split_paragraphs("첫 문단입니다.\n\n둘째 문단입니다.")
    assert [segment.text for segment in paragraphs] == [
        "첫 문단입니다.",
        "둘째 문단입니다.",
    ]


def test_paragraph_offsets_point_into_source():
    text = "첫 문단입니다.\n\n둘째 문단입니다."
    for segment in split_paragraphs(text):
        assert text[segment.start : segment.end] == segment.text


def test_splits_sentences_on_terminators_and_newlines():
    sentences = split_sentences("하나입니다. 둘입니다!\n셋입니다?")
    assert [segment.text for segment in sentences] == [
        "하나입니다.",
        "둘입니다!",
        "셋입니다?",
    ]


def test_scrub_hides_fenced_code_but_keeps_length():
    text = "설명입니다.\n\n```\n되어집니다\n```\n\n끝입니다."
    scrubbed = scrub(text, build_mask(text))
    assert len(scrubbed) == len(text)
    assert "되어집니다" not in scrubbed
    assert "설명입니다." in scrubbed


def test_scrub_hides_inline_code_and_urls():
    text = "`되어진다`를 https://example.com/되어진다 에서 봤습니다."
    scrubbed = scrub(text, build_mask(text))
    assert "되어진다" not in scrubbed
    assert scrubbed.count(PLACEHOLDER) > 0


def test_scrub_preserves_newlines():
    text = "```\n줄\n바꿈\n```"
    assert scrub(text, build_mask(text)).count("\n") == text.count("\n")


def test_direct_quotes_are_protected_from_fixes_but_still_detected():
    text = '그는 "분석되어집니다"라고 적었다.'
    quote = text.index('"')
    assert overlaps(protected_spans(text), quote, quote + 1)
    assert "분석되어집니다" in scrub(text, build_mask(text))


def test_protected_spans_cover_code_and_urls():
    text = "`코드` 설명 https://a.b"
    spans = protected_spans(text)
    assert [text[span.start : span.end] for span in spans] == ["`코드`", "https://a.b"]


def test_overlaps_is_exclusive_at_the_boundary():
    spans = (Span(5, 10),)
    assert overlaps(spans, 4, 6) is True
    assert overlaps(spans, 10, 12) is False
    assert overlaps(spans, 3, 5) is False


def test_merge_spans_collapses_overlaps():
    merged = merge_spans([Span(0, 5), Span(3, 8), Span(20, 22)])
    assert merged == (Span(0, 8), Span(20, 22))


def test_document_shares_one_paragraph_split():
    text = "첫 문단입니다.\n\n둘째 문단입니다."
    document = Document.of(text)
    assert document.source == text
    assert document.paragraphs == split_paragraphs(document.scrubbed)
