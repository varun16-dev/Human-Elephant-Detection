import cv2
import csv
import os
import sys
import time
import threading
from datetime import datetime

# Ensure working directory is always the script folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def safe_pause():
    try:
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to close...")
    except Exception:
        pass

import json
import pyttsx3
import argparse
import urllib.request
import numpy as np

# =====================================================
# ESP32 WEBCAM & CAMERA SOURCE CONFIGURATION
# =====================================================
CONFIG_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_config.json")

def load_saved_camera_config():
    """Loads saved camera source from camera_config.json"""
    if os.path.exists(CONFIG_JSON_PATH):
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_camera_config(source_str):
    """Persists camera source so it is remembered across runs"""
    try:
        raw_val = str(source_str).strip()
        data = {
            "camera_source": format_camera_source(raw_val) if not raw_val.isdigit() else int(raw_val),
            "raw_input": raw_val,
            "updated_at": datetime.now().isoformat()
        }
        if ":" in raw_val:
            data["esp32_ip"] = raw_val.split(":")[0].replace("http://", "").replace("https://", "").replace("/", "")
        elif not raw_val.isdigit():
            data["esp32_ip"] = raw_val.replace("http://", "").replace("https://", "").replace("/", "")
        with open(CONFIG_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[CONFIG] Warning: Could not save camera config: {e}")

def format_camera_source(src):
    """
    Normalizes camera source.
    - If digit (e.g. 0, 1): returns integer camera index.
    - If starts with http/https/rtsp: returns full URL.
    - If IP or IP:PORT (e.g. 10.57.175.25 or 10.57.175.25:81): formats as ESP32 stream URL.
    """
    if src is None:
        return 0
    s = str(src).strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    if s.startswith(("http://", "https://", "rtsp://")):
        return s
    
    # Format bare IP or IP:PORT to standard ESP32-CAM stream URL
    if ":" in s:
        parts = s.split(":")
        ip = parts[0]
        port_path = parts[1]
        if "/stream" in s or "/mjpeg" in s or "/video" in s or "/" in port_path:
            return f"http://{s}"
        elif port_path.startswith("81"):
            return f"http://{ip}:81/stream"
        else:
            return f"http://{s}/"
    else:
        # Default ESP32 camera stream endpoint (port 80 root stream)
        return f"http://{s}/"

def get_camera_source_input(cli_arg=None, force_prompt=False):
    """
    Determines camera source. If CLI arg is provided, uses it.
    Otherwise, uses saved camera_config.json.
    """
    saved_cfg = load_saved_camera_config()
    saved_src = saved_cfg.get("camera_source")
    if saved_src is None:
        saved_src = os.environ.get("ESP32_CAM_IP") or 0
    
    if cli_arg is not None and str(cli_arg).strip():
        chosen = str(cli_arg).strip()
        save_camera_config(chosen)
        return format_camera_source(chosen)
    
    is_interactive = False
    try:
        is_interactive = sys.stdin and sys.stdin.isatty()
    except Exception:
        pass
    
    if is_interactive or force_prompt:
        print("\n" + "=" * 65)
        print("                   CAMERA SOURCE SETUP")
        print("=" * 65)
        print("Select Camera:")
        print("  0 : Camera Index 0")
        print("  1 : Camera Index 1")
        print("  Or enter ESP32 IP/Stream URL (e.g. 192.168.1.50)")
        print(f"Press Enter to use current [{saved_src}]:")
        try:
            user_input = input("Camera >> ").strip()
            if user_input:
                save_camera_config(user_input)
                return format_camera_source(user_input)
        except (EOFError, KeyboardInterrupt):
            print("\nUsing default camera source.")
        except Exception:
            pass

    return format_camera_source(saved_src)

parser = argparse.ArgumentParser(description="Elephant Camera Detection Engine")
parser.add_argument("--device-id", default="ESP32-NODE-01", help="Associated ESP32 Device ID")
parser.add_argument("--trigger-source", default="MANUAL", help="Trigger source: PIR, SOUND, PIR_AND_SOUND, MANUAL")
parser.add_argument("--session-seconds", type=int, default=15, help="Session duration in seconds (0 = run indefinitely)")
parser.add_argument("--camera-source", "--camera-index", dest="camera_source", default=None, help="Camera index (e.g. 0) or ESP32 Webcam IP/URL (e.g. 192.168.1.50)")
parser.add_argument("--prompt-ip", action="store_true", help="Always prompt for ESP32 IP before starting")
parser.add_argument("--headless", action="store_true", help="Run without GUI window")
parser.add_argument("--confidence-threshold", type=float, default=0.72, help="Confidence threshold for elephant detection (default: 0.72)")
args, _ = parser.parse_known_args()

# =====================================================
# SETTINGS
# =====================================================
CONFIDENCE_THRESHOLD = float(args.confidence_threshold)
CAMERA_SOURCE = get_camera_source_input(args.camera_source, force_prompt=args.prompt_ip)
LOG_INTERVAL_SECONDS = 1
DEVICE_ID = args.device_id
TRIGGER_SOURCE = args.trigger_source
SESSION_SECONDS = args.session_seconds
HEADLESS = args.headless or os.getenv("ELEPHANT_HEADLESS", "0").lower() in ("1", "true", "yes")

CLASS_FILE = "coco.data"
CONFIG_FILE = "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt.txt"
WEIGHTS_FILE = "frozen_inference_graph.pb"

CSV_FILE = "elephant_detection_dataset.csv"
IMAGE_FOLDER = "detected_elephants"

# =====================================================
# CREATE IMAGE FOLDER
# =====================================================
os.makedirs(IMAGE_FOLDER, exist_ok=True)

# =====================================================
# CHECK REQUIRED FILES
# =====================================================
required_files = [
    CLASS_FILE,
    CONFIG_FILE,
    WEIGHTS_FILE
]

for required_file in required_files:
    if not os.path.exists(required_file):
        print("ERROR: File not found:", required_file)
        print("Keep all model files in the same folder as this program.")
        safe_pause()
        raise SystemExit(1)

# =====================================================
# LOAD COCO CLASS NAMES
# =====================================================
with open(CLASS_FILE, "rt", encoding="utf-8") as file:
    class_names = file.read().strip().splitlines()

print("Total classes loaded:", len(class_names))

if "elephant" not in [
    class_name.strip().lower()
    for class_name in class_names
]:
    print("ERROR: Elephant class is not present in coco.data")
    safe_pause()
    raise SystemExit(1)

# =====================================================
# LOAD MOBILENET SSD MODEL
# =====================================================
try:
    net = cv2.dnn_DetectionModel(
        WEIGHTS_FILE,
        CONFIG_FILE
    )

    net.setInputSize(320, 320)
    net.setInputScale(1.0 / 127.5)
    net.setInputMean((127.5, 127.5, 127.5))
    net.setInputSwapRB(True)

except cv2.error as error:
    print("ERROR: Model could not be loaded.")
    print(error)
    safe_pause()
    raise SystemExit(1)

# =====================================================
# VOICE ALERT FUNCTION
# =====================================================
voice_is_speaking = False
voice_lock = threading.Lock()


def speak_elephant_alert(elephant_count):
    global voice_is_speaking

    with voice_lock:
        if voice_is_speaking:
            return

        voice_is_speaking = True

    def voice_worker():
        global voice_is_speaking

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.setProperty("volume", 1.0)

            if elephant_count == 1:
                message = "Warning! Elephant detected."
            else:
                message = (
                    f"Warning! {elephant_count} elephants detected."
                )

            engine.say(message)
            engine.runAndWait()
            engine.stop()

        except Exception as error:
            print("Voice error:", error)

        finally:
            with voice_lock:
                voice_is_speaking = False

    threading.Thread(
        target=voice_worker,
        daemon=True
    ).start()


def sync_detection_to_backend(elephant_count, highest_confidence, image_path, timestamp_iso):
    """Asynchronously pushes detection to backend API and Supabase without blocking camera frames"""
    def worker():
        try:
            import requests
            payload = {
                "device_id": "ESP32-NODE-01",
                "timestamp": timestamp_iso,
                "elephant_count": int(elephant_count),
                "confidence": float(highest_confidence),
                "image_name": os.path.basename(image_path) if image_path else "",
                "image_full_path": os.path.abspath(image_path) if image_path else ""
            }
            try:
                res = requests.post("http://127.0.0.1:5000/api/camera/detection-event", json=payload, timeout=2.5)
                if res.status_code == 200:
                    return
            except Exception:
                pass
                
            # Direct Supabase fallback if local server is unreachable
            try:
                from supabase import create_client
                env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Integrated-IoT-and-Edge-AI-Acoustic-Early-Warning-System-for-Human-Elephant-Conflict-Mitigation-main', '.env'))
                sb_url = None
                sb_key = None
                if os.path.exists(env_path):
                    with open(env_path, 'r', encoding='utf-8') as f_env:
                        for line in f_env:
                            if line.startswith('SUPABASE_URL='):
                                sb_url = line.strip().split('=', 1)[1]
                            elif line.startswith('SUPABASE_SERVICE_ROLE_KEY='):
                                sb_key = line.strip().split('=', 1)[1]
                if sb_url and sb_key:
                    sb = create_client(sb_url, sb_key)
                    conf_norm = round(float(highest_confidence) / 100.0 if float(highest_confidence) > 1.0 else float(highest_confidence), 4)
                    clean_name = os.path.basename(image_path) if image_path else ""
                    if clean_name and os.path.exists(image_path):
                        with open(image_path, 'rb') as f_img:
                            sb.storage.from_('elephant-images').upload(
                                path=clean_name,
                                file=f_img.read(),
                                file_options={"content-type": "image/jpeg", "upsert": "true"}
                            )
                    sb.table('detections').insert({
                        "device_id": "ESP32-NODE-01",
                        "timestamp": timestamp_iso,
                        "detection": "ELEPHANT_DETECTED",
                        "elephant_count": int(elephant_count),
                        "confidence": conf_norm,
                        "image_path": clean_name,
                        "pir_detected": True,
                        "sound_detected": True,
                        "sound_level": 85,
                        "latitude": 12.8224,
                        "longitude": 77.577,
                        "incident_status": "pending",
                        "alert_sent": True
                    }).execute()
                    print("[SYNC] Direct Supabase push complete.")
            except Exception:
                pass
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


# =====================================================
# ESP32 MJPEG STREAM CAPTURE ENGINE
# =====================================================
class ESP32CameraCapture:
    """
    High-performance MJPEG stream decoder for ESP32-CAM.
    Decodes JPEG frames continuously in a background thread to eliminate latency.
    Implements standard cv2.VideoCapture interface.
    """
    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.running = True
        self.last_frame = None
        self.last_frame_time = 0
        self.first_frame_event = threading.Event()
        self.lock = threading.Lock()
        
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        
        # Wait up to 5 seconds for the first frame
        self.opened = self.first_frame_event.wait(timeout=5.0)
        if not self.opened:
            self.release()

    def _worker(self):
        while self.running:
            stream = None
            try:
                req = urllib.request.Request(self.stream_url, headers={'User-Agent': 'Mozilla/5.0'})
                stream = urllib.request.urlopen(req, timeout=6.0)
                buffer = b""
                while self.running:
                    chunk = stream.read(2048)
                    if not chunk:
                        time.sleep(0.01)
                        continue
                    buffer += chunk
                    
                    if len(buffer) > 150000:
                        a = buffer.rfind(b'\xff\xd8')
                        if a != -1:
                            buffer = buffer[a:]
                        else:
                            buffer = b""
                            continue

                    a = buffer.find(b'\xff\xd8')
                    b = buffer.find(b'\xff\xd9', a)
                    if a != -1 and b != -1 and b > a:
                        jpg_bytes = buffer[a:b+2]
                        buffer = buffer[b+2:]
                        frame = cv2.imdecode(np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            with self.lock:
                                self.last_frame = frame
                                self.last_frame_time = time.time()
                            if not self.first_frame_event.is_set():
                                self.first_frame_event.set()
            except Exception as e:
                # Print connection diagnosis
                print(f"[ESP32 STREAM DEBUG] Error on {self.stream_url}: {e}")
                time.sleep(1.0)
            finally:
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass

    def isOpened(self):
        return self.opened and self.running

    def read(self):
        with self.lock:
            if self.last_frame is not None and (time.time() - self.last_frame_time < 5.0):
                return True, self.last_frame.copy()
        return False, None

    def get(self, propId):
        with self.lock:
            if self.last_frame is not None:
                if propId == cv2.CAP_PROP_FRAME_WIDTH:
                    return float(self.last_frame.shape[1])
                elif propId == cv2.CAP_PROP_FRAME_HEIGHT:
                    return float(self.last_frame.shape[0])
        return 0.0

    def set(self, propId, value):
        return True

    def release(self):
        self.running = False
        self.opened = False


# =====================================================
# OPEN CAMERA (ESP32 WEBCAM / LOCAL WEBCAM)
# =====================================================
def open_camera_stream(source):
    """
    Opens video capture from an ESP32 network stream or local webcam.
    Never silently falls back to laptop webcam if ESP32 source was requested.
    """
    print(f"\n[CAMERA] Connecting to video source: {source}")
    if isinstance(source, int):
        print(f"[CAMERA] Opening camera device index {source} via DirectShow...")
        c = cv2.VideoCapture(source, cv2.CAP_DSHOW)
        if not c.isOpened():
            for retry in range(1, 4):
                print(f"[CAMERA] Camera index {source} busy or initializing, retrying ({retry}/3)...")
                time.sleep(1.0)
                c = cv2.VideoCapture(source, cv2.CAP_DSHOW)
                if c.isOpened():
                    break
        if c.isOpened():
            c.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            c.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            print(f"[CAMERA] SUCCESS! Opened camera device index {source}")
        else:
            print(f"[CAMERA ERROR] Could not open camera device index {source}.")
            print(f"[CAMERA ERROR] Please ensure no other process is holding the camera.")
        return c

    # Network IP Stream (ESP32-CAM)
    print(f"[CAMERA] Opening ESP32 MJPEG stream: {source} ...")
    cap = ESP32CameraCapture(str(source))
    if cap.isOpened():
        print(f"[CAMERA] SUCCESS! Connected to ESP32 stream: {source}")
        return cap

    # If stream didn't open, try common alternate ESP32 endpoints
    src_str = str(source).strip()
    alternates = []
    if ":81/stream" in src_str:
        alternates.append(src_str.replace(":81/stream", "/"))
        alternates.append(src_str.replace(":81/stream", "/stream"))
    elif src_str.endswith("/"):
        base = src_str[:-1]
        alternates.append(f"{base}:81/stream")
        alternates.append(f"{base}/stream")
    elif "/stream" in src_str:
        alternates.append(src_str.replace("/stream", "/"))
        alternates.append(src_str.replace("/stream", ":81/stream"))

    for alt in alternates:
        print(f"[CAMERA] Retrying alternate ESP32 endpoint: {alt} ...")
        alt_cap = ESP32CameraCapture(alt)
        if alt_cap.isOpened():
            print(f"[CAMERA] SUCCESS! Connected to alternate ESP32 stream: {alt}")
            save_camera_config(alt)
            return alt_cap

    return cap

cap = open_camera_stream(CAMERA_SOURCE)

if not cap.isOpened():
    print(f"\n[ERROR] Camera source could not be opened: {CAMERA_SOURCE}")
    if not isinstance(CAMERA_SOURCE, int):
        print("\n--- ESP32 WEBCAM TROUBLESHOOTING ---")
        print("1. Ensure ESP32-CAM is powered ON and connected to the same Wi-Fi network.")
        print(f"2. Verify the stream URL in your web browser: {CAMERA_SOURCE}")
        print("3. Common ESP32-CAM stream URLs:")
        print("   - http://<ESP32_IP>:81/stream (standard CameraWebServer)")
        print("   - http://<ESP32_IP>/stream")
        print("   - http://<ESP32_IP>:8080/video")
        print("4. Check that your Windows firewall is not blocking incoming RTSP/HTTP streams.")
    else:
        print("\n--- LAPTOP WEBCAM TROUBLESHOOTING ---")
        print("1. Check Windows Settings -> Privacy -> Camera permissions.")
        print("2. Ensure no other applications (Zoom, Teams, Meet, WhatsApp) are using the camera.")
    safe_pause()
    raise SystemExit(1)

# =====================================================
# CREATE CSV DATASET
# =====================================================
csv_already_exists = os.path.exists(CSV_FILE)

csv_file = open(
    CSV_FILE,
    mode="a",
    newline="",
    encoding="utf-8"
)

csv_writer = csv.writer(csv_file)

if not csv_already_exists:
    csv_writer.writerow([
        "Date",
        "Time",
        "Timestamp",
        "Elephant_Detected",
        "Number_of_Elephants",
        "Highest_Confidence_Percent",
        "Saved_Image"
    ])

    csv_file.flush()

def get_camera_name(src):
    """Returns friendly label for camera source"""
    if src == 0:
        return "Laptop Webcam (Cam 0)"
    elif src == 1:
        return "External HD Webcam (Cam 1)"
    elif isinstance(src, int):
        return f"USB Camera {src}"
    else:
        return f"ESP32 Stream ({src})"

def switch_camera_source(new_src, current_cap):
    """Dynamically switch camera capture between Laptop Webcam and External Webcam"""
    global CAMERA_SOURCE, last_switch_time, switch_banner_text, elephant_event_active, current_event_image
    formatted = format_camera_source(new_src)
    if formatted == CAMERA_SOURCE and current_cap is not None and getattr(current_cap, 'isOpened', lambda: False)():
        return current_cap
    
    print(f"\n[CAMERA SWITCH] >>> Switching camera to: {formatted} ({get_camera_name(formatted)}) <<<")
    if current_cap is not None:
        try:
            current_cap.release()
        except Exception:
            pass
        time.sleep(0.3)
    
    new_cap = open_camera_stream(formatted)
    if new_cap and getattr(new_cap, 'isOpened', lambda: False)():
        CAMERA_SOURCE = formatted
        save_camera_config(formatted)
        last_switch_time = time.time()
        switch_banner_text = f"SWITCHED TO: {get_camera_name(formatted)}"
        elephant_event_active = False
        current_event_image = ""
        print(f"[CAMERA SWITCH] SUCCESS! Now running elephant detection on {get_camera_name(formatted)}")
        return new_cap
    else:
        print(f"[CAMERA SWITCH] FAILED to open {formatted}. Falling back to previous {CAMERA_SOURCE}")
        return open_camera_stream(CAMERA_SOURCE)

# =====================================================
# VARIABLES
# =====================================================
last_log_time = 0
last_switch_time = time.time()
switch_banner_text = f"ACTIVE: {get_camera_name(CAMERA_SOURCE)}"
loop_counter = 0

# True while an elephant detection event is active
elephant_event_active = False

# Stores the current event's image
current_event_image = ""

print("\nElephant detection started.")
print(f"Active Camera: {get_camera_name(CAMERA_SOURCE)}")
print("Keyboard Controls:")
print("  - Press 'C' or 'S' to TOGGLE between Laptop Webcam and External Webcam")
print("  - Press '0' to switch to Laptop Webcam (Index 0)")
print("  - Press '1' to switch to External HD Webcam (Index 1)")
print("  - Press 'Q' inside the camera window to stop.")
print("CSV dataset:", CSV_FILE)
print("Detected images:", IMAGE_FOLDER)

# =====================================================
# MAIN DETECTION LOOP
# =====================================================
consecutive_empty_frames = 0
MAX_EMPTY_FRAMES = 30  # Allow up to ~3 seconds of network stutter before exiting

while True:

    success, frame = cap.read()

    # Prevent empty image error with graceful retry for network streams
    if not success or frame is None or frame.size == 0:
        consecutive_empty_frames += 1
        if consecutive_empty_frames >= MAX_EMPTY_FRAMES:
            print("WARNING: Camera stream lost (30 consecutive failed frames). Exiting detection loop.")
            break
        time.sleep(0.1)
        continue

    consecutive_empty_frames = 0

    try:
        # Detect with lower bound to capture both person and elephant context for conflict suppression
        class_ids, confidences, boxes = net.detect(
            frame,
            confThreshold=min(CONFIDENCE_THRESHOLD, 0.40),
            nmsThreshold=0.4
        )

    except cv2.error as error:
        print("Detection error:", error)
        continue

    elephant_detections = []

    # =================================================
    # FILTER ELEPHANT DETECTIONS & SUPPRESS FALSE POSITIVES
    # =================================================
    if class_ids is not None and len(class_ids) > 0:
        h_frame, w_frame = frame.shape[:2]
        frame_area = float(max(h_frame * w_frame, 1))

        person_boxes = []
        raw_candidates = []

        for class_id, confidence, box in zip(
            class_ids.flatten(),
            confidences.flatten(),
            boxes
        ):
            class_index = int(class_id) - 1

            if class_index < 0:
                continue

            if class_index >= len(class_names):
                continue

            object_name = (
                class_names[class_index]
                .strip()
                .lower()
            )

            if object_name == "person":
                person_boxes.append((box, float(confidence)))
            elif object_name == "elephant" and float(confidence) >= CONFIDENCE_THRESHOLD:
                raw_candidates.append((box, float(confidence)))

        for box, conf in raw_candidates:
            x, y, width, height = map(int, box)
            box_area = float(max(width * height, 1))

            # Suppression Rule 1: Full-frame bounding box artifact.
            # If the candidate covers >= 80% of the entire frame, MobileNet SSD
            # is misattributing room lighting/walls as an elephant. Require >= 0.85 confidence.
            if (box_area / frame_area) >= 0.80 and conf < 0.85:
                continue

            # Suppression Rule 2: Person conflict check.
            # If candidate overlaps heavily (> 45% of its area) with a detected human person
            # and confidence is below 0.80, suppress as a human false positive.
            person_conflict = False
            for p_box, _ in person_boxes:
                px, py, pw, ph = map(int, p_box)
                ix1 = max(x, px)
                iy1 = max(y, py)
                ix2 = min(x + width, px + pw)
                iy2 = min(y + height, py + ph)
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = float((ix2 - ix1) * (iy2 - iy1))
                    if (inter_area / box_area) > 0.45 and conf < 0.80:
                        person_conflict = True
                        break

            if person_conflict:
                continue

            elephant_detections.append({
                "confidence": conf,
                "x": x,
                "y": y,
                "width": width,
                "height": height
            })

    # =================================================
    # COUNT ELEPHANTS
    # =================================================
    elephant_count = len(elephant_detections)
    current_time = time.time()

    if elephant_count > 0:

        confidence_values = []

        # Draw a box around every elephant
        for elephant_number, detection in enumerate(
            elephant_detections,
            start=1
        ):
            confidence = detection["confidence"]
            x = detection["x"]
            y = detection["y"]
            width = detection["width"]
            height = detection["height"]

            confidence_values.append(confidence)

            label = (
                f"Elephant {elephant_number} - "
                f"{confidence * 100:.1f}%"
            )

            cv2.rectangle(
                frame,
                (x, y),
                (x + width, y + height),
                (0, 0, 255),
                3
            )

            cv2.putText(
                frame,
                label,
                (x, max(y - 10, 30)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )

        highest_confidence = max(confidence_values) * 100

        # Display elephant count
        cv2.rectangle(
            frame,
            (10, 10),
            (530, 70),
            (0, 0, 0),
            -1
        )

        cv2.putText(
            frame,
            f"Elephants Detected: {elephant_count}",
            (25, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            3
        )

        # Save image and speak only when a new event begins
        if not elephant_event_active:
            elephant_event_active = True

            now = datetime.now()

            image_name = (
                "elephant_"
                + now.strftime("%Y%m%d_%H%M%S")
                + ".jpg"
            )

            current_event_image = os.path.join(
                IMAGE_FOLDER,
                image_name
            )

            image_saved = cv2.imwrite(
                current_event_image,
                frame
            )

            if image_saved:
                print("Elephant image saved:", current_event_image)
                sync_detection_to_backend(
                    elephant_count,
                    highest_confidence,
                    current_event_image,
                    now.isoformat(timespec="seconds")
                )
            else:
                print("ERROR: Image could not be saved.")
                current_event_image = ""

            speak_elephant_alert(elephant_count)

        # Save one CSV row every second
        if current_time - last_log_time >= LOG_INTERVAL_SECONDS:
            now = datetime.now()

            csv_writer.writerow([
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                now.isoformat(timespec="seconds"),
                "YES",
                elephant_count,
                round(highest_confidence, 2),
                current_event_image
            ])

            csv_file.flush()
            last_log_time = current_time

            sync_detection_to_backend(
                elephant_count,
                highest_confidence,
                current_event_image,
                now.isoformat(timespec="seconds")
            )

            print(
                now.strftime("%H:%M:%S"),
                "- Elephant count:",
                elephant_count
            )

    else:
        # Reset event when no elephant is detected
        elephant_event_active = False
        current_event_image = ""

        cv2.rectangle(
            frame,
            (10, 10),
            (440, 70),
            (0, 0, 0),
            -1
        )

        cv2.putText(
            frame,
            "No Elephant Detected",
            (25, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        # Save zero count once every second
        if current_time - last_log_time >= LOG_INTERVAL_SECONDS:
            now = datetime.now()

            csv_writer.writerow([
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                now.isoformat(timespec="seconds"),
                "NO",
                0,
                0,
                ""
            ])

            csv_file.flush()
            last_log_time = current_time

            print(
                now.strftime("%H:%M:%S"),
                "- Elephant count: 0"
            )

    # =================================================
    # SHOW VIDEO & CAMERA CONTROLS HUD
    # =================================================
    display_frame = frame
    if frame is not None and frame.shape[1] < 640:
        scale = 640.0 / frame.shape[1]
        display_frame = cv2.resize(frame, (640, int(frame.shape[0] * scale)), interpolation=cv2.INTER_LINEAR)

    # Render Camera Info Pill HUD in top-right
    h_d, w_d = display_frame.shape[:2]
    cam_str = get_camera_name(CAMERA_SOURCE)
    cv2.rectangle(display_frame, (w_d - 360, 10), (w_d - 10, 42), (15, 23, 42), -1)
    cv2.rectangle(display_frame, (w_d - 360, 10), (w_d - 10, 42), (6, 182, 212), 1)
    cv2.putText(
        display_frame,
        f"CAM: {cam_str} [Press C/0/1]",
        (w_d - 350, 31),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.44,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    # Show eye-catching switch notification banner for 3 seconds after switching
    if time.time() - last_switch_time < 3.0:
        cv2.rectangle(display_frame, (20, h_d - 85), (w_d - 20, h_d - 20), (15, 23, 42), -1)
        cv2.rectangle(display_frame, (20, h_d - 85), (w_d - 20, h_d - 20), (6, 182, 212), 2)
        cv2.putText(
            display_frame,
            f">>> {switch_banner_text} <<<",
            (40, h_d - 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (6, 182, 212),
            2,
            cv2.LINE_AA
        )
        cv2.putText(
            display_frame,
            "AI ELEPHANT DETECTION ENGINE ACTIVE ON THIS CAMERA",
            (40, h_d - 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

    if not HEADLESS:
        cv2.imshow(
            "Elephant Detection System",
            display_frame
        )

        # Keyboard Camera Switcher:
        # 'Q': Exit
        # 'C' or 'S': Toggle between Laptop (0) and External (1)
        # '0': Select Laptop Webcam
        # '1': Select External HD Webcam
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q")):
            break
        elif key in (ord("c"), ord("C"), ord("s"), ord("S")):
            next_cam = 1 if CAMERA_SOURCE == 0 else 0
            cap = switch_camera_source(next_cam, cap)
        elif key == ord("0"):
            cap = switch_camera_source(0, cap)
        elif key == ord("1"):
            cap = switch_camera_source(1, cap)
    else:
        # Sleep lightly in headless mode to prevent busy-waiting loop
        time.sleep(0.01)

    # Check for external camera switch requests from web dashboard config every ~1 second
    loop_counter += 1
    if loop_counter % 25 == 0:
        try:
            cfg = load_saved_camera_config()
            cfg_src = format_camera_source(cfg.get("camera_source", CAMERA_SOURCE))
            if cfg_src != CAMERA_SOURCE:
                print(f"[CONFIG SYNC] Dashboard requested camera switch to: {cfg_src}")
                cap = switch_camera_source(cfg_src, cap)
        except Exception:
            pass

# =====================================================
# CLOSE PROGRAM
# =====================================================
csv_file.close()
cap.release()
cv2.destroyAllWindows()

print("\nElephant detection stopped.")
print("Dataset saved as:", CSV_FILE)
print("Images saved inside:", IMAGE_FOLDER)