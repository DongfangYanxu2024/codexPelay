from copy import deepcopy
from pathlib import Path
import tomllib

from .utils.encoding import write_text
from .core.paths import safe_codepp_path


DEFAULT_CONFIG = {
    "project": {"name": "auto"},
    "relay": {"provider": "clipboard"},
    "context": {
        "max_file_bytes": 200000,
        "max_memory_bytes": 100000,
        "max_related_files": 12,
        "max_related_bytes": 400000,
        "include_git_diff": True,
        "include_staged_diff": False,
        "include_git_status": True,
        "include_project_metadata": True,
    },
    "security": {
        "redact_secrets": True,
        "respect_gitignore": True,
        "respect_codeppignore": True,
    },
    "patch": {"auto_validate": True, "auto_apply": False},
    "protocol": {"max_response_bytes": 2000000},
    "output": {"language": "auto"},
}

DEFAULT_CONFIG_TEXT = """[project]
name = "auto"

[relay]
provider = "clipboard"

[context]
max_file_bytes = 200000
max_memory_bytes = 100000
max_related_files = 12
max_related_bytes = 400000
include_git_diff = true
include_staged_diff = false
include_git_status = true
include_project_metadata = true

[security]
redact_secrets = true
respect_gitignore = true
respect_codeppignore = true

[patch]
auto_validate = true
auto_apply = false

[protocol]
max_response_bytes = 2000000

[output]
language = "auto"
"""

DEFAULT_IGNORE_TEXT = """# Secrets
.env
.env.*
*.pem
*.key
*.crt
*.p12
*.pfx
credentials*
secrets*
private/

# Dependencies and generated output
node_modules/
vendor/
dist/
build/
target/

# Tooling
.git/
.codepp/
.idea/
.vscode/

# Local data
*.sqlite
*.db
data/
datasets/
"""


def _merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(root: Path) -> dict:
    path = safe_codepp_path(root, "config.toml")
    try:
        with path.open("rb") as handle:
            loaded = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid Code++ config: {exc}") from exc
    unknown_sections = sorted(set(loaded) - set(DEFAULT_CONFIG))
    if unknown_sections:
        raise ValueError(
            f"invalid Code++ config: unknown section(s): {', '.join(unknown_sections)}"
        )
    for section, defaults in DEFAULT_CONFIG.items():
        if section not in loaded:
            continue
        if not isinstance(loaded[section], dict):
            raise ValueError(f"invalid Code++ config: {section} must be a TOML table")
        unknown_keys = sorted(set(loaded[section]) - set(defaults))
        if unknown_keys:
            names = ", ".join(f"{section}.{key}" for key in unknown_keys)
            raise ValueError(f"invalid Code++ config: unknown option(s): {names}")
    config = _merge(DEFAULT_CONFIG, loaded)
    for key in ("max_file_bytes", "max_memory_bytes", "max_related_files", "max_related_bytes"):
        value = config["context"].get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"invalid Code++ config: context.{key} must be a positive integer")
    response_limit = config["protocol"].get("max_response_bytes")
    if not isinstance(response_limit, int) or isinstance(response_limit, bool) or response_limit <= 0:
        raise ValueError("invalid Code++ config: protocol.max_response_bytes must be a positive integer")
    boolean_options = {
        "context": ("include_git_diff", "include_staged_diff", "include_git_status", "include_project_metadata"),
        "security": ("redact_secrets", "respect_gitignore", "respect_codeppignore"),
        "patch": ("auto_validate", "auto_apply"),
    }
    for section, keys in boolean_options.items():
        for key in keys:
            if not isinstance(config[section].get(key), bool):
                raise ValueError(f"invalid Code++ config: {section}.{key} must be true or false")
    project_name = config["project"].get("name")
    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("invalid Code++ config: project.name must be a non-empty string")
    if config["patch"]["auto_apply"]:
        raise ValueError("invalid Code++ config: patch.auto_apply is not supported for safety")
    if config["relay"]["provider"] != "clipboard":
        raise ValueError("invalid Code++ config: only relay.provider = 'clipboard' is supported")
    return config


def initialize_config(root: Path) -> list[Path]:
    created: list[Path] = []
    base = safe_codepp_path(root)
    for name in ("inbox", "outbox", "tasks", "cache", "memory", "logs"):
        path = safe_codepp_path(root, name)
        if not path.exists():
            path.mkdir(parents=True)
            created.append(path)
    config_path = safe_codepp_path(root, "config.toml")
    if not config_path.exists():
        write_text(config_path, DEFAULT_CONFIG_TEXT)
        created.append(config_path)
    ignore_path = root / ".codeppignore"
    if not ignore_path.exists():
        write_text(ignore_path, DEFAULT_IGNORE_TEXT)
        created.append(ignore_path)
    return created
