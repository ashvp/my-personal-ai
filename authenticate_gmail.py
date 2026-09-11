#!/usr/bin/env python3
"""WSL-Friendly Gmail OAuth2 Authentication.

Works 100% reliably in WSL/Linux environments without needing network port forwarding.
"""

import os
import sys

# Allow HTTP for localhost OAuth in local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("❌ Missing Google Auth libraries. Please run: pip install -r requirements.txt")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def authenticate():
    if not os.path.exists(CREDS_FILE):
        print(f"❌ '{CREDS_FILE}' not found! Please place credentials.json in the project root.")
        return False

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        print(f"✅ Already authenticated. Valid token found at: {TOKEN_FILE}")
        return True

    if creds and creds.expired and creds.refresh_token:
        print("🔄 Refreshing existing expired token...")
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as token_out:
                token_out.write(creds.to_json())
            print(f"✅ Token refreshed successfully! Saved to: {TOKEN_FILE}")
            return True
        except Exception as e:
            print(f"⚠️ Could not refresh token ({e}). Starting fresh authorization...")

    print("\n" + "=" * 65)
    print("           🔐 GMAIL ONE-TIME AUTHORIZATION (WSL)")
    print("=" * 65)

    # Use fixed redirect_uri compatible with credentials.json
    redirect_uri = "http://localhost:8080/"
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    auth_url, _ = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )

    print("\n👉 STEP 1: Copy and open this URL in your Windows browser:")
    print("-" * 65)
    print(auth_url)
    print("-" * 65)

    print("\n👉 STEP 2: Sign in with ashwin.vp.2005@gmail.com and click 'Allow'.")
    print("When redirected, your browser address bar will show a URL starting with:")
    print("http://localhost:8080/?state=...&code=...")

    print("\n👉 STEP 3: Copy that FULL URL from your browser address bar and paste it below:")
    try:
        redirect_response = input("\nPaste redirected URL here: ").strip()
        if not redirect_response:
            print("❌ No URL provided. Aborted.")
            return False

        # In case browser used http instead of https or vice versa
        if redirect_response.startswith("localhost:8080"):
            redirect_response = "http://" + redirect_response

        # Exchange authorization code for token
        flow.fetch_token(authorization_response=redirect_response)
        creds = flow.credentials

        with open(TOKEN_FILE, 'w') as token_out:
            token_out.write(creds.to_json())

        print("\n" + "=" * 65)
        print(f"🎉 SUCCESS! Gmail authorized! Token saved to: {TOKEN_FILE}")
        print("=" * 65 + "\n")
        return True

    except Exception as exc:
        print(f"\n❌ Error completing authorization: {exc}")
        return False


if __name__ == "__main__":
    authenticate()
