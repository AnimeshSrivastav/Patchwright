import pytest
from autofix.monitor.redactor import redact, redact_dict


def test_redact_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"
    result = redact(text)
    assert "eyJ" not in result
    assert "[REDACTED]" in result or "[JWT]" in result


def test_redact_api_key():
    text = "api_key=super_secret_value_12345"
    result = redact(text)
    assert "super_secret_value_12345" not in result
    assert "[REDACTED]" in result


def test_redact_email():
    text = "User alice@example.com sent a request"
    result = redact(text)
    assert "alice@example.com" not in result
    assert "[EMAIL]" in result


def test_redact_ip():
    text = "Request from 192.168.1.100 failed"
    result = redact(text)
    assert "192.168.1.100" not in result
    assert "[IP]" in result


def test_redact_uuid():
    text = "incident id: 550e8400-e29b-41d4-a716-446655440000"
    result = redact(text)
    assert "550e8400-e29b-41d4-a716-446655440000" not in result
    assert "[UUID]" in result


def test_redact_google_api_key():
    text = "key=AIzaSyDk7fSZHb38KAaLFJiHuRrkGPz9kZhvlUw"
    result = redact(text)
    assert "AIzaSy" not in result


def test_redact_preserves_non_sensitive():
    text = "KeyError: 'price' in get_item at line 24"
    result = redact(text)
    assert "KeyError" in result
    assert "price" in result
    assert "get_item" in result


def test_redact_dict_recursive():
    data = {
        "message": "token=abc123secret",
        "nested": {"email": "user@test.com"},
        "number": 42,
    }
    result = redact_dict(data)
    assert "abc123secret" not in result["message"]
    assert "user@test.com" not in result["nested"]["email"]
    assert result["number"] == 42
