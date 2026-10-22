"""
One-time interactive script to generate your GOOGLE_REFRESH_TOKEN for both:
- Google Drive API v3 (reading Queue folder & archiving Posted videos)
- YouTube Data API v3 (uploading Shorts to TheKyunProject)

Usage:
1. Download your OAuth 2.0 Desktop Client JSON from Google Cloud Console
   and save it as `client_secret.json` in `d:\\Automation\\` (or pass --client-secret).
2. Run:
   python scripts/setup_oauth.py
"""
import argparse
import json
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# Allow http://localhost redirect and relaxed scope matching on Google OAuth callback
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/youtube.upload",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Google OAuth2 Refresh Token")
    parser.add_argument(
        "--client-secret",
        default="client_secret.json",
        help="Path to downloaded OAuth2 Desktop client_secret.json (default: client_secret.json)",
    )
    parser.add_argument(
        "--youtube-only",
        action="store_true",
        help="Authorize only YouTube (use when your YouTube channel is on a different email than Google Drive)",
    )
    args = parser.parse_args()

    secret_path = Path(args.client_secret)
    if not secret_path.exists():
        print(f"[ERROR] File not found: {secret_path.resolve()}", flush=True)
        print(
            "Please download your OAuth 2.0 Desktop Client JSON from Google Cloud Console "
            "and save it as 'client_secret.json' in this folder.",
            flush=True,
        )
        return

    scopes = ["https://www.googleapis.com/auth/youtube.upload"] if args.youtube_only else SCOPES
    token_env_key = "YOUTUBE_REFRESH_TOKEN" if args.youtube_only else "GOOGLE_REFRESH_TOKEN"

    print("\nOpening browser for Google OAuth login...", flush=True)
    if args.youtube_only:
        print("IMPORTANT: Sign in with the Google account/email that owns 'TheKyunProject' YouTube channel!\n", flush=True)
    else:
        print("IMPORTANT: When prompted to choose an account/brand channel for YouTube,", flush=True)
        print("select 'TheKyunProject' so uploads go directly to that channel!\n", flush=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), scopes)
    creds = flow.run_local_server(
        host="localhost",
        port=0,
        prompt="select_account consent",
        access_type="offline",
        open_browser=True,
    )

    with open(secret_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
        client_info = raw.get("installed") or raw.get("web") or {}

    client_id = client_info.get("client_id", creds.client_id)
    client_secret = client_info.get("client_secret", creds.client_secret)

    print("\n" + "=" * 75, flush=True)
    print("SUCCESS! Copy these values into your .env file and GitHub Actions Secrets:", flush=True)
    print("=" * 75, flush=True)
    print(f"GOOGLE_CLIENT_ID={client_id}", flush=True)
    print(f"GOOGLE_CLIENT_SECRET={client_secret}", flush=True)
    print(f"{token_env_key}={creds.refresh_token}", flush=True)
    print("=" * 75 + "\n", flush=True)

    # Also auto-save/update .env locally
    env_path = Path(".env")
    if not env_path.exists() and Path(".env.example").exists():
        env_text = Path(".env.example").read_text(encoding="utf-8")
    elif env_path.exists():
        env_text = env_path.read_text(encoding="utf-8")
    else:
        env_text = ""

    replacements = {
        "GOOGLE_CLIENT_ID=": f"GOOGLE_CLIENT_ID={client_id}",
        "GOOGLE_CLIENT_SECRET=": f"GOOGLE_CLIENT_SECRET={client_secret}",
        f"{token_env_key}=": f"{token_env_key}={creds.refresh_token}",
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
    print(f"[INFO] Automatically saved Google OAuth credentials to {env_path.resolve()}!")


if __name__ == "__main__":
    main()
