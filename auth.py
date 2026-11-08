"""FYERS v3 OAuth helper. Never print or commit access tokens."""
import argparse
import os
import re
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

load_dotenv()
CLIENT = os.environ.get("FYERS_CLIENT_ID", "").strip()
SECRET = os.environ.get("FYERS_SECRET_KEY", "").strip()
REDIRECT = os.environ.get("FYERS_REDIRECT_URI", "").strip()

def session():
    if not all((CLIENT, SECRET, REDIRECT)):
        raise SystemExit("Missing FYERS_CLIENT_ID, FYERS_SECRET_KEY or FYERS_REDIRECT_URI.")
    if not re.fullmatch(r"[A-Z0-9]{8,12}-\d{3}", CLIENT):
        raise SystemExit(
            f"FYERS_CLIENT_ID looks wrong (got {CLIENT[:2]}***{CLIENT[-4:]}, length {len(CLIENT)}). "
            "Use the APP ID from myapi.fyers.in (like ABCDE12345-100), not your FYERS login ID, "
            "and no quotes/spaces."
        )
    return fyersModel.SessionModel(
        client_id=CLIENT,
        secret_key=SECRET,
        redirect_uri=REDIRECT,
        response_type="code",
        grant_type="authorization_code",
    )

def exchange(code):
    s = session()
    s.set_token(code)
    result = s.generate_token()
    token = result.get("access_token") if isinstance(result, dict) else None
    if not token:
        raise SystemExit("Token exchange failed. Check auth code, redirect URI and app credentials.")
    return token

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["login", "exchange"])
    args = parser.parse_args()

    if args.action == "login":
        print(f"Credential check: App ID length={len(CLIENT)}, has_-100_suffix={CLIENT.endswith('-100')}, redirect_matches_expected={REDIRECT == 'https://trade.fyers.in/api-login/redirect-uri/index.html'}")
        url = session().generate_authcode()
        with open("fyers_login_url.txt", "w", encoding="utf-8") as f:
            f.write(url + "\n")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("## FYERS authorisation\n\n")
                f.write("[Open FYERS login page](" + url + ")\n\n")
                f.write("If the button does not open, copy this URL:\n\n" + url + "\n")
        print("FYERS login link added to the workflow summary.")
        return

    value = os.environ.get("FYERS_AUTH_CODE", "").strip()
    if not value:
        value = input("Paste redirect URL or auth_code: ").strip()
    code = parse_qs(urlparse(value).query).get("auth_code", [value])[0]
    if not code:
        raise SystemExit("No auth_code found.")
    token = exchange(code)
    with open(".fyers_access_token", "w", encoding="utf-8") as f:
        f.write(token)
    print("FYERS access token generated. Token value intentionally hidden.")

if __name__ == "__main__":
    main()
