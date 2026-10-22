"""
Helper script to automatically:
1. Exchange a short-lived Meta Graph API Explorer token for a 60-day Long-Lived Token (if App ID & Secret are provided).
2. Auto-discover your Instagram Business/Creator Account ID (IG_USER_ID) for @psychologist.uday.
3. Save IG_USER_ID and IG_ACCESS_TOKEN directly into .env.
"""
import argparse
from pathlib import Path
import requests

GRAPH_BASE = "https://graph.facebook.com/v21.0"


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-configure Instagram Graph API credentials")
    parser.add_argument("--token", required=True, help="Access token from Meta Graph API Explorer")
    parser.add_argument("--app-id", default="", help="Meta App ID (optional, to exchange for 60-day long-lived token)")
    parser.add_argument("--app-secret", default="", help="Meta App Secret (optional, to exchange for 60-day long-lived token)")
    args = parser.parse_args()

    access_token = args.token.strip()

    # 1. Exchange for 60-day long-lived token if App ID & App Secret are given
    if args.app_id and args.app_secret:
        print("[INFO] Exchanging token for a 60-day Long-Lived Access Token...", flush=True)
        resp = requests.get(
            f"{GRAPH_BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": args.app_id.strip(),
                "client_secret": args.app_secret.strip(),
                "fb_exchange_token": access_token,
            },
            timeout=30,
        )
        data = resp.json()
        if resp.ok and "access_token" in data:
            access_token = data["access_token"]
            print("[SUCCESS] Obtained 60-day Long-Lived Access Token!", flush=True)
        else:
            print(f"[WARN] Could not exchange token ({data}); proceeding with provided token...", flush=True)

    # 2. Discover linked Instagram Business/Creator Account ID
    print("[INFO] Looking up linked Facebook Pages and Instagram Creator/Business accounts...", flush=True)
    resp = requests.get(
        f"{GRAPH_BASE}/me/accounts",
        params={
            "fields": "id,name,instagram_business_account{id,username,name}",
            "access_token": access_token,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok:
        print(f"[ERROR] Graph API error: {data}", flush=True)
        return

    pages = data.get("data", [])
    ig_user_id = None
    ig_username = None

    for page in pages:
        ig_acct = page.get("instagram_business_account")
        if ig_acct and ig_acct.get("id"):
            ig_user_id = ig_acct["id"]
            ig_username = ig_acct.get("username", "unknown")
            print(
                f"[FOUND] Facebook Page '{page.get('name')}' -> Instagram @{ig_username} (IG_USER_ID: {ig_user_id})",
                flush=True,
            )
            break

    if not ig_user_id:
        print("\n[ERROR] No linked Instagram Professional/Creator account was found on your Facebook Pages.", flush=True)
        print("Make sure:", flush=True)
        print("  1. @psychologist.uday is a Creator or Business account (not Personal).", flush=True)
        print("  2. It is linked to a Facebook Page (Instagram Settings -> Account Type and Tools / Linked Accounts).", flush=True)
        print("  3. When clicking 'Generate Access Token' in Graph API Explorer, you selected that Facebook Page & Instagram account.", flush=True)
        return

    # 3. Save to .env
    env_path = Path(".env")
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    replacements = {
        "IG_USER_ID=": f"IG_USER_ID={ig_user_id}",
        "IG_ACCESS_TOKEN=": f"IG_ACCESS_TOKEN={access_token}",
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
    print(f"\n[SUCCESS] Saved IG_USER_ID ({ig_user_id} for @{ig_username}) and IG_ACCESS_TOKEN to {env_path.resolve()}!", flush=True)


if __name__ == "__main__":
    main()
