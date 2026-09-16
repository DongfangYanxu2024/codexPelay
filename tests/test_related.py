from copy import deepcopy
from pathlib import Path

from codepp.config import DEFAULT_CONFIG
from codepp.core.related import discover_related_files


def related_config(limit: int = 200000) -> dict:
    config = deepcopy(DEFAULT_CONFIG)
    config["context"]["max_file_bytes"] = limit
    return config


def write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discovers_python_imports_without_recursing(tmp_path: Path):
    write(tmp_path / "pkg" / "__init__.py")
    write(
        tmp_path / "pkg" / "main.py",
        "from . import helper\nfrom .nested import VALUE\nimport root_module\n",
    )
    write(tmp_path / "pkg" / "helper.py", "import second_hop\n")
    write(tmp_path / "pkg" / "nested.py")
    write(tmp_path / "root_module.py")
    write(tmp_path / "second_hop.py")

    assert discover_related_files(tmp_path, ["pkg/main.py"], related_config()) == [
        "pkg/helper.py",
        "pkg/nested.py",
        "root_module.py",
    ]


def test_discovers_javascript_relative_modules_and_directory_index(tmp_path: Path):
    write(
        tmp_path / "src" / "main.ts",
        """import { value } from "./utils";
const legacy = require('./legacy');
const lazy = import("./lazy");
// require("./commented")
const example = "import ignored from './inside-string'";
""",
    )
    write(tmp_path / "src" / "utils" / "index.ts")
    write(tmp_path / "src" / "legacy.js")
    write(tmp_path / "src" / "lazy.tsx")
    write(tmp_path / "src" / "commented.ts")
    write(tmp_path / "src" / "inside-string.ts")

    assert discover_related_files(tmp_path, ["src/main.ts"], related_config()) == [
        "src/utils/index.ts",
        "src/legacy.js",
        "src/lazy.tsx",
    ]


def test_discovers_adjacent_and_mirrored_test_source_counterparts(tmp_path: Path):
    write(tmp_path / "src" / "service.py")
    write(tmp_path / "src" / "test_service.py")
    write(tmp_path / "tests" / "api" / "test_client.py")
    write(tmp_path / "src" / "api" / "client.py")

    assert discover_related_files(tmp_path, ["src/service.py"], related_config()) == [
        "src/test_service.py"
    ]
    assert discover_related_files(tmp_path, ["tests/api/test_client.py"], related_config()) == [
        "src/api/client.py"
    ]


def test_honors_both_ignore_files(tmp_path: Path):
    write(tmp_path / ".gitignore", "ignored.py\n")
    write(tmp_path / ".codeppignore", "private/\n")
    write(
        tmp_path / "main.py",
        "import ignored\nfrom private import hidden\nimport visible\n",
    )
    write(tmp_path / "ignored.py")
    write(tmp_path / "private" / "__init__.py")
    write(tmp_path / "private" / "hidden.py")
    write(tmp_path / "visible.py")

    assert discover_related_files(tmp_path, ["main.py"], related_config()) == ["visible.py"]


def test_rejects_traversal_and_external_symlink(tmp_path: Path):
    project = tmp_path / "project"
    outside = tmp_path / "outside.ts"
    write(outside)
    write(project / "src" / "main.ts", "import '../../outside';\nimport './external';\n")
    external_link = project / "src" / "external.ts"
    try:
        external_link.symlink_to(outside)
    except OSError:
        pass

    assert discover_related_files(project, ["src/main.ts", "../outside.ts"], related_config()) == []


def test_excludes_seeds_duplicates_and_caps_in_source_order(tmp_path: Path):
    write(tmp_path / "main.py", "import beta\nimport alpha\nimport beta\nimport gamma\n")
    for name in ("alpha.py", "beta.py", "gamma.py"):
        write(tmp_path / name)

    assert discover_related_files(tmp_path, ["main.py", "./main.py"], related_config(), max_files=2) == [
        "beta.py",
        "alpha.py",
    ]
    assert discover_related_files(tmp_path, ["main.py", "beta.py"], related_config()) == [
        "alpha.py",
        "gamma.py",
    ]
    assert discover_related_files(tmp_path, ["main.py"], related_config(), max_files=0) == []


def test_does_not_parse_or_return_files_over_the_configured_limit(tmp_path: Path):
    write(tmp_path / "large_seed.py", "import target\n" + "x" * 50)
    write(tmp_path / "small_seed.py", "import large_target\n")
    write(tmp_path / "target.py")
    write(tmp_path / "large_target.py", "x" * 100)

    config = related_config(30)
    assert discover_related_files(tmp_path, ["large_seed.py"], config) == []
    assert discover_related_files(tmp_path, ["small_seed.py"], config) == []
