"""
One-time interactive script to generate your LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN
for automated video posting to your personal LinkedIn profile.
"""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import urllib.parse
import webbrowser
from dotenv import load_dotenv
import requests

load_dotenv()

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
REDIRECT_URI = "http://localhost:8085/"
SCOPES = "openid profile email w_member_social"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    error = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>LinkedIn Authorization Successful!</h2><p>You can close this tab and return to the chat.</p>"
            )
        else:
            err = params.get("error_description", ["Unknown error"])[0]
            OAuthCallbackHandler.error = err
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>Authorization Failed:</h2><p>{err}</p>".encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Quiet logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LinkedIn OAuth2 Access Token")
    parser.add_argument(
        "--client-id",
        default=os.getenv("LINKEDIN_CLIENT_ID", ""),
        help="LinkedIn App Client ID",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("LINKEDIN_CLIENT_SECRET", ""),
        help="LinkedIn App Client Secret",
    )
    args = parser.parse_args()

    client_id = args.client_id.strip()
    client_secret = args.client_secret.strip()

    if not client_id or not client_secret:
        print("[ERROR] Please provide --client-id and --client-secret (or set them in .env).", flush=True)
        return

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "state": "linkedin_oauth_state",
        "scope": SCOPES,
    }
    auth_url = f"{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("\nOpening browser for LinkedIn OAuth login...", flush=True)
    print("Please visit this URL to authorize your LinkedIn account:\n", flush=True)
    print(auth_url, flush=True)
    print("\nWaiting for authorization callback on http://localhost:8085/ ...", flush=True)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    server = HTTPServer(("localhost", 8085), OAuthCallbackHandler)
    while OAuthCallbackHandler.auth_code is None and OAuthCallbackHandler.error is None:
        server.handle_request()
    server.server_close()

    if OAuthCallbackHandler.error:
        print(f"\n[ERROR] LinkedIn OAuth Error: {OAuthCallbackHandler.error}", flush=True)
        return

    code = OAuthCallbackHandler.auth_code
    print("\nReceived authorization code! Exchanging for Access Token...", flush=True)

    token_resp = requests.post(
        LINKEDIN_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if not token_resp.ok:
        print(f"\n[ERROR] Token exchange failed ({token_resp.status_code}): {token_resp.text}", flush=True)
        return

    token_data = token_resp.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", "unknown")

    # Get User Person URN
    userinfo_resp = requests.get(
        LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if not userinfo_resp.ok:
        print(f"\n[ERROR] Could not fetch user profile info: {userinfo_resp.text}", flush=True)
        return

    userinfo = userinfo_resp.json()
    person_urn = f"urn:li:person:{userinfo['sub']}"
    user_name = userinfo.get("name", "LinkedIn User")

    print("\n" + "=" * 75, flush=True)
    print(f"SUCCESS! Authorized as: {user_name} ({person_urn})", flush=True)
    print(f"Token valid for: {expires_in} seconds (~60 days)", flush=True)
    print("=" * 75, flush=True)
    print(f"LINKEDIN_CLIENT_ID={client_id}", flush=True)
    print(f"LINKEDIN_CLIENT_SECRET={client_secret}", flush=True)
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}", flush=True)
    print(f"LINKEDIN_PERSON_URN={person_urn}", flush=True)
    print("=" * 75 + "\n", flush=True)

    # Save to local .env
    env_path = Path(".env")
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    replacements = {
        "LINKEDIN_CLIENT_ID=": f"LINKEDIN_CLIENT_ID={client_id}",
        "LINKEDIN_CLIENT_SECRET=": f"LINKEDIN_CLIENT_SECRET={client_secret}",
        "LINKEDIN_ACCESS_TOKEN=": f"LINKEDIN_ACCESS_TOKEN={access_token}",
        "LINKEDIN_PERSON_URN=": f"LINKEDIN_PERSON_URN={person_urn}",
    }

    lines = env_text.splitlines()
    new_lines = []
    seen = set()
    for line in lines:
        replaced = False
        for prefix, full_val in replacements.items():
            if line.startswith(prefix):
                new_lines.append(full_val)
                seen.add(prefix)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)
    for prefix, full_val in replacements.items():
        if prefix not in seen:
            new_lines.append(full_val)

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[INFO] Automatically saved LinkedIn credentials to {env_path.resolve()}!", flush=True)


if __name__ == "__main__":
    main()
