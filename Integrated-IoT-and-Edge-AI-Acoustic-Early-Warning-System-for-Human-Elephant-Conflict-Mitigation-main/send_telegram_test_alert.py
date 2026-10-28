#!/usr/bin/env python3
"""
CLI Utility: Verify and Send Telegram Bot Alert
Department of AI & ML, Sri Sairam College of Engineering

Usage:
  # Check Bot Token and Chat ID without sending an alert:
  python send_telegram_test_alert.py

  # Send one real test alert message (Requires explicit --confirm):
  python send_telegram_test_alert.py --confirm

  # Send a bilingual elephant detection alert with photo:
  python send_telegram_test_alert.py --confirm --bilingual --count 2 --location "Sector 4 Corridor"

  # Test custom credentials from command line:
  python send_telegram_test_alert.py --token "123456:ABC-DEF..." --chat "987654321" --confirm
"""

import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Add project root to module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

from free_alert_service import TelegramAlertDispatcher, FreeAlertManager


def main():
    parser = argparse.ArgumentParser(
        description="Verify Telegram Bot Credentials and Dispatch Test Alerts"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Explicit authorization flag. Required to send a live message to Telegram."
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Telegram Bot Token from @BotFather. Defaults to TELEGRAM_BOT_TOKEN in .env"
    )
    parser.add_argument(
        "--chat",
        type=str,
        default=None,
        help="Telegram Chat ID or Channel (@channel). Defaults to TELEGRAM_CHAT_ID in .env"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Elephant count for simulated alert (default: 3)"
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Monitoring Zone 1",
        help="Monitoring location name (default: 'Monitoring Zone 1')"
    )
    parser.add_argument(
        "--bilingual",
        action="store_true",
        default=True,
        help="Format alert in English and Tamil (default: True)"
    )
    parser.add_argument(
        "--photo",
        type=str,
        default=None,
        help="Optional path to elephant detection image to attach"
    )

    args = parser.parse_args()

    token = (args.token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = (args.chat or os.getenv("TELEGRAM_CHAT_ID", "")).strip()

    masked_token = FreeAlertManager.mask_sender("telegram", token)
    masked_chat = FreeAlertManager.mask_recipient("telegram", chat_id)

    print("=" * 65)
    print(" Telegram Bot Alert System - Diagnostic & Verification Tool")
    print("=" * 65)
    print(f" Bot Token:   {masked_token}")
    print(f" Target Chat: {masked_chat}")
    print("-" * 65)

    if not token:
        print("\n[ERROR] Telegram Bot Token is missing.")
        print("Please configure TELEGRAM_BOT_TOKEN in your .env file or pass --token.")
        print("Tip: You can create a new bot and get a token via @BotFather on Telegram.")
        sys.exit(1)

    dispatcher = TelegramAlertDispatcher(bot_token=token, default_chat_id=chat_id)

    # Step 1: Verify token with Telegram API (getMe)
    print("\n[STEP 1] Validating Bot Token with Telegram API...")
    import requests
    try:
        me_resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        me_data = me_resp.json()
        if not me_data.get("ok"):
            desc = me_data.get("description", "Unknown error")
            print(f"[FAILED] Invalid Bot Token: {desc}")
            sys.exit(1)

        bot_info = me_data.get("result", {})
        bot_user = bot_info.get("username", "Unknown")
        bot_first = bot_info.get("first_name", "Bot")
        print(f"[OK] Token valid! Connected to bot: @{bot_user} ({bot_first})")
    except Exception as e:
        print(f"[ERROR] Could not reach Telegram API: {e}")
        sys.exit(1)

    # Step 2: Prepare the trilingual alert text matching user's exact specification
    alert_text = TelegramAlertDispatcher.build_trilingual_alert(
        count=args.count,
        location=args.location,
        dt_or_str=datetime.now()
    )

    print("\n--- Alert Message Preview ---")
    clean_preview = alert_text.replace("<b>", "").replace("</b>", "")
    try:
        print(clean_preview)
    except UnicodeEncodeError:
        print(clean_preview.encode("ascii", errors="replace").decode("ascii"))
    print("-" * 65)

    if not chat_id:
        print("\n[NOTICE] TELEGRAM_CHAT_ID is not configured.")
        print("Please set TELEGRAM_CHAT_ID in .env or pass --chat <your_chat_id>.")
        print("How to get your Chat ID:")
        print("  1. Open Telegram and search for @userinfobot or @RawDataBot.")
        print("  2. Start the bot to see your numeric Chat ID (e.g., 123456789).")
        print(f"  3. Open your bot @{bot_user} and click 'Start' (/start) so it has permission to message you.")
        sys.exit(0)

    # Step 3: Send or dry-run
    if not args.confirm:
        print("\n[DRY RUN ONLY] Token verified successfully. No message sent.")
        print(f"Make sure you have started your bot @{bot_user} by sending /start in Telegram.")
        print("To send this test alert to your Telegram chat, run:")
        print(f"  python send_telegram_test_alert.py --confirm")
        sys.exit(0)

    print(f"\n[SENDING] Dispatching test alert to Chat ID: {masked_chat}...")
    success, msg = dispatcher.send_alert(
        text=alert_text,
        chat_id=chat_id,
        parse_mode="HTML",
        photo_path=args.photo,
        severity="CRITICAL",
        raw=True
    )

    if success:
        print(f"\n[SUCCESS] Alert dispatched to Telegram!")
        print(f"Info: {msg}")
        print(f"Check your Telegram app (@{bot_user}) for the incoming message.")
    else:
        print(f"\n[FAILED] Could not deliver message to Telegram: {msg}")
        if "403" in msg or "Forbidden" in msg or "bot was blocked" in msg:
            print("\nAction required:")
            print(f"  You must open Telegram, search for @{bot_user}, and click 'START' (/start).")
            print("  Telegram security prevents bots from initiating chats without user authorization.")
        elif "400" in msg or "chat not found" in msg:
            print("\nAction required:")
            print("  The specified Chat ID was not found. Please double-check your numeric Chat ID.")
        sys.exit(1)


if __name__ == "__main__":
    main()
