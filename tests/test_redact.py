import pytest

from codepp.security.redact import redact_secrets


def test_redacts_common_assignments():
    text = 'OPENAI_API_KEY=sk-abc\npassword = "hunter2"\naws_secret_access_key: xyz'
    result, count = redact_secrets(text)
    assert "sk-abc" not in result
    assert "hunter2" not in result
    assert "xyz" not in result
    assert result.count("[REDACTED]") == 3
    assert count == 3


def test_redacts_authorization_and_bearer():
    result, count = redact_secrets("Authorization: Bearer abcdef123\nuse bearer qwerty987")
    assert "abcdef123" not in result
    assert "qwerty987" not in result
    assert count == 2


def test_does_not_redact_token_count():
    result, count = redact_secrets("token_count = 200\nsecretary = 'Ada'")
    assert result == "token_count = 200\nsecretary = 'Ada'"
    assert count == 0


def test_redacts_json_key():
    result, _ = redact_secrets('{"password": "hidden"}')
    assert "hidden" not in result


def test_redacts_spaced_quoted_assignments_and_preserves_quote_style():
    text = '\"api-key\"   :   \"first secret\"\n\'PASSWORD\' = \'second secret\''
    result, count = redact_secrets(text)
    assert "first secret" not in result
    assert "second secret" not in result
    assert '\"api-key\"   :   \"[REDACTED]\"' in result
    assert "'PASSWORD' = '[REDACTED]'" in result
    assert count == 2


def test_redacts_complete_authorization_value_once():
    result, count = redact_secrets("AUTHORIZATION : Basic dXNlcjpwYXNzd29yZA==\nnext: safe")
    assert "dXNlcjpwYXNzd29yZA==" not in result
    assert "AUTHORIZATION : [REDACTED]" in result
    assert "next: safe" in result
    assert count == 1


def test_redacts_multiline_private_key_block():
    text = "before\n-----BEGIN PRIVATE KEY-----\nvery-secret-material\n-----END PRIVATE KEY-----\nafter"
    result, count = redact_secrets(text)
    assert "very-secret-material" not in result
    assert "BEGIN PRIVATE KEY" not in result
    assert result == "before\n[REDACTED PRIVATE KEY]\nafter"
    assert count == 1


@pytest.mark.parametrize(
    "token",
    [
        "sk-proj-" + "abcdefghijklmnop",
        "github_pat_" + "abcdefghijklmnopqrst",
        "ghp_" + "abcdefghijklmnopqrst",
        "xoxb-" + "abcdefghijklmnop",
        "AKIA" + "ABCDEFGHIJKLMNOP",
    ],
)
def test_redacts_standalone_high_confidence_tokens(token: str):
    result, count = redact_secrets(f"prefix ({token}) suffix")
    assert token not in result
    assert result == "prefix ([REDACTED]) suffix"
    assert count == 1


def test_does_not_redact_short_token_like_text():
    text = "Use sk-short or ghp_example as documentation placeholders."
    assert redact_secrets(text) == (text, 0)
