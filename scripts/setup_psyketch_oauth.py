"""
One-time interactive script to generate OAuth2 Refresh Tokens for the @psyketch.studio profile:
- Google Drive API v3 (reading English Queue folder & archiving Posted videos)
- YouTube Data API v3 (uploading Shorts to @psyketch.studio)

Usage:
1. Save your OAuth 2.0 Desktop Client JSON for the psyketch Google account as `psyketch_client_secret.json`
   (or pass --client-secret).
2. Run:
   python scripts/setup_psyketch_oauth.py
"""
import argparse
import json
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/youtube.upload",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Google OAuth2 Refresh Token for @psyketch.studio")
    parser.add_argument(
        "--client-secret",
        default="psyketch_client_secret.json",
        help="Path to downloaded OAuth2 Desktop client_secret.json for psyketch (default: psyketch_client_secret.json)",
    )
    args = parser.parse_args()

    secret_path = Path(args.client_secret)
    if not secret_path.exists():
        # Fallback check for client_secret.json if user used standard name
        if Path("client_secret.json").exists():
            print("[INFO] Using 'client_secret.json' found in workspace.", flush=True)
            secret_path = Path("client_secret.json")
        else:
            print(f"[ERROR] File not found: {secret_path.resolve()}", flush=True)
            print(
                "Please download your OAuth 2.0 Desktop Client JSON from Google Cloud Console (for @psyketch.studio) "
                "and save it as 'psyketch_client_secret.json' in this folder.",
                flush=True,
            )
            return

    print("\nOpening browser for Google OAuth login...", flush=True)
    print("IMPORTANT: Sign in with the Google account that owns the '@psyketch.studio' YouTube channel and Google Drive!\n", flush=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
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
    print(f"PSYKETCH_GOOGLE_CLIENT_ID={client_id}", flush=True)
    print(f"PSYKETCH_GOOGLE_CLIENT_SECRET={client_secret}", flush=True)
    print(f"PSYKETCH_GOOGLE_REFRESH_TOKEN={creds.refresh_token}", flush=True)
    print(f"PSYKETCH_YOUTUBE_REFRESH_TOKEN={creds.refresh_token}", flush=True)
    print("=" * 75 + "\n", flush=True)

    # Save to local .env under PSYKETCH_ variables (does NOT overwrite existing uday variables)
    env_path = Path(".env")
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    replacements = {
        "PSYKETCH_GOOGLE_CLIENT_ID=": f"PSYKETCH_GOOGLE_CLIENT_ID={client_id}",
        "PSYKETCH_GOOGLE_CLIENT_SECRET=": f"PSYKETCH_GOOGLE_CLIENT_SECRET={client_secret}",
        "PSYKETCH_GOOGLE_REFRESH_TOKEN=": f"PSYKETCH_GOOGLE_REFRESH_TOKEN={creds.refresh_token}",
        "PSYKETCH_YOUTUBE_REFRESH_TOKEN=": f"PSYKETCH_YOUTUBE_REFRESH_TOKEN={creds.refresh_token}",
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
    print(f"[INFO] Automatically saved @psyketch.studio credentials to {env_path.resolve()}!")


if __name__ == "__main__":
    main()
