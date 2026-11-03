import json
from pathlib import Path

import pytest

from korean_normalizer.cli import main
from korean_normalizer.rules import load_rules

AI_TEXT = "결과가 분석되어집니다. 현대 사회에 있어서 데이터가 중요하다.\n"


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(AI_TEXT, encoding="utf-8")
    return path


def test_detect_text_output(sample, capsys):
    assert main(["detect", str(sample)]) == 0
    output = capsys.readouterr().out
    assert "자연도 등급:" in output
    assert "패턴 31" in output


def test_detect_json_output(sample, capsys):
    assert main(["detect", str(sample), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["S1"] >= 1


def test_detect_fail_on_finding_sets_exit_code(sample):
    assert main(["detect", str(sample), "--fail-on-finding"]) == 1


def test_detect_reports_clean_text(tmp_path, capsys):
    path = tmp_path / "clean.md"
    path.write_text("어제 비가 왔다. 우산을 챙겼다.\n", encoding="utf-8")
    assert main(["detect", str(path), "--fail-on-finding"]) == 0
    assert "검출된 AI 문체 패턴이 없습니다." in capsys.readouterr().out


def test_detect_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _FakeStdin(AI_TEXT))
    assert main(["detect"]) == 0
    assert "패턴 31" in capsys.readouterr().out


def test_fix_writes_to_stdout(sample, capsys):
    assert main(["fix", str(sample)]) == 0
    assert "분석됩니다" in capsys.readouterr().out


def test_fix_diff_mode(sample, capsys):
    assert main(["fix", str(sample), "--diff"]) == 0
    assert "+결과가 분석됩니다" in capsys.readouterr().out


def test_fix_in_place(sample, capsys):
    assert main(["fix", str(sample), "--in-place"]) == 0
    assert "분석됩니다" in sample.read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["replacements"] >= 1


def test_fix_in_place_requires_a_path(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin(AI_TEXT))
    with pytest.raises(SystemExit):
        main(["fix", "--in-place"])


def test_rules_listing(capsys):
    assert main(["rules"]) == 0
    output = capsys.readouterr().out
    assert "tier A" in output
    assert output.count("\n") == len(load_rules())


def test_rules_json_listing(capsys):
    assert main(["rules", "--format", "json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == len(load_rules())


class _FakeStdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def test_missing_file_reports_cleanly_without_a_traceback():
    with pytest.raises(SystemExit) as failure:
        main(["detect", "/없는/경로.md"])
    assert "입력을 읽을 수 없습니다" in str(failure.value)


def test_shipped_example_is_readable(capsys):
    example = Path(__file__).resolve().parent.parent / "examples" / "ai-sample.md"
    assert main(["detect", str(example)]) == 0
    assert "자연도 등급: C" in capsys.readouterr().out


def test_detect_includes_grammar_in_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _FakeStdin("책를 읽었다."))
    assert main(["detect", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["grammar"]["counts"] == {"error": 1, "review": 0}
    assert payload["grammar"]["findings"][0]["text"] == "를"


def test_detect_text_includes_grammar_and_fail_status(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _FakeStdin("내 목표는 개발자가 되고 싶다."))
    assert main(["detect", "--fail-on-finding"]) == 1
    output = capsys.readouterr().out
    assert "G003" in output
    assert "검토 후보 1건" in output


def test_fix_preserves_grammar_review_candidates(monkeypatch, capsys):
    text = "내 목표는 개발자가 되고 싶다."
    monkeypatch.setattr("sys.stdin", _FakeStdin(text))
    assert main(["fix"]) == 0
    assert capsys.readouterr().out == text


def test_detect_explains_when_grammar_is_skipped(monkeypatch, capsys):
    from korean_normalizer import grammar

    monkeypatch.setattr(grammar, "get_analyzer", lambda: None)
    monkeypatch.setattr("sys.stdin", _FakeStdin("책를 읽었다."))
    assert main(["detect"]) == 0
    assert "비문 검사 건너뜀" in capsys.readouterr().out


def test_detect_preserves_file_offsets_with_crlf(tmp_path, capsys):
    text = "설명입니다.\r\n🙂 책를 읽었다.\r\n"
    path = tmp_path / "crlf.md"
    path.write_bytes(text.encode("utf-8"))
    assert main(["detect", str(path), "--format", "json"]) == 0
    finding = json.loads(capsys.readouterr().out)["grammar"]["findings"][0]
    assert (finding["line"], finding["column"]) == (2, 4)
    assert text[finding["start"] : finding["end"]] == "를"


def test_detect_rejects_non_utf8_without_a_traceback(tmp_path):
    path = tmp_path / "invalid.md"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(SystemExit, match="입력을 읽을 수 없습니다"):
        main(["detect", str(path)])


def test_detect_explains_when_middle_dot_check_is_skipped(monkeypatch, capsys):
    from korean_normalizer import matchers

    monkeypatch.setattr(matchers, "get_analyzer", lambda: None)
    monkeypatch.setattr(
        "sys.stdin", _FakeStdin("모집 페이지 · 홍보 자료 · 채널 가이드")
    )
    assert main(["detect"]) == 0
    assert "41:middle_dot_enumeration" in capsys.readouterr().out
