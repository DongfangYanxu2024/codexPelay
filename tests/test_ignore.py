from pathlib import Path

from codepp.security.ignore import IgnoreMatcher, parse_rules


def test_ignore_patterns_and_negation():
    matcher = IgnoreMatcher(parse_rules("*.pem\nbuild/\n!important.pem\n"))
    assert matcher.ignored("keys/server.pem")
    assert matcher.ignored("build/app.js")
    assert not matcher.ignored("important.pem")
    assert not matcher.ignored("src/app.py")


def test_comments_and_blanks_are_ignored():
    assert parse_rules("# comment\n\n*.db\n") == parse_rules("*.db")


def test_git_matcher_honors_nested_gitignore_and_info_exclude(git_repo: Path):
    nested = git_repo / "src" / "generated"
    nested.mkdir(parents=True)
    (git_repo / "src" / ".gitignore").write_text(
        "*.trace\n!important.trace\n",
        encoding="utf-8",
    )
    (nested / "debug.trace").write_text("ignored", encoding="utf-8")
    (nested / "important.trace").write_text("kept", encoding="utf-8")
    (git_repo / ".git" / "info" / "exclude").write_text(
        "local-cache/\n",
        encoding="utf-8",
    )
    (git_repo / "local-cache").mkdir()
    (git_repo / "local-cache" / "state.txt").write_text("ignored", encoding="utf-8")

    matcher = IgnoreMatcher.from_project(git_repo)
    assert matcher.ignored("src/generated/debug.trace")
    assert not matcher.ignored("src/generated/important.trace")
    assert not matcher.ignored("debug.trace")
    assert matcher.ignored("local-cache/state.txt")


def test_can_disable_all_git_ignore_sources(git_repo: Path):
    (git_repo / ".gitignore").write_text("root.log\n", encoding="utf-8")
    (git_repo / ".git" / "info" / "exclude").write_text("private.log\n", encoding="utf-8")
    matcher = IgnoreMatcher.from_project(git_repo, gitignore=False, codeppignore=False)
    assert not matcher.ignored("root.log")
    assert not matcher.ignored("private.log")


def test_codepp_negation_cannot_override_git_ignore(git_repo: Path):
    (git_repo / ".gitignore").write_text("private.txt\n", encoding="utf-8")
    (git_repo / ".codeppignore").write_text("!private.txt\n", encoding="utf-8")
    matcher = IgnoreMatcher.from_project(git_repo)
    assert matcher.ignored("private.txt")


def test_codepp_negation_cannot_override_non_git_gitignore(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("private.txt\n", encoding="utf-8")
    (tmp_path / ".codeppignore").write_text("!private.txt\n", encoding="utf-8")
    matcher = IgnoreMatcher.from_project(tmp_path)
    assert matcher.ignored("private.txt")
