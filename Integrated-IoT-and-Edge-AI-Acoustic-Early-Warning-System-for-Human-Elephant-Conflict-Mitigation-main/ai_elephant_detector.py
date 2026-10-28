"""
AI Elephant Detection Engine
Department of AI & ML, Sri Sairam College of Engineering

Reusable, thread-safe computer vision pipeline leveraging SSD MobileNet v3
trained on COCO dataset for real-time elephant detection.
Supports local camera frames, uploaded evidence, and VETRAX Spider Robot frame streams.
"""

import os
import cv2
import time
import threading
import numpy as np
from datetime import datetime

class ElephantDetectionResult:
    """Structured container for AI elephant detection results"""
    def __init__(self, elephant_detected=False, elephant_count=0, highest_confidence=0.0,
                 boxes=None, annotated_frame=None, error=None, inference_time_ms=0.0):
        self.elephant_detected = bool(elephant_detected)
        self.elephant_count = int(elephant_count)
        self.highest_confidence = float(highest_confidence)
        self.boxes = boxes or []
        self.annotated_frame = annotated_frame
        self.error = error
        self.inference_time_ms = round(inference_time_ms, 2)

    def to_dict(self):
        return {
            "elephant_detected": self.elephant_detected,
            "elephant_count": self.elephant_count,
            "highest_confidence": round(self.highest_confidence, 4),
            "confidence": round(self.highest_confidence, 4),
            "highest_confidence_percent": round(self.highest_confidence * 100, 1),
            "boxes": self.boxes,
            "detections": self.boxes,
            "error": self.error,
            "inference_time_ms": self.inference_time_ms
        }

    def __getitem__(self, item):
        d = self.to_dict()
        if item in d:
            return d[item]
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __contains__(self, item):
        return item in self.to_dict() or hasattr(self, item)


class ElephantDetector:
    """
    Thread-safe detector loading SSD MobileNet v3 using OpenCV DNN module.
    """
    def __init__(self, base_search_dir=None):
        self.lock = threading.Lock()
        self.model = None
        self.class_names = []
        self.elephant_class_index = -1
        self.is_loaded = False
        self.load_error = None
        self._init_model(base_search_dir)

    def _find_model_files(self, base_search_dir=None):
        """Locates required model weights, config, and coco dataset files"""
        candidates = []
        if base_search_dir:
            candidates.append(base_search_dir)

        # Common locations in the repository
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.extend([
            os.path.abspath(os.path.join(curr_dir, '..', 'WelcomeScreen', 'fall_final')),
            os.path.abspath(os.path.join(curr_dir, 'model')),
            curr_dir
        ])

        for path in candidates:
            weights = os.path.join(path, "frozen_inference_graph.pb")
            config = os.path.join(path, "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt.txt")
            classes = os.path.join(path, "coco.data")
            if os.path.exists(weights) and os.path.exists(config) and os.path.exists(classes):
                return weights, config, classes

        return None, None, None

    def _init_model(self, base_search_dir=None):
        """Loads and configures the OpenCV DNN DetectionModel"""
        with self.lock:
            weights, config, classes_file = self._find_model_files(base_search_dir)
            if not weights:
                self.load_error = "Model files not found (frozen_inference_graph.pb / config / coco.data)."
                print(f"[AI-DETECTOR] Warning: {self.load_error}")
                self.is_loaded = False
                return

            try:
                # Load class names
                with open(classes_file, "r", encoding="utf-8") as f:
                    self.class_names = [line.strip().lower() for line in f if line.strip()]

                # Find the elephant class index
                try:
                    self.elephant_class_index = self.class_names.index("elephant")
                except ValueError:
                    self.load_error = "'elephant' class not present in coco.data"
                    self.is_loaded = False
                    return

                # Load OpenCV DNN detection model
                net = cv2.dnn_DetectionModel(weights, config)
                net.setInputSize(320, 320)
                net.setInputScale(1.0 / 127.5)
                net.setInputMean((127.5, 127.5, 127.5))
                net.setInputSwapRB(True)

                self.model = net
                self.is_loaded = True
                self.load_error = None
                print(f"[AI-DETECTOR] Model loaded successfully. Elephant class index: {self.elephant_class_index}")

            except Exception as e:
                self.load_error = f"Exception during model initialization: {str(e)}"
                print(f"[AI-DETECTOR] Error: {self.load_error}")
                self.is_loaded = False

    def detect(self, image_input, confidence_threshold=0.65, annotate=True):
        """
        Runs object detection on the input image.
        image_input can be:
        - numpy.ndarray (OpenCV BGR image)
        - bytes / bytearray (encoded JPEG/PNG)
        - str (path to image file)
        """
        start_t = time.time()

        if not self.is_loaded:
            return ElephantDetectionResult(
                error=f"Model not loaded: {self.load_error}",
                inference_time_ms=(time.time() - start_t) * 1000
            )

        # 1. Decode or validate image
        frame = None
        try:
            if isinstance(image_input, np.ndarray):
                frame = image_input.copy()
            elif isinstance(image_input, (bytes, bytearray)):
                np_arr = np.frombuffer(image_input, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            elif isinstance(image_input, str):
                if not os.path.exists(image_input):
                    return ElephantDetectionResult(error=f"File not found: {image_input}")
                frame = cv2.imread(image_input)
            else:
                return ElephantDetectionResult(error="Unsupported image input type.")
        except Exception as e:
            return ElephantDetectionResult(error=f"Failed to decode image: {str(e)}")

        if frame is None or frame.size == 0 or len(frame.shape) < 2:
            return ElephantDetectionResult(error="Empty or corrupt image frame.")

        # 2. Run inference inside thread lock
        with self.lock:
            try:
                eff_threshold = float(confidence_threshold)
                class_ids, confidences, boxes = self.model.detect(
                    frame,
                    confThreshold=min(eff_threshold, 0.40),
                    nmsThreshold=0.4
                )
            except Exception as dnn_err:
                return ElephantDetectionResult(
                    error=f"Inference execution failed: {str(dnn_err)}",
                    inference_time_ms=(time.time() - start_t) * 1000
                )

        # 3. Filter for elephant detections with false-positive suppression
        elephant_boxes = []
        conf_list = []

        if class_ids is not None and len(class_ids) > 0:
            h_frame, w_frame = frame.shape[:2]
            frame_area = float(max(h_frame * w_frame, 1))

            person_boxes = []
            candidates = []

            for class_id, conf, box in zip(class_ids.flatten(), confidences.flatten(), boxes):
                class_idx = int(class_id) - 1  # 1-indexed to 0-indexed
                if 0 <= class_idx < len(self.class_names):
                    cname = self.class_names[class_idx]
                    if cname == "person":
                        person_boxes.append((box, float(conf)))
                    elif cname == "elephant" and float(conf) >= eff_threshold:
                        candidates.append((box, float(conf)))

            for box, conf_val in candidates:
                x, y, w, h = map(int, box)
                box_area = float(max(w * h, 1))

                # Suppression 1: Full-frame bounding box artifact (>80% frame area requires >= 0.85 conf)
                if (box_area / frame_area) >= 0.80 and conf_val < 0.85:
                    continue

                # Suppression 2: Human conflict (>45% overlap with person requires >= 0.80 conf)
                person_conflict = False
                for p_box, _ in person_boxes:
                    px, py, pw, ph = map(int, p_box)
                    ix1, iy1 = max(x, px), max(y, py)
                    ix2, iy2 = min(x + w, px + pw), min(y + h, py + ph)
                    if ix2 > ix1 and iy2 > iy1:
                        inter = float((ix2 - ix1) * (iy2 - iy1))
                        if (inter / box_area) > 0.45 and conf_val < 0.80:
                            person_conflict = True
                            break

                if person_conflict:
                    continue

                elephant_boxes.append({
                    "x": x, "y": y, "width": w, "height": h,
                    "confidence": round(conf_val, 4),
                    "class_name": "elephant"
                })
                conf_list.append(conf_val)

        elephant_count = len(elephant_boxes)
        highest_conf = max(conf_list) if conf_list else 0.0

        # 4. Optional annotation of frame
        annotated_frame = frame
        if annotate and elephant_count > 0:
            for idx, item in enumerate(elephant_boxes, 1):
                x, y, w, h = item["x"], item["y"], item["width"], item["height"]
                c = item["confidence"]
                # Red bounding box for elephant
                cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
                label = f"Elephant #{idx}: {c * 100:.1f}%"
                cv2.putText(annotated_frame, label, (x, max(y - 10, 25)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)

            # Top counter banner
            cv2.rectangle(annotated_frame, (10, 10), (420, 65), (15, 23, 42), -1)
            cv2.rectangle(annotated_frame, (10, 10), (420, 65), (0, 0, 255), 2)
            cv2.putText(annotated_frame, f"ELEPHANTS DETECTED: {elephant_count}",
                        (20, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        inference_ms = (time.time() - start_t) * 1000

        return ElephantDetectionResult(
            elephant_detected=(elephant_count > 0),
            elephant_count=elephant_count,
            highest_confidence=highest_conf,
            boxes=elephant_boxes,
            annotated_frame=annotated_frame,
            inference_time_ms=inference_ms
        )


class DetectionCooldownManager:
    """
    Manages detection debouncing and cooldowns to prevent alert spam
    during continuous sightings.
    """
    def __init__(self, cooldown_seconds=60, confirmation_frames=2):
        self.cooldown_seconds = cooldown_seconds
        self.confirmation_frames = confirmation_frames
        self.lock = threading.Lock()
        self.device_states = {}

    def should_trigger_alert(self, device_id, elephant_detected, confidence=0.0):
        """
        Determines whether a new alert should be triggered for a device.
        Returns (trigger_alert: bool, reason: str)
        """
        now = time.time()
        with self.lock:
            state = self.device_states.get(device_id, {
                "consecutive_frames": 0,
                "last_alert_time": 0.0,
                "is_active_sighting": False
            })

            if not elephant_detected:
                state["consecutive_frames"] = 0
                state["is_active_sighting"] = False
                self.device_states[device_id] = state
                return False, "No elephant detected in frame."

            state["consecutive_frames"] += 1
            elapsed_since_last = now - state["last_alert_time"]

            # Check if confirmation frames threshold reached
            if state["consecutive_frames"] < self.confirmation_frames:
                self.device_states[device_id] = state
                return False, f"Awaiting confirmation frames ({state['consecutive_frames']}/{self.confirmation_frames})"

            # Check cooldown
            if state["is_active_sighting"] and elapsed_since_last < self.cooldown_seconds:
                rem = round(self.cooldown_seconds - elapsed_since_last, 1)
                self.device_states[device_id] = state
                return False, f"Cooldown active ({rem}s remaining for continuous sighting)."

            # Trigger alert
            state["last_alert_time"] = now
            state["is_active_sighting"] = True
            self.device_states[device_id] = state
            return True, "Elephant sighting confirmed and cooldown elapsed."

    def should_alert(self, device_id, elephant_detected=True, confidence=0.0):
        """Convenience alias for should_trigger_alert"""
        return self.should_trigger_alert(device_id, elephant_detected, confidence)

    def reset(self, device_id=None):
        """Resets cooldown state for a specific device or all devices"""
        with self.lock:
            if device_id:
                self.device_states.pop(device_id, None)
            else:
                self.device_states.clear()


# Global Singleton Getter
_GLOBAL_DETECTOR = None
_GLOBAL_COOLDOWN = None

def get_elephant_detector():
    global _GLOBAL_DETECTOR
    if _GLOBAL_DETECTOR is None:
        _GLOBAL_DETECTOR = ElephantDetector()
    return _GLOBAL_DETECTOR

def get_cooldown_manager():
    global _GLOBAL_COOLDOWN
    if _GLOBAL_COOLDOWN is None:
        _GLOBAL_COOLDOWN = DetectionCooldownManager(cooldown_seconds=60, confirmation_frames=2)
    return _GLOBAL_COOLDOWN
