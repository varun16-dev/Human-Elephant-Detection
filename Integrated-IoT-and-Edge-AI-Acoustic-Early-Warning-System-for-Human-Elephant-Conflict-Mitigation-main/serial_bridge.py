#!/usr/bin/env python3
"""
USB Serial Telemetry Bridge for ESP32
Reads live telemetry JSON strings emitted by esp32_node.ino over USB Serial (e.g., COM16)
and forwards them directly to the Flask backend endpoint: http://127.0.0.1:5000/api/esp32/data.
"""

import sys
import time
import json
import requests
import serial
from serial.tools import list_ports

FLASK_ENDPOINT = "http://127.0.0.1:5000/api/esp32/data"
DEFAULT_BAUD = 115200

def detect_port():
    ports = list(list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["cp210", "ch340", "usb to uart", "ftdi", "silicon labs", "esp"]):
            return p.device
    if ports:
        return ports[0].device
    return "COM16"

def run_bridge(port_name=None):
    target_port = port_name or detect_port()
    print("=" * 60)
    print("   ESP32 USB SERIAL TELEMETRY BRIDGE")
    print("=" * 60)
    print(f"Target Port : {target_port} @ {DEFAULT_BAUD} baud")
    print(f"Forwarding  : {FLASK_ENDPOINT}")
    print("=" * 60)
    print("Note: If Arduino IDE Serial Monitor is open, close it so this bridge can access the port.\n")

    while True:
        try:
            print(f"[SERIAL] Connecting to {target_port}...")
            ser = serial.Serial(target_port, DEFAULT_BAUD, timeout=1)
            print(f"[SERIAL] Connected to {target_port}! Listening for telemetry...\n")

            while True:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if not line:
                    continue

                # esp32_node.ino emits JSON lines starting with {"deviceId"
                if line.startswith("{") and "deviceId" in line:
                    try:
                        payload = json.loads(line)
                        print(f"[RX-JSON] Received from {payload.get('deviceId')}: PIR={payload.get('pir')}, Sound={payload.get('sound')}")
                        resp = requests.post(FLASK_ENDPOINT, json=payload, timeout=2)
                        if resp.status_code == 200:
                            print(f"[FORWARD] Successfully forwarded to Flask (Status: {resp.status_code})")
                        else:
                            print(f"[FORWARD-WARN] Flask returned status: {resp.status_code}")
                    except json.JSONDecodeError:
                        pass
                    except Exception as post_err:
                        print(f"[FORWARD-ERR] Error sending to Flask: {post_err}")
                else:
                    # Informational serial line from ESP32
                    if any(key in line for key in ["WiFi", "IP", "Dashboard", "GPS", "ALERT", "HTTP"]):
                        print(f"[ESP32-LOG] {line}")

        except serial.SerialException as se:
            err_str = str(se)
            if "PermissionError" in err_str or "Access is denied" in err_str:
                print(f"[SERIAL ERROR] Port {target_port} is busy or locked (e.g. by Arduino IDE Serial Monitor).")
                print("                 Please close Arduino IDE Serial Monitor to allow data forwarding.")
            else:
                print(f"[SERIAL ERROR] {se}")
            time.sleep(3)
        except KeyboardInterrupt:
            print("\n[SERIAL] Bridge stopped by user.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(3)

if __name__ == '__main__':
    port = sys.argv[1] if len(sys.argv) > 1 else None
    run_bridge(port)
