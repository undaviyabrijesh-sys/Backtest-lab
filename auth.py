"""Interactive FYERS v3 OAuth; run locally, never in GitHub Actions."""
import argparse
import os
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

load_dotenv()
CLIENT = os.environ.get("FYERS_CLIENT_ID", "")
SECRET = os.environ.get("FYERS_SECRET_KEY", "")
REDIRECT = os.environ.get("FYERS_REDIRECT_URI", "")

def session():
    if not all((CLIENT, SECRET, REDIRECT)):
        raise SystemExit("Set FYERS_CLIENT_ID, FYERS_SECRET_KEY and FYERS_REDIRECT_URI in local .env")
    return fyersModel.SessionModel(client_id=CLIENT, secret_key=SECRET, redirect_uri=REDIRECT,
                                   response_type="code", grant_type="authorization_code")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["login", "exchange"])
    args = parser.parse_args()
    s = session()
    if args.action == "login":
        print("Open this URL in your browser:\n", s.generate_authcode())
        return
    value = input("Paste redirect URL or auth_code: ").strip()
    code = parse_qs(urlparse(value).query).get("auth_code", [value])[0]
    if not code:
        raise SystemExit("No auth_code found")
    s.set_token(code)
    result = s.generate_token()
    token = result.get("access_token") if isinstance(result, dict) else None
    if not token:
        raise SystemExit("Token exchange failed; check your redirect URL, app settings and auth code")
    with open(".env", "a", encoding="utf-8") as f:
        f.write("\nFYERS_ACCESS_TOKEN=" + token + "\n")
    print("Access token saved locally in .env (never commit).")

if __name__ == "__main__":
    main()
