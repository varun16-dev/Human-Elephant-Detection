#!/usr/bin/env python3
"""
CLI Utility: Unified Trilingual Test Alert Dispatcher (WhatsApp & Telegram)
Department of AI & ML, Sri Sairam College of Engineering

Sends the standardized trilingual elephant detection alert:
1. English
2. Kannada (ಕನ್ನಡ)
3. Tamil (தமிழ்)

Channels:
- Telegram: Via existing configured Telegram Bot (@Vetrax_Alert_bot)
- WhatsApp: Via PyWhatKit to WhatsApp Web

Usage:
  # 1. Preview message and verify connections (Dry Run - No messages sent):
  python send_unified_test_alert.py

  # 2. Send live test to BOTH Telegram and WhatsApp (Requires explicit --confirm):
  python send_unified_test_alert.py --confirm

  # 3. Send live test to WhatsApp only:
  python send_unified_test_alert.py --whatsapp --confirm

  # 4. Send live test to Telegram only:
  python send_unified_test_alert.py --telegram --confirm

  # 5. Custom count and location:
  python send_unified_test_alert.py --confirm --count 3 --location "Monitoring Zone 1" --phone "+917094528671"
"""

import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from trilingual_message_builder import build_trilingual_alert
from free_alert_service import TelegramAlertDispatcher, FreeAlertManager
from whatsapp_pywhatkit_service import (
    get_whatsapp_service,
    normalize_phone_number,
    mask_phone_number
)


def main():
    parser = argparse.ArgumentParser(
        description="Unified Trilingual Elephant Alert Verification Tool (WhatsApp + Telegram)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Explicit authorization flag. Required to send live messages."
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        default=False,
        help="Target Telegram only."
    )
    parser.add_argument(
        "--whatsapp",
        action="store_true",
        default=False,
        help="Target WhatsApp only."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Simulated elephant count (default: 3)"
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Monitoring Zone 1",
        help="Monitoring zone name (default: 'Monitoring Zone 1')"
    )
    parser.add_argument(
        "--phone",
        type=str,
        default=None,
        help="Target WhatsApp recipient phone number (defaults to configured number)"
    )

    args = parser.parse_args()

    # Determine targets: if neither --telegram nor --whatsapp is passed, default to BOTH
    send_tg = args.telegram or (not args.telegram and not args.whatsapp)
    send_wa = args.whatsapp or (not args.telegram and not args.whatsapp)

    # 1. Inspect Telegram configuration
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    masked_token = FreeAlertManager.mask_sender("telegram", tg_token)
    masked_chat = FreeAlertManager.mask_recipient("telegram", tg_chat)

    # 2. Inspect WhatsApp configuration
    wa_service = get_whatsapp_service()
    raw_phone = args.phone or wa_service.config.get("default_phone") or os.getenv("WHATSAPP_TARGET_PHONE", "+917094528671")
    norm_phone, phone_err = normalize_phone_number(raw_phone)
    masked_phone = mask_phone_number(norm_phone) if norm_phone else "Invalid"

    print("=" * 68)
    print(" Unified Trilingual Alert Dispatcher - Diagnostic & Verification Tool")
    print("=" * 68)
    if send_tg:
        print(f" [Telegram Bot]   Token: {masked_token}")
        print(f" [Telegram Chat]  Target: {masked_chat}")
    if send_wa:
        print(f" [WhatsApp]       Target Phone: {masked_phone} ({'OK' if norm_phone else phone_err})")
        print(f" [WhatsApp Mode]  PyWhatKit (WhatsApp Web Automation)")
    print("-" * 68)

    # Step 1: Validate credentials
    if send_tg:
        if not tg_token:
            print("[NOTICE] TELEGRAM_BOT_TOKEN is not configured in .env.")
        else:
            try:
                import requests
                me_resp = requests.get(f"https://api.telegram.org/bot{tg_token}/getMe", timeout=8)
                me_data = me_resp.json()
                if me_data.get("ok"):
                    bot_user = me_data.get("result", {}).get("username", "Unknown")
                    print(f"[OK] Telegram Bot Connected: @{bot_user}")
                else:
                    print(f"[WARN] Telegram Bot Token error: {me_data.get('description')}")
            except Exception as e:
                print(f"[WARN] Could not reach Telegram API: {e}")

    # Step 2: Build the identical shared trilingual alert
    alert_text = build_trilingual_alert(
        elephant_count=args.count,
        location=args.location,
        timestamp=datetime.now().astimezone()
    )

    print("\n--- Shared Trilingual Alert Preview (WhatsApp & Telegram) ---")
    try:
        print(alert_text)
    except UnicodeEncodeError:
        print(alert_text.encode("ascii", errors="replace").decode("ascii"))
    print("-" * 68)

    # Step 3: Check confirmation
    if not args.confirm:
        print("\n[DRY RUN ONLY] Preview generated successfully. No live messages sent.")
        print("To send this live test alert, run with explicit --confirm:")
        if send_tg and send_wa:
            print("  python send_unified_test_alert.py --confirm")
        elif send_wa:
            print("  python send_unified_test_alert.py --whatsapp --confirm")
        elif send_tg:
            print("  python send_unified_test_alert.py --telegram --confirm")
        sys.exit(0)

    # Step 4: Dispatches
    print("\n[EXECUTION] Dispatching authorized test alerts...")

    # A. Telegram Dispatch
    if send_tg:
        if not tg_token or not tg_chat:
            print("\n[TELEGRAM: SKIPPED] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        else:
            print(f"\n[TELEGRAM] Sending alert to Chat ID: {masked_chat}...")
            tg_dispatcher = TelegramAlertDispatcher(bot_token=tg_token, default_chat_id=tg_chat)
            ok, msg = tg_dispatcher.send_alert(
                text=alert_text,
                chat_id=tg_chat,
                parse_mode="HTML",
                severity="CRITICAL",
                raw=True
            )
            if ok:
                print(f"[TELEGRAM: SUCCESS] Message delivered to Telegram Bot API!")
                print(f"Details: {msg}")
            else:
                print(f"[TELEGRAM: FAILED] {msg}")

    # B. WhatsApp Dispatch via PyWhatKit
    if send_wa:
        if not norm_phone:
            print(f"\n[WHATSAPP: SKIPPED] Invalid recipient phone: {phone_err}")
        else:
            print(f"\n[WHATSAPP] Launching PyWhatKit dispatch to {masked_phone}...")
            print("Notice: PyWhatKit will open WhatsApp Web in your default browser.")
            print("Ensure you are logged into WhatsApp Web on this machine.")

            wa_res = wa_service.send_single_test_message(
                phone=norm_phone,
                count=args.count,
                location=args.location,
                confirmed=True
            )

            if wa_res.get("success"):
                print(f"[WHATSAPP: ATTEMPT COMPLETED] Keystroke sent via browser automation.")
                print(f"Details: {wa_res.get('details')}")
                print(f"Duration: {wa_res.get('duration_s')}s")
            else:
                print(f"[WHATSAPP: FAILED] {wa_res.get('error')}")

    print("\n" + "=" * 68)
    print(" Verification run finished. Check your Telegram app and WhatsApp Web.")
    print("=" * 68)


if __name__ == "__main__":
    main()
