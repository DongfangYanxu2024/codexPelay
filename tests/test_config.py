from pathlib import Path

import pytest

from codepp.config import initialize_config, load_config


def test_old_config_receives_v02_defaults(tmp_path: Path):
    initialize_config(tmp_path)
    config_path = tmp_path / ".codepp" / "config.toml"
    config_path.write_text('[relay]\nprovider = "clipboard"\n', encoding="utf-8")
    config = load_config(tmp_path)
    assert config["context"]["max_memory_bytes"] == 100000
    assert config["context"]["include_staged_diff"] is False
    assert config["context"]["max_related_files"] == 12
    assert config["context"]["max_related_bytes"] == 400000
    assert config["protocol"]["max_response_bytes"] == 2000000


@pytest.mark.parametrize(
    "content,error",
    [
        ('[context]\nmax_memory_bytes = 0\n', "max_memory_bytes"),
        ('[context]\nmax_related_files = 0\n', "max_related_files"),
        ('[context]\nmax_related_bytes = true\n', "max_related_bytes"),
        ('[protocol]\nmax_response_bytes = -1\n', "max_response_bytes"),
        ('[protocol]\nmax_response_bytes = "many"\n', "max_response_bytes"),
        ('[context]\ninclude_git_diff = "yes"\n', "include_git_diff"),
        ('[security]\nredact_secrets = 1\n', "redact_secrets"),
        ('[project]\nname = ""\n', "project.name"),
        ('[patch]\nauto_apply = true\n', "auto_apply"),
    ],
)
def test_rejects_invalid_config_types(tmp_path: Path, content: str, error: str):
    initialize_config(tmp_path)
    (tmp_path / ".codepp" / "config.toml").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_config(tmp_path)


def test_rejects_unknown_sections_in_deterministic_order(tmp_path: Path):
    initialize_config(tmp_path)
    config_path = tmp_path / ".codepp" / "config.toml"
    config_path.write_text("[zebra]\nvalue = 1\n[alpha]\nvalue = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"unknown section\(s\): alpha, zebra"):
        load_config(tmp_path)


def test_rejects_unknown_keys_with_qualified_names(tmp_path: Path):
    initialize_config(tmp_path)
    config_path = tmp_path / ".codepp" / "config.toml"
    config_path.write_text("[context]\nzebra = 1\nalpha = 2\n", encoding="utf-8")
    with pytest.raises(
        ValueError,
        match=r"unknown option\(s\): context.alpha, context.zebra",
    ):
        load_config(tmp_path)


@pytest.mark.parametrize("content,section", [('context = "wide"', "context"), ("protocol = 42", "protocol")])
def test_rejects_known_sections_with_wrong_toml_type(tmp_path: Path, content: str, section: str):
    initialize_config(tmp_path)
    (tmp_path / ".codepp" / "config.toml").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{section} must be a TOML table"):
        load_config(tmp_path)


def test_accepts_explicit_positive_v03_limits(tmp_path: Path):
    initialize_config(tmp_path)
    (tmp_path / ".codepp" / "config.toml").write_text(
        """[context]
max_related_files = 3
max_related_bytes = 8192

[protocol]
max_response_bytes = 65536
""",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config["context"]["max_related_files"] == 3
    assert config["context"]["max_related_bytes"] == 8192
    assert config["protocol"]["max_response_bytes"] == 65536
