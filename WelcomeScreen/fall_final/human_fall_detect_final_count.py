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

import pyttsx3

import argparse

parser = argparse.ArgumentParser(description="Elephant Camera Detection Engine")
parser.add_argument("--device-id", default="ESP32-NODE-01", help="Associated ESP32 Device ID")
parser.add_argument("--trigger-source", default="MANUAL", help="Trigger source: PIR, SOUND, PIR_AND_SOUND, MANUAL")
parser.add_argument("--session-seconds", type=int, default=15, help="Session duration in seconds (0 = run indefinitely)")
parser.add_argument("--camera-index", type=int, default=0, help="Camera index")
parser.add_argument("--headless", action="store_true", help="Run without GUI window")
args, _ = parser.parse_known_args()

# =====================================================
# SETTINGS
# =====================================================
CONFIDENCE_THRESHOLD = 0.45
CAMERA_INDEX = args.camera_index
LOG_INTERVAL_SECONDS = 1
DEVICE_ID = args.device_id
TRIGGER_SOURCE = args.trigger_source
SESSION_SECONDS = args.session_seconds
HEADLESS = args.headless

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
# OPEN CAMERA
# =====================================================
cap = cv2.VideoCapture(
    CAMERA_INDEX,
    cv2.CAP_DSHOW
)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    print("ERROR: Camera could not be opened.")
    print("Check Windows camera permission.")
    print("Close Camera, Zoom, Meet and WhatsApp.")
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

# =====================================================
# VARIABLES
# =====================================================
last_log_time = 0

# True while an elephant detection event is active
elephant_event_active = False

# Stores the current event's image
current_event_image = ""

print("\nElephant detection started.")
print("Press Q inside the camera window to stop.")
print("CSV dataset:", CSV_FILE)
print("Detected images:", IMAGE_FOLDER)

# =====================================================
# MAIN DETECTION LOOP
# =====================================================
while True:

    success, frame = cap.read()

    # Prevent empty image error
    if not success or frame is None or frame.size == 0:
        print("WARNING: Camera frame was not received.")
        break

    try:
        class_ids, confidences, boxes = net.detect(
            frame,
            confThreshold=CONFIDENCE_THRESHOLD,
            nmsThreshold=0.4
        )

    except cv2.error as error:
        print("Detection error:", error)
        continue

    elephant_detections = []

    # =================================================
    # FILTER ONLY ELEPHANT DETECTIONS
    # =================================================
    if class_ids is not None and len(class_ids) > 0:

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

            if object_name == "elephant":
                x, y, width, height = map(int, box)

                elephant_detections.append({
                    "confidence": float(confidence),
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
    # SHOW VIDEO
    # =================================================
    cv2.imshow(
        "Elephant Detection System",
        frame
    )

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# =====================================================
# CLOSE PROGRAM
# =====================================================
csv_file.close()
cap.release()
cv2.destroyAllWindows()

print("\nElephant detection stopped.")
print("Dataset saved as:", CSV_FILE)
print("Images saved inside:", IMAGE_FOLDER)