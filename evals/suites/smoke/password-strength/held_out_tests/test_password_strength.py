"""Held-out acceptance tests for password-strength. The agent never sees these."""

import pytest


def test_all_rules_pass():
    from password_strength import assess

    result = assess("Tr0ub4dor&3")
    assert result["score"] == 4
    assert result["issues"] == []


def test_no_rules_pass():
    from password_strength import assess

    result = assess("abc")
    assert result["score"] == 0
    assert len(result["issues"]) == 4


def test_partial_scores():
    from password_strength import assess

    # long + lowercase only: satisfies rule 1 only
    assert assess("abcdefgh")["score"] == 1
    # long + digit: rules 1 and 2
    assert assess("abcdefg1")["score"] == 2
    # long + digit + upper: rules 1-3
    assert assess("Abcdefg1")["score"] == 3
    # short but digit + upper + symbol: rules 2-4
    assert assess("A1!")["score"] == 3


def test_issue_count_matches_failed_rules():
    from password_strength import assess

    result = assess("Abcdefg1")
    assert result["score"] + len(result["issues"]) == 4
    assert all(isinstance(issue, str) and issue for issue in result["issues"])


def test_non_string_raises_type_error():
    from password_strength import assess

    with pytest.raises(TypeError):
        assess(12345678)
