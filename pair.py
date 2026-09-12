#!/usr/bin/env python3
"""Device Pairing Utility.

Generates pairing credentials, displays terminal ASCII QR codes for phones,
and provides copy-paste curl commands for secondary laptops.
"""

import os
import sys
import json
import secrets
import argparse
from typing import Optional

# Try loading existing .env
try:
    from dotenv import load_dotenv, set_key
    load_dotenv()
except ImportError:
    pass

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def get_existing_tokens():
    tokens_str = os.getenv("AUTHORIZED_DEVICE_TOKENS", "")
    return [t.strip() for t in tokens_str.split(",") if t.strip()]


def add_token_to_env(token: str):
    existing = get_existing_tokens()
    if token not in existing:
        existing.append(token)
        new_val = ",".join(existing)
        # Update .env file
        if os.path.exists(ENV_FILE):
            try:
                set_key(ENV_FILE, "AUTHORIZED_DEVICE_TOKENS", new_val)
            except Exception:
                pass


def display_qr(text: str):
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(text)
        qr.make(fit=True)
        print("\n" + "=" * 55)
        print("  📱 SCAN WITH YOUR PHONE CAMERA TO AUTO-OPEN & PAIR")
        print("=" * 55)
        qr.print_ascii(invert=True)
    except ImportError:
        print("\n[Tip] Install 'qrcode' to render ASCII QR codes in terminal: pip install qrcode")


def main():
    parser = argparse.ArgumentParser(description="Pair a new device to your Personal AI Assistant")
    parser.add_argument("--url", default=None, help="Public server URL (e.g. https://your-id.ngrok-free.app)")
    parser.add_argument("--name", default=None, help="Device label (e.g. 'work-laptop', 'iphone-15')")
    parser.add_argument("--new", action="store_true", help="Generate a fresh device token")
    args = parser.parse_args()

    # Determine server URL
    default_server = os.getenv("SERVER_URL", "http://localhost:8000")
    server_url = (args.url or default_server).rstrip("/")


    existing_tokens = get_existing_tokens()

    if args.new or not existing_tokens:
        label = args.name or "device"
        token = f"dev_{secrets.token_hex(16)}"
        add_token_to_env(token)
        print(f"✨ Created and saved new token for '{label}': {token}")
    else:
        token = existing_tokens[0]

    # Instant Web App Pairing Link (auto-authenticates and clears token from URL)
    direct_link = f"{server_url}/?token={token}"

    print("\n" + "=" * 65)
    print("           🔐 PERSONAL AI ASSISTANT - DEVICE PAIRING")
    print("=" * 65)
    print(f"\n🔑 Device Token: {token}")
    print(f"🌐 Server URL:   {server_url}")
    print(f"🔗 Direct Link:  {direct_link}")

    print("\n--- 💻 Option 1: On Your Other Laptop Browser ---")
    print(f"Open this URL (it will automatically pair and save your token):")
    print(f"  👉 {direct_link}")

    print("\n--- 📱 Option 2: On Your Mobile Phone ---")
    print("Scan the QR code below with your phone camera.")
    print("It will open the app and automatically pair your phone.")
    print("Then tap 'Share' -> 'Add to Home Screen' to install it as an app!")

    # Display QR encoding the direct web link for camera scanning
    display_qr(direct_link)

    print("\n--- ⚡ Option 3: Terminal / Scripts (curl -N) ---")
    print(f'curl -N -X POST "{server_url}/chat" \\')
    print(f'     -H "X-Device-Token: {token}" \\')
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"message": "Hello from another laptop!"}\'')
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
