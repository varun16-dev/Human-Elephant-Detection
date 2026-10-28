#!/usr/bin/env python3
"""
CLI Utility: Send One Real Twilio SMS Alert (Explicit Confirmation Required)
Department of AI & ML, Sri Sairam College of Engineering

Usage:
  # Dry-run preview (Does NOT send SMS):
  python send_twilio_test_sms.py

  # Send one real SMS to configured recipient (Requires explicit --confirm):
  python send_twilio_test_sms.py --confirm

  # Optional parameters:
  python send_twilio_test_sms.py --confirm --count 2 --location "Sector 4 Corridor" --format concise
"""

import os
import sys
import argparse
from datetime import datetime

# Add project root to Python module path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from twilio_sms_service import (
    get_twilio_sms_manager,
    BilingualTwilioMessageBuilder,
    mask_credential,
    mask_phone_number
)


def main():
    parser = argparse.ArgumentParser(
        description="Explicit Test SMS Sender for Twilio Programmable Messaging"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Explicit authorization flag. Must be specified to actually send an SMS."
    )
    parser.add_argument(
        "--to",
        type=str,
        default=None,
        help="Destination phone number (E.164 format, e.g. +91XXXXXXXXXX). Defaults to TWILIO_TO_NUMBER in .env"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Simulated elephant count (default: 1)"
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        help="Monitoring zone name (default: configured location or 'Monitoring Zone 1')"
    )
    parser.add_argument(
        "--state",
        type=str,
        default=None,
        choices=["tamil_nadu", "karnataka"],
        help="Monitoring state for regional language (default: configured state or 'tamil_nadu')"
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["standard", "concise"],
        help="Message format template ('standard' or 'concise', default: configured format)"
    )

    args = parser.parse_args()

    mgr = get_twilio_sms_manager()
    status = mgr.get_safe_status()

    target_to = (args.to or mgr.config.get("to_number", "")).strip()
    target_location = (args.location or mgr.config.get("location_name", "Monitoring Zone 1")).strip()
    target_state = (args.state or mgr.config.get("state", "tamil_nadu")).strip()
    target_format = (args.format or mgr.config.get("message_format", "standard")).strip()

    print("=" * 65)
    print(" Twilio Programmable SMS - Live Test Utility")
    print("=" * 65)
    print(f" Account SID:          {status['account_sid_masked']}")
    print(f" From Number:          {status['from_number_masked']}")
    print(f" Messaging Service SID:{status['messaging_service_sid_masked']}")
    print(f" Target Recipient:     {mask_phone_number(target_to)}")
    print(f" Format:               {target_format}")
    print(f" Elephant Count:       {args.count}")
    print(f" Location:             {target_location}")
    print(f" State:                {target_state}")
    print("-" * 65)

    if not status["is_configured"]:
        print("\n[ERROR] Twilio is not fully configured.")
        print("Please check your .env file and ensure:")
        print("  - TWILIO_ACCOUNT_SID is set (starts with AC...)")
        print("  - TWILIO_AUTH_TOKEN is set")
        print("  - Either TWILIO_FROM_NUMBER or TWILIO_MESSAGING_SERVICE_SID is set")
        print("  - TWILIO_TO_NUMBER is set")
        sys.exit(1)

    if not target_to:
        print("\n[ERROR] Target recipient number is required (use --to +91XXXXXXXXXX or set TWILIO_TO_NUMBER in .env)")
        sys.exit(1)

    # Build the message
    now_str = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    message_body = BilingualTwilioMessageBuilder.build_alert_message(
        count=args.count,
        location=target_location,
        state=target_state,
        timestamp_str=now_str,
        format_type=target_format
    )
    metrics = BilingualTwilioMessageBuilder.calculate_segments(message_body)

    print("\n--- Message Preview ---")
    print(message_body)
    print("-" * 65)
    print(f"Length: {metrics['char_count']} chars | Segments: {metrics['segment_count']} ({metrics['encoding']})")
    print("-" * 65)

    if not args.confirm:
        print("\n[DRY RUN ONLY] No SMS was sent.")
        print("To send this test SMS to the authorized destination number, run:")
        print(f"  python send_twilio_test_sms.py --confirm")
        sys.exit(0)

    print("\n[SENDING] Dispatching test SMS via Twilio API...")
    success, result_msg, record = mgr.send_sms(to_number=target_to, body=message_body)

    if success:
        print("\n[SUCCESS] SMS submitted to Twilio!")
        print(f" Message SID: {record.get('message_sid')}")
        print(f" Status:      {record.get('status')}")
        print(f" Info:        {result_msg}")
        print("\nNote: Status is 'QUEUED' or 'SENT' at Twilio. For final delivery confirmation,")
        print("check Twilio Console logs or configure StatusCallback webhook URL.")
    else:
        print(f"\n[FAILED] Could not send SMS: {result_msg}")
        if "21608" in str(record.get("error_message", "")):
            print("\nAction required for Twilio Trial Accounts:")
            print("  1. Visit: https://console.twilio.com/us1/develop/phone-numbers/manage/verified")
            print(f"  2. Add and verify recipient number: {mask_phone_number(target_to)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
