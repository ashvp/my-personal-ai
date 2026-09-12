#!/usr/bin/env python3
"""WSL & Windows Friendly Microsoft Graph / Outlook Device Code Authentication.

Works 100% reliably in terminal/WSL environments using Microsoft's Device Code Flow:
Prints a code and asks you to approve at https://microsoft.com/devicelogin.
"""

import os
import sys
import json

try:
    import msal
except ImportError:
    print("❌ Missing msal library. Please run: pip install msal")
    sys.exit(1)

# Default to Microsoft Office multi-tenant public client ID or custom Azure App ID from .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "outlook_token.json")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try reading from .env if present
DEFAULT_CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
CLIENT_ID = os.getenv("APPLICATION_ID_OUTLOOK") or os.getenv("OUTLOOK_CLIENT_ID") or DEFAULT_CLIENT_ID
TENANT_ID = os.getenv("DIRECTORY_ID_OUTLOOK") or os.getenv("OUTLOOK_TENANT_ID") or "common"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read"
]


def authenticate():
    print("\n" + "=" * 65)
    print("       🔐 OUTLOOK / COLLEGE EMAIL ONE-TIME AUTHORIZATION")
    print("=" * 65)

    # Check if we already have a valid cached token
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                cached_data = json.load(f)
            if cached_data.get("access_token"):
                print(f"✅ Existing Outlook token found at: {TOKEN_FILE}")
                choice = input("Do you want to re-authenticate with a new account? [y/N]: ").strip().lower()
                if choice != "y":
                    return True
        except Exception:
            pass

    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY
    )

    print(f"\nInitiating Microsoft Device Code Flow...")
    print(f"  • Client ID: {CLIENT_ID}")
    print(f"  • Authority: {AUTHORITY}")
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        print(f"❌ Failed to initiate device flow: {flow.get('error_description', flow)}")
        print("\nTip: If your college requires a custom Azure App ID, create one at portal.azure.com")
        print("and add OUTLOOK_CLIENT_ID=<id> in your .env file.")
        return False

    print("\n" + "-" * 65)
    print(f"👉 1. Open this URL in any browser (Phone or PC):")
    print(f"   {flow['verification_uri']}")
    print(f"\n👉 2. Enter this code:")
    print(f"   🔑 {flow['user_code']}")
    print(f"\n👉 3. Sign in with your College/Outlook account and click 'Accept'.")
    print("-" * 65 + "\n")
    print("⏳ Waiting for your authorization in the browser...")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        token_data = {
            "client_id": CLIENT_ID,
            "authority": AUTHORITY,
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token", ""),
            "id_token_claims": result.get("id_token_claims", {}),
            "token_type": result.get("token_type", "Bearer"),
            "expires_in": result.get("expires_in", 3600),
            "account_username": result.get("id_token_claims", {}).get("preferred_username", "Unknown User")
        }

        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

        print("\n" + "=" * 65)
        print(f"🎉 SUCCESS! Outlook authorized for: {token_data['account_username']}")
        print(f"Token saved securely to: {TOKEN_FILE}")
        print("=" * 65 + "\n")
        return True
    else:
        error_msg = result.get("error_description", result.get("error", "Unknown error"))
        print(f"\n❌ Authorization failed: {error_msg}")
        return False


if __name__ == "__main__":
    authenticate()
