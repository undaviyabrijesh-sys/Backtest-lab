import hashlib
import json
from unittest.mock import patch

import pytest

from india_day_trader import fyers_auth


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_app_id_hash_uses_colon_separated_credentials():
    expected = hashlib.sha256(b"APP-100:secret").hexdigest()
    assert fyers_auth.app_id_hash("APP-100", "secret") == expected


def test_refresh_success_returns_access_token_without_logging_it():
    response = FakeResponse({"s": "ok", "code": 200, "access_token": "secret-token-value"})
    with patch("india_day_trader.fyers_auth.urlopen", return_value=response) as mocked:
        token = fyers_auth.request_access_token("APP-100", "app-secret", "refresh-secret", "1234")
    assert token == "secret-token-value"
    request = mocked.call_args.args[0]
    body = json.loads(request.data.decode("utf-8"))
    assert body["grant_type"] == "refresh_token"
    assert body["pin"] == "1234"
    assert body["refresh_token"] == "refresh-secret"


def test_refresh_rejects_incomplete_credentials():
    with pytest.raises(ValueError):
        fyers_auth.request_access_token("APP-100", "", "refresh-secret", "1234")


def test_refresh_fails_closed_on_api_error_without_access_token():
    response = FakeResponse({"s": "error", "code": -501, "message": "invalid refresh token"})
    with patch("india_day_trader.fyers_auth.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="code -501"):
            fyers_auth.request_access_token("APP-100", "app-secret", "refresh-secret", "1234")
