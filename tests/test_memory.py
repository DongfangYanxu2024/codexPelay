from pathlib import Path

from codepp.config import DEFAULT_CONFIG, initialize_config
from codepp.core.memory import collect_memory


def memory_config(limit: int = 100000) -> dict:
    config = {key: value.copy() for key, value in DEFAULT_CONFIG.items()}
    config["context"]["max_memory_bytes"] = limit
    return config


def test_collects_all_text_memory_with_redaction(tmp_path: Path):
    initialize_config(tmp_path)
    memory = tmp_path / ".codepp" / "memory"
    (memory / "architecture.md").write_text("Layers: CLI -> core\n", encoding="utf-8")
    (memory / "commands.txt").write_text("TOKEN=private-value\npytest\n", encoding="utf-8")
    (memory / "ignored.json").write_text("{}\n", encoding="utf-8")
    result = collect_memory(tmp_path, [], memory_config())
    assert [item.path for item in result] == ["memory/architecture.md", "memory/commands.txt"]
    assert "private-value" not in result[1].content
    assert result[1].redactions == 1


def test_collects_selected_memory_and_reports_missing(tmp_path: Path):
    initialize_config(tmp_path)
    memory = tmp_path / ".codepp" / "memory"
    (memory / "decisions.md").write_text("Use argparse.\n", encoding="utf-8")
    result = collect_memory(tmp_path, ["decisions.md", "missing.md"], memory_config())
    assert result[0].content.splitlines() == ["Use argparse."]
    assert result[1].omitted
    assert "does not exist" in result[1].content


def test_memory_budget_and_path_boundary(tmp_path: Path):
    initialize_config(tmp_path)
    memory = tmp_path / ".codepp" / "memory"
    (memory / "large.md").write_text("x" * 20, encoding="utf-8")
    result = collect_memory(tmp_path, ["large.md", "../outside.md"], memory_config(10))
    assert result[0].omitted
    assert "budget" in result[0].content
    assert result[1].omitted
    assert "outside" in result[1].content


def test_rejects_unsupported_memory_type(tmp_path: Path):
    initialize_config(tmp_path)
    memory = tmp_path / ".codepp" / "memory"
    (memory / "data.json").write_text("{}\n", encoding="utf-8")
    result = collect_memory(tmp_path, ["data.json"], memory_config())
    assert result[0].omitted
    assert ".md or .txt" in result[0].content
