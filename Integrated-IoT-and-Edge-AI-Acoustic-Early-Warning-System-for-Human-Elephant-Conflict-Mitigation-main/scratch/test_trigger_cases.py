import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def post_telemetry(pir, sound, label):
    url = f"{BASE_URL}/api/esp32/data"
    payload = {
        "deviceId": "ESP32-NODE-01",
        "pir": pir,
        "sound": sound,
        "gpsFix": False,
        "latitude": None,
        "longitude": None,
        "satellites": 0,
        "alert": pir or sound,
        "wifiRSSI": -65,
        "ledStrobe": False,
        "strobeManualControl": False
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            print(f"[{label}] HTTP {resp.status} - Status: {res.get('status')}")
            return res
    except Exception as e:
        print(f"[{label}] Error: {e}")
        return None

def get_detection_status():
    url = f"{BASE_URL}/api/detection/status"
    try:
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"Error checking status: {e}")
        return {}

def test_api_trigger(pir, sound, label):
    url = f"{BASE_URL}/api/detection/trigger"
    payload = {"pir": pir, "sound": sound}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            print(f"[{label}] Trigger Result: {json.dumps(res)}")
            return res
    except Exception as e:
        print(f"[{label}] Error: {e}")
        return None

print("Checking initial status...")
init_status = get_detection_status()
print(f"Initial status: {json.dumps(init_status)}")

print("\n--- TEST CASE 1: PIR = OFF (False), Sound = OFF (False) ---")
res1 = test_api_trigger(False, False, "CASE 1")
print(f"Expected: NOT triggered. Got: triggered={res1.get('triggered') if res1 else None}")
assert res1 and res1.get('triggered') == False, "CASE 1 Failed: Should NOT trigger when PIR=OFF and Sound=OFF"

print("\n--- TEST CASE 2: PIR = ON (True), Sound = OFF (False) ---")
res2 = test_api_trigger(True, False, "CASE 2")
print(f"Expected: Triggered. Got: triggered={res2.get('triggered') if res2 else None}, message={res2.get('message')}")
assert res2 and res2.get('triggered') == True, "CASE 2 Failed: Should trigger when PIR=ON"

print("\n--- TEST CASE 3: PIR = OFF (False), Sound = ON (True) ---")
# If case 2 started a process or triggered, let's see if duplicate/cooldown or trigger works
res3 = test_api_trigger(False, True, "CASE 3")
print(f"Expected: Triggered. Got: triggered={res3.get('triggered') if res3 else None}, message={res3.get('message')}")
assert res3 and res3.get('triggered') == True, "CASE 3 Failed: Should trigger when Sound=ON"

print("\n--- TEST CASE 4: PIR = ON (True), Sound = ON (True) ---")
res4 = test_api_trigger(True, True, "CASE 4")
print(f"Expected: Triggered only once. Got: triggered={res4.get('triggered') if res4 else None}, message={res4.get('message')}")
assert res4 and res4.get('triggered') == True, "CASE 4 Failed: Should trigger when both are ON"

print("\n--- TESTING TELEMETRY INGESTION ENDPOINT (/api/esp32/data) ---")
print("1. Sending telemetry PIR=False, Sound=False...")
tel_res1 = post_telemetry(False, False, "TELEMETRY PIR=0, SOUND=0")
print("2. Sending telemetry PIR=True, Sound=False...")
tel_res2 = post_telemetry(True, False, "TELEMETRY PIR=1, SOUND=0")

final_status = get_detection_status()
print(f"\nFinal status: {json.dumps(final_status)}")
print("\nALL TEST CASES PASSED SUCCESSFULLY!")
