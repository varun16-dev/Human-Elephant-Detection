import cv2
import csv
import os
import time
import threading
from datetime import datetime

import pyttsx3

# =====================================================
# SETTINGS
# =====================================================
CONFIDENCE_THRESHOLD = 0.45
CAMERA_INDEX = 0
LOG_INTERVAL_SECONDS = 1

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
        input("Press Enter to close...")
        raise SystemExit

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
    input("Press Enter to close...")
    raise SystemExit

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
    input("Press Enter to close...")
    raise SystemExit

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
    input("Press Enter to close...")
    raise SystemExit

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