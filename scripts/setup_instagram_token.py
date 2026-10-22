"""
Helper script to:
1. Exchange a short-lived Meta Graph API User Token for a 60-day Long-Lived Token.
2. Automatically discover your Instagram Business/Creator Account ID (IG_USER_ID)
   for @psychologist.uday from your linked Facebook Page.

Usage:
  python scripts/setup_instagram_token.py --app-id YOUR_APP_ID --app-secret YOUR_APP_SECRET --token SHORT_LIVED_TOKEN
"""
import argparse
import requests

GRAPH_URL = "https://graph.facebook.com/v21.0"


def main() -> None:
    parser = argparse.ArgumentParser(description="Exchange Meta token & find IG_USER_ID for @psychologist.uday")
    parser.add_argument("--app-id", required=True, help="Meta App ID")
    parser.add_argument("--app-secret", required=True, help="Meta App Secret")
    parser.add_argument("--token", required=True, help="Short-lived User Access Token from Graph API Explorer")
    args = parser.parse_args()

    # 1. Exchange for a 60-day Long-Lived User Token
    print("Exchanging token for a 60-day long-lived access token...")
    exchange_resp = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": args.app_id,
            "client_secret": args.app_secret,
            "fb_exchange_token": args.token,
        },
        timeout=30,
    )
    if not exchange_resp.ok:
        raise SystemExit(f"[ERROR] Token exchange failed: {exchange_resp.text}")

    long_lived_token = exchange_resp.json()["access_token"]

    # 2. Discover connected Facebook Pages & linked Instagram Professional Accounts
    print("Fetching linked Instagram Professional/Creator accounts...")
    accounts_resp = requests.get(
        f"{GRAPH_URL}/me/accounts",
        params={
            "fields": "name,instagram_business_account{id,username,name}",
            "access_token": long_lived_token,
        },
        timeout=30,
    )
    if not accounts_resp.ok:
        raise SystemExit(f"[ERROR] Could not list accounts: {accounts_resp.text}")

    pages = accounts_resp.json().get("data", [])
    found_ig = None
    for page in pages:
        ig_acct = page.get("instagram_business_account")
        if ig_acct:
            print(f"Found Instagram account @{ig_acct.get('username')} (ID: {ig_acct['id']}) via Page '{page.get('name')}'")
            found_ig = ig_acct

    print("\n" + "=" * 75)
    print("SUCCESS! Copy these values into your .env and GitHub Actions Secrets:")
    print("=" * 75)
    if found_ig:
        print(f"IG_USER_ID={found_ig['id']}  # @{found_ig.get('username')}")
    else:
        print("IG_USER_ID=<Could not auto-detect: ensure @psychologist.uday is linked to a FB Page>")
    print(f"IG_ACCESS_TOKEN={long_lived_token}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
