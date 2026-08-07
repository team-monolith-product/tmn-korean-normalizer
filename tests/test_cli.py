import json

import pytest

from korean_normalizer.cli import main

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
    assert "검출된 패턴이 없습니다." in capsys.readouterr().out


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
    assert output.count("\n") == 40


def test_rules_json_listing(capsys):
    assert main(["rules", "--format", "json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 40


class _FakeStdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text
