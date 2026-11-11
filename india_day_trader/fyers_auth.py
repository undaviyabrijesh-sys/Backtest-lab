"""Refresh a daily FYERS v3 access token without exposing credentials in logs."""
import hashlib
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

REFRESH_URL = "https://api-t1.fyers.in/api/v3/validate-refresh-token"


def app_id_hash(client_id, app_secret):
    """Return SHA-256(app_id:app_secret), as required by FYERS."""
    value = f"{client_id}:{app_secret}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def request_access_token(client_id, app_secret, refresh_token, pin, http_open=None):
    """Exchange the refresh token for today's access token."""
    if not all((client_id, app_secret, refresh_token, pin)):
        raise ValueError("FYERS client ID, app secret, refresh token and PIN are required")
    opener = http_open or urlopen
    payload = {
        "grant_type": "refresh_token",
        "appIdHash": app_id_hash(client_id, app_secret),
        "refresh_token": refresh_token,
        "pin": pin,
    }
    request = Request(
        REFRESH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Never echo request payloads or credential values.
        raise RuntimeError(f"FYERS token refresh HTTP error ({exc.code})") from exc
    except URLError as exc:
        raise RuntimeError("Unable to reach FYERS token refresh endpoint") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("FYERS returned an invalid token-refresh response") from exc

    token = result.get("access_token") if isinstance(result, dict) else None
    if not token or result.get("s") != "ok":
        code = result.get("code", "unknown") if isinstance(result, dict) else "unknown"
        message = result.get("message", "no access token returned") if isinstance(result, dict) else "invalid response"
        raise RuntimeError(f"FYERS token refresh failed (code {code}): {message}")
    return token


def main():
    load_dotenv()
    client_id = os.getenv("FYERS_CLIENT_ID", "").strip()
    app_secret = os.getenv("FYERS_SECRET_KEY", "").strip()
    refresh_token = os.getenv("FYERS_REFRESH_TOKEN", "").strip()
    pin = os.getenv("FYERS_PIN", "").strip()
    github_env = os.getenv("GITHUB_ENV", "").strip()
    if not github_env:
        raise SystemExit("GITHUB_ENV is required; run this module inside the GitHub Actions workflow.")
    try:
        token = request_access_token(client_id, app_secret, refresh_token, pin)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    with open(github_env, "a", encoding="utf-8") as handle:
        handle.write(f"FYERS_ACCESS_TOKEN={token}\n")
    print("FYERS daily access token refreshed successfully; token value hidden.")


if __name__ == "__main__":
    main()
