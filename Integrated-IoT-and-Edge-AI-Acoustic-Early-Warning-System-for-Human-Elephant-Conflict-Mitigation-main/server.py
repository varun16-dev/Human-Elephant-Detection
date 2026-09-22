"""
Integrated IoT and Edge-AI Acoustic Early Warning System
Major Project Phase II - Server & REST API Engine
Department of AI & ML, Sri Sairam College of Engineering
"""

from flask import Flask, render_template, jsonify, request, send_from_directory, Response
import random
import time
import math
import os
import threading
import csv
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import alert services
from notification_service import get_notification_service
from push_service import get_push_service

base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, 
            static_folder=os.path.join(base_dir, 'static'),
            template_folder=os.path.join(base_dir, 'templates'))

# Default Standby State for Bannerghatta National Park Fringe Village Nodes (All Clear / Safe)
NODES_DATA = [
    {
        "id": "ESP32-NODE-01",
        "name": "Node 1 - Buthanahalli (Bannerghatta NP)",
        "location": "Buthanahalli, Bannerghatta NP Fringe, KA",
        "lat": 12.8224,
        "lng": 77.5770,
        "pir": False,
        "vibration": 0.12, # m/s^2
        "acoustic_db": 34.5,
        "sound_class": "Ambient Forest Sound",
        "confidence": 99.2,
        "status": "SAFE",
        "battery": 95,
        "solar_v": 14.1,
        "lora_rssi": -72,
        "wifi_status": "Connected",
        "cache_count": 0,
        "last_seen": "Just now"
    },
    {
        "id": "ESP32-NODE-02",
        "name": "Node 2 - Begihalli (Anekal Taluk)",
        "location": "Begihalli, Anekal Taluk, KA",
        "lat": 12.79213,
        "lng": 77.61622,
        "pir": False,
        "vibration": 0.18,
        "acoustic_db": 36.1,
        "sound_class": "Ambient Forest Sound",
        "confidence": 98.5,
        "status": "SAFE",
        "battery": 94,
        "solar_v": 14.1,
        "lora_rssi": -65,
        "wifi_status": "Connected",
        "cache_count": 0,
        "last_seen": "2s ago"
    },
    {
        "id": "ESP32-NODE-03",
        "name": "Node 3 - Bettamugilalam (Hosur-Denkanikottai)",
        "location": "Bettamugilalam, Krishnagiri, TN",
        "lat": 12.5195,
        "lng": 77.8200,
        "pir": False,
        "vibration": 0.10,
        "acoustic_db": 32.8,
        "sound_class": "Ambient Forest Sound",
        "confidence": 99.1,
        "status": "SAFE",
        "battery": 92,
        "solar_v": 13.9,
        "lora_rssi": -81,
        "wifi_status": "LoRa Mesh",
        "cache_count": 0,
        "last_seen": "5s ago"
    },
    {
        "id": "ESP32-NODE-04",
        "name": "Node 4 - Ragihalli Village",
        "location": "Ragihalli, Bengaluru Urban, KA",
        "lat": 12.7180,
        "lng": 77.5840,
        "pir": False,
        "vibration": 0.15,
        "acoustic_db": 38.0,
        "sound_class": "Wind Noise",
        "confidence": 99.1,
        "status": "SAFE",
        "battery": 91,
        "solar_v": 14.0,
        "lora_rssi": -69,
        "wifi_status": "Connected",
        "cache_count": 0,
        "last_seen": "1s ago"
    },
    {
        "id": "ESP32-NODE-05",
        "name": "Node 5 - Thammanayakanahalli (Anekal Area)",
        "location": "Thammanayakanahalli, Bengaluru Urban, KA",
        "lat": 12.6100,
        "lng": 77.7100,
        "pir": False,
        "vibration": 0.09,
        "acoustic_db": 31.4,
        "sound_class": "Ambient Forest Sound",
        "confidence": 99.5,
        "status": "SAFE",
        "battery": 96,
        "solar_v": 14.2,
        "lora_rssi": -78,
        "wifi_status": "Connected",
        "cache_count": 0,
        "last_seen": "3s ago"
    },
    {
        "id": "ESP32-NODE-06",
        "name": "Node 6 - Kadusivanapalli (Jawalagiri Area)",
        "location": "Kadusivanapalli, Krishnagiri, TN",
        "lat": 12.5400,
        "lng": 77.7800,
        "pir": False,
        "vibration": 0.08,
        "acoustic_db": 35.2,
        "sound_class": "Rain/Foliage",
        "confidence": 97.4,
        "status": "SAFE",
        "battery": 96,
        "solar_v": 14.2,
        "lora_rssi": -58,
        "wifi_status": "Connected",
        "cache_count": 0,
        "last_seen": "Just now"
    }
]

DETERRENT_STATE = {
    "bio_acoustic_active": False,
    "strobe_light_active": False,
    "siren_active": False,
    "sms_alert_dispatched": False,
    "last_trigger_time": "None",
    "trigger_node": "None"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    active_alerts = [n for n in NODES_DATA if n['status'] == 'ALERT']
    warnings = [n for n in NODES_DATA if n['status'] == 'WARNING']
    overall_status = "CRITICAL_ALERT" if active_alerts else ("WARNING" if warnings else "NORMAL")
    
    return jsonify({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_status": overall_status,
        "total_nodes": len(NODES_DATA),
        "nodes_online": 6,
        "active_alerts_count": len(active_alerts),
        "warning_count": len(warnings),
        "lora_mesh_health": "100%",
        "cloud_sync": "Active (MakeAcademy Cloud)",
        "solar_power_avg": "14.05V",
        "battery_avg": "94.0%",
        "herd_info": None, # Default: No threat detected
        "deterrent_status": DETERRENT_STATE
    })

@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    # Return actual node data without simulation - only real ESP32 telemetry
    # Process current node data for history (only if ESP32 is connected)
    process_node_data_for_history()
    
    # Check connection status before returning
    check_esp32_connection()
            
    return jsonify(NODES_DATA)

@app.route('/api/simulate-node-alert', methods=['POST'])
def simulate_node_alert():
    data = request.json or {}
    node_id = data.get('node_id')
    reset = data.get('reset', False)
    
    if reset:
        for node in NODES_DATA:
            node['status'] = 'SAFE'
            node['pir'] = False
            node['vibration'] = 0.12
            node['acoustic_db'] = 34.0
            node['sound_class'] = 'Ambient Forest Sound'
            node['confidence'] = 99.1
        return jsonify({"status": "reset", "message": "All nodes restored to SAFE / Standby state."})
        
    target = None
    for node in NODES_DATA:
        if node['id'] == node_id:
            node['status'] = 'ALERT'
            node['pir'] = True
            node['vibration'] = 1.85
            node['acoustic_db'] = 88.5
            node['sound_class'] = 'Elephant Trumpet'
            node['confidence'] = 96.4
            target = node
        else:
            node['status'] = 'SAFE'
            node['pir'] = False
            node['vibration'] = 0.10
            node['acoustic_db'] = 32.0
            node['sound_class'] = 'Ambient Forest Sound'
            node['confidence'] = 99.0
            
    if target:
        return jsonify({"status": "alert_triggered", "node": target})
    return jsonify({"status": "error", "message": "Node ID not found"}), 404

@app.route('/api/node-event', methods=['POST'])
def handle_node_event():
    """Hardware ESP32 HTTP POST Telemetry Ingestion Endpoint"""
    global ESP32_LAST_SEEN, ESP32_CONNECTED
    
    data = request.json or {}
    node_id = data.get('node_id')
    
    # Update ESP32 connection status - real data received
    ESP32_LAST_SEEN = datetime.now()
    ESP32_CONNECTED = True
    
    print(f"[ESP32] Real telemetry received from {node_id} at {ESP32_LAST_SEEN.strftime('%H:%M:%S')}")
    
    for node in NODES_DATA:
        if node['id'] == node_id:
            node['pir'] = data.get('pir', node['pir'])
            node['vibration'] = data.get('vibration', node['vibration'])
            node['acoustic_db'] = data.get('acoustic_db', node['acoustic_db'])
            node['sound_class'] = data.get('sound_class', node['sound_class'])
            node['confidence'] = data.get('confidence', node['confidence'])
            if 'Elephant' in node['sound_class'] or node['pir']:
                node['status'] = 'ALERT'
            else:
                node['status'] = 'SAFE'
            return jsonify({"status": "accepted", "node": node})
            
    return jsonify({"status": "error", "message": "Node ID not found"}), 404

@app.route('/api/esp32/data', methods=['POST'])
def handle_esp32_data():
    """Hardware ESP32 HTTP POST Telemetry Ingestion Endpoint - matches ESP32 client"""
    global ESP32_LAST_SEEN, ESP32_CONNECTED
    
    data = request.json or {}
    device_id = data.get('deviceId')
    
    # Update ESP32 connection status - real data received
    ESP32_LAST_SEEN = datetime.now()
    ESP32_CONNECTED = True
    
    print(f"[ESP32] Real telemetry received from {device_id} at {ESP32_LAST_SEEN.strftime('%H:%M:%S')}")
    print(f"[ESP32] Data: PIR={data.get('pir')}, Sound={data.get('sound')}, GPS Fix={data.get('gpsFix')}, Lat={data.get('latitude')}, Lon={data.get('longitude')}")
    
    # Use device_id directly as node_id (ESP32 now sends ESP32-NODE-01)
    node_id = device_id
    
    for node in NODES_DATA:
        if node['id'] == node_id:
            # Convert ESP32 boolean to server format
            node['pir'] = data.get('pir', False)
            # Map sound detection to acoustic_db (sound=true = high dB, sound=false = ambient)
            node['acoustic_db'] = 85.0 if data.get('sound', False) else 35.0
            # Update sound class based on detection
            if data.get('sound', False):
                node['sound_class'] = 'Elephant Trumpet' if data.get('pir', False) else 'Ambient Forest Sound'
            else:
                node['sound_class'] = 'Ambient Forest Sound'
            node['confidence'] = 95.0 if (data.get('pir', False) or data.get('sound', False)) else 99.0
            
            # Update GPS coordinates if GPS has fix
            if data.get('gpsFix', False) and data.get('latitude') and data.get('longitude'):
                new_lat = float(data.get('latitude'))
                new_lng = float(data.get('longitude'))
                
                # Only update if coordinates changed significantly (more than 0.0001 degrees ~ 11 meters)
                if abs(new_lat - node['lat']) > 0.0001 or abs(new_lng - node['lng']) > 0.0001:
                    node['lat'] = new_lat
                    node['lng'] = new_lng
                    # Dynamic reverse geocoding for location name
                    node['location'] = reverse_geocode_coordinates(node['lat'], node['lng'])
                    # Update node name dynamically for Node 1
                    if node['id'] == 'ESP32-NODE-01':
                        node['name'] = f"Node 1 - {node['location']}"
                    print(f"[ESP32] Updated GPS coordinates: {node['lat']}, {node['lng']} -> {node['location']}")
                else:
                    # Small coordinate change, don't trigger reverse geocoding
                    node['lat'] = new_lat
                    node['lng'] = new_lng
                    print(f"[ESP32] Minor GPS update: {node['lat']}, {node['lng']} (location unchanged)")
                    
            elif not data.get('gpsFix', False):
                # GPS has no fix - preserve last valid coordinates but update location name
                node['location'] = "GPS: No Fix"
                print(f"[ESP32] GPS no fix - preserving last valid coordinates: {node['lat']}, {node['lng']}")
            
            # Update status based on detections
            if data.get('pir', False) or data.get('sound', False):
                node['status'] = 'ALERT'
            else:
                node['status'] = 'SAFE'
            
            # Update last seen time
            node['last_seen'] = 'Just now'
            
            print(f"[ESP32] Updated node {node_id}: PIR={node['pir']}, Status={node['status']}")
            return jsonify({"status": "accepted", "node": node})
    
    # If node not found, still return success to ESP32
    print(f"[ESP32] Node {node_id} not found in NODES_DATA, but accepting data")
    return jsonify({"status": "accepted", "message": "Data received"})

@app.route('/api/edge-ai/predict', methods=['POST'])
def predict_audio():
    data = request.json or {}
    sample_type = data.get('sample_type', 'wind')
    
    if sample_type == 'trumpet':
        res = {
            "class": "Elephant Trumpet",
            "confidence": round(96.4 + random.uniform(-1, 2), 1),
            "threat_score": 98,
            "mfcc": [14.2, -8.5, 6.2, 12.1, -4.3, 8.7, -2.1, 5.4, -1.8, 4.2, 2.1, -0.9],
            "frequency_peak_hz": 1450,
            "energy_db": 88.5,
            "pir_confirmation": True,
            "vibration_confirmed": True,
            "fused_decision": "CONFIRMED ELEPHANT DETECTED"
        }
    elif sample_type == 'rumble':
        res = {
            "class": "Elephant Infrasonic Rumble",
            "confidence": round(91.8 + random.uniform(-1, 2), 1),
            "threat_score": 85,
            "mfcc": [18.5, 12.1, -3.2, 4.5, -9.1, 2.2, -5.4, 1.2, 0.8, -2.1, 1.4, -0.5],
            "frequency_peak_hz": 24,
            "energy_db": 74.2,
            "pir_confirmation": True,
            "vibration_confirmed": True,
            "fused_decision": "CONFIRMED ELEPHANT DETECTED"
        }
    elif sample_type == 'wind':
        res = {
            "class": "Environmental Wind Noise",
            "confidence": 98.2,
            "threat_score": 5,
            "mfcc": [-5.2, 2.1, -1.5, 0.8, -0.4, 1.1, -0.2, 0.5, -0.1, 0.3, 0.1, -0.2],
            "frequency_peak_hz": 120,
            "energy_db": 34.0,
            "pir_confirmation": False,
            "vibration_confirmed": False,
            "fused_decision": "NON-ELEPHANT SOUND - CLEAR"
        }
    else: # Vehicle engine
        res = {
            "class": "Vehicle Motor Noise",
            "confidence": 94.6,
            "threat_score": 12,
            "mfcc": [8.1, -12.4, 2.3, -4.1, 1.8, -2.2, 0.9, -1.1, 0.4, -0.8, 0.2, -0.3],
            "frequency_peak_hz": 420,
            "energy_db": 58.0,
            "pir_confirmation": False,
            "vibration_confirmed": False,
            "fused_decision": "NON-ELEPHANT SOUND - CLEAR"
        }
        
    return jsonify(res)

@app.route('/api/deterrent/trigger', methods=['POST'])
def trigger_deterrent():
    data = request.json or {}
    device = data.get('device')
    action = data.get('action')
    
    if device == 'bio_acoustic':
        DETERRENT_STATE['bio_acoustic_active'] = not DETERRENT_STATE['bio_acoustic_active'] if action == 'toggle' else (action == 'on')
    elif device == 'strobe_light':
        DETERRENT_STATE['strobe_light_active'] = not DETERRENT_STATE['strobe_light_active'] if action == 'toggle' else (action == 'on')
    elif device == 'siren':
        DETERRENT_STATE['siren_active'] = not DETERRENT_STATE['siren_active'] if action == 'toggle' else (action == 'on')
    elif device == 'sms_broadcast':
        DETERRENT_STATE['sms_alert_dispatched'] = True
        
    DETERRENT_STATE['last_trigger_time'] = time.strftime("%H:%M:%S")
    return jsonify({
        "status": "success",
        "message": f"{device} set to {action}",
        "deterrent_state": DETERRENT_STATE
    })

@app.route('/api/dss/recommendations', methods=['GET'])
def get_dss():
    return jsonify({
        "predicted_conflict_time": "None (System Standby)",
        "target_vulnerable_village": "None - Boundary Secure",
        "recommended_actions": [
            {
                "priority": "LOW",
                "action": "All 6 ESP32 field nodes online and operating normally",
                "status": "ACTIVE"
            },
            {
                "priority": "LOW",
                "action": "Solar battery levels optimal (Avg 14.05V)",
                "status": "HEALTHY"
            },
            {
                "priority": "LOW",
                "action": "LoRa Mesh communication signal strength stable across Anekal sector",
                "status": "CONNECTED"
            }
        ]
    })

# ==============================================================================
# NEW CAMERA DETECTION INTEGRATION
# ==============================================================================
import csv
import cv2

# Global camera for live streaming
camera_stream = None
camera_lock = threading.Lock()

def get_camera_stream():
    global camera_stream
    with camera_lock:
        if camera_stream is None or not camera_stream.isOpened():
            camera_stream = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            camera_stream.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera_stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return camera_stream

def release_camera():
    global camera_stream
    with camera_lock:
        if camera_stream is not None:
            camera_stream.release()
            camera_stream = None

@app.route('/api/camera/stream')
def camera_stream_route():
    def generate():
        cap = get_camera_stream()
        try:
            while True:
                success, frame = cap.read()
                if not success:
                    break
                
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        finally:
            pass
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/camera/status', methods=['GET'])
def get_camera_status():
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    
    # Check if CSV exists
    if not os.path.exists(csv_path):
        return jsonify({
            "camera_status": "OFFLINE",
            "detection_status": "CSV unavailable",
            "elephant_count": 0,
            "confidence": "0.0%",
            "last_detection_time": "N/A",
            "latest_detection_image": "N/A"
        })
        
    # Check if file has been modified recently (camera is online if modified in last 10 seconds)
    try:
        mtime = os.path.getmtime(csv_path)
        time_diff = time.time() - mtime
        camera_online = (time_diff <= 10.0)
    except Exception:
        camera_online = False
        
    camera_status_str = "CONNECTED" if camera_online else "OFFLINE"
    
    # Read the latest record (last line) from the CSV
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if len(lines) <= 1:
            # File exists but empty or only has header
            return jsonify({
                "camera_status": camera_status_str,
                "detection_status": "No detection history",
                "elephant_count": 0,
                "confidence": "0.0%",
                "last_detection_time": "N/A",
                "latest_detection_image": "N/A"
            })
            
        # Parse the last line
        reader = csv.reader([lines[-1].strip()])
        last_row = next(reader)
        
        # Determine format based on length
        if len(last_row) >= 6:
            date_val = last_row[0]
            time_val = last_row[1]
            detected_val = last_row[3]
            count_val = int(last_row[4]) if last_row[4].isdigit() else 0
            try:
                conf_val = float(last_row[5])
            except ValueError:
                conf_val = 0.0
                
            image_val = ""
            # CSV has 8 columns: Date, Time, Timestamp, Elephant_Detected, Number_of_Elephants, Highest_Confidence_Percent, Possible_Fall_Count, Detection_Duration_Seconds
            # No image column in current CSV format - images are stored separately in detected_elephants/ folder
            
            # Always try to get the latest image from detected_elephants folder if any exist
            image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
            image_timestamp = None
            if os.path.exists(image_dir):
                try:
                    files = os.listdir(image_dir)
                    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                    if images:
                        # Sort by modification time, get the most recent
                        images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
                        image_val = images[0]
                        image_timestamp = os.path.getmtime(os.path.join(image_dir, image_val))
                except Exception:
                    pass
            
            # If we have a recent image but CSV shows NO, check if there's a YES detection within 5 seconds of the image
            if image_val and (detected_val == "NO" or count_val == 0):
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        header = next(reader, None)
                        for row in reader:
                            if len(row) >= 6:
                                row_detected = row[3]
                                row_count = int(row[4]) if row[4].isdigit() else 0
                                row_timestamp_str = row[2]
                                try:
                                    row_time = datetime.fromisoformat(row_timestamp_str).timestamp()
                                    # If this detection is within 5 seconds of the image time and is YES, use it
                                    if image_timestamp and abs(row_time - image_timestamp) < 5 and row_detected == "YES":
                                        detected_val = row_detected
                                        count_val = row_count
                                        try:
                                            conf_val = float(row[5])
                                        except ValueError:
                                            conf_val = 0.0
                                        break
                                except:
                                    continue
                except Exception:
                    pass
                
            det_status = "🐘 ELEPHANT DETECTED" if (detected_val == "YES" or count_val > 0) else "SAFE (NO ELEPHANT)"
            if not camera_online:
                det_status = "OFFLINE"
                
            return jsonify({
                "camera_status": camera_status_str,
                "detection_status": det_status,
                "elephant_count": count_val,
                "confidence": f"{conf_val:.1f}%",
                "last_detection_time": f"{date_val} {time_val}",
                "latest_detection_image": image_val if image_val else "N/A"
            })
            
    except Exception as e:
        return jsonify({
            "camera_status": camera_status_str,
            "detection_status": f"Error: {str(e)}",
            "elephant_count": 0,
            "confidence": "0.0%",
            "last_detection_time": "N/A",
            "latest_detection_image": "N/A"
        })
        
    return jsonify({
        "camera_status": camera_status_str,
        "detection_status": "No detection history",
        "elephant_count": 0,
        "confidence": "0.0%",
        "last_detection_time": "N/A",
        "latest_detection_image": "N/A"
    })

@app.route('/api/detections', methods=['GET'])
def get_detections():
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    
    if not os.path.exists(csv_path):
        return jsonify([])
        
    detections = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return jsonify([])
                
            for row in reader:
                if len(row) < 6:
                    continue
                
                date_val = row[0]
                time_val = row[1]
                timestamp_val = row[2]
                detected_val = row[3]
                count_val = int(row[4]) if row[4].isdigit() else 0
                try:
                    conf_val = float(row[5])
                except ValueError:
                    conf_val = 0.0
                    
                # CSV has 8 columns: Date, Time, Timestamp, Elephant_Detected, Number_of_Elephants, Highest_Confidence_Percent, Possible_Fall_Count, Detection_Duration_Seconds
                # No image column in current CSV format - images are stored separately in detected_elephants/ folder
                image_val = ""
                    
                detections.append({
                    "date": date_val,
                    "time": time_val,
                    "timestamp": timestamp_val,
                    "elephant_detected": detected_val,
                    "elephant_count": count_val,
                    "confidence": conf_val,
                    "saved_image": image_val
                })
                
        # Sort latest detections first
        detections.reverse()
        return jsonify(detections)
    except Exception:
        return jsonify([])

@app.route('/api/elephant-detection/confirmed', methods=['GET'])
def get_confirmed_elephant_detection():
    """Get the latest confirmed elephant detection for popup display.
    Only returns a detection if it occurred within the last 30 seconds
    (i.e. a FRESH detection, not a historical one from the CSV).
    """
    RECENCY_WINDOW_SECONDS = 30  # only trigger popup for detections within this window

    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))

    if not os.path.exists(csv_path):
        return jsonify({"confirmed": False, "detection": None})

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return jsonify({"confirmed": False, "detection": None})

            rows = list(reader)
            if not rows:
                return jsonify({"confirmed": False, "detection": None})

        # Search backwards for the most recent confirmed detection
        latest_confirmed = None
        for row in reversed(rows):
            if len(row) < 6:
                continue
            detected_val = row[3]
            count_val = int(row[4]) if row[4].isdigit() else 0
            if detected_val == "YES" and count_val > 0:
                latest_confirmed = row
                break

        if not latest_confirmed:
            return jsonify({"confirmed": False, "detection": None})

        # --- RECENCY CHECK ---
        # Parse the ISO timestamp (column 2) and compare to now
        timestamp_val = latest_confirmed[2]
        try:
            detection_dt = datetime.fromisoformat(timestamp_val)
            age_seconds = (datetime.now() - detection_dt).total_seconds()
        except Exception:
            # If timestamp is unparseable, fall back to CSV file mtime
            age_seconds = time.time() - os.path.getmtime(csv_path)

        if age_seconds > RECENCY_WINDOW_SECONDS:
            # Detection is old — do NOT trigger popup
            return jsonify({"confirmed": False, "detection": None})

        # Detection is fresh — build and return it
        date_val  = latest_confirmed[0]
        time_val  = latest_confirmed[1]
        count_val = int(latest_confirmed[4]) if latest_confirmed[4].isdigit() else 0
        try:
            conf_val = float(latest_confirmed[5])
        except ValueError:
            conf_val = 0.0

        image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
        image_val = ""
        if os.path.exists(image_dir):
            try:
                files  = os.listdir(image_dir)
                images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if images:
                    images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
                    image_val = images[0]
            except Exception:
                pass

        # Get current ESP32 sensor data
        current_pir = None
        current_sound = None
        if ESP32_CONNECTED and NODES_DATA:
            node = NODES_DATA[0]
            current_pir = 1.0 if node.get('pir', False) else 0.0
            current_sound = min(node.get('acoustic_db', 30) / 100.0, 1.0)
            print(f"[ESP32] Elephant detection: Including sensor data - PIR={current_pir}, Sound={current_sound}")
        else:
            print("[ESP32] Elephant detection: ESP32 offline, sensor data unavailable")

        detection = {
            "id":         f"{timestamp_val}_{count_val}",
            "timestamp":  timestamp_val,
            "count":      count_val,
            "confidence": conf_val,
            "image":      image_val,
            "date":       date_val,
            "time":       time_val,
            "age_seconds": round(age_seconds, 1),
            "pir":        current_pir,
            "sound":      current_sound
        }

        return jsonify({"confirmed": True, "detection": detection})

    except Exception as e:
        print(f"Error reading confirmed detection: {e}")
        return jsonify({"confirmed": False, "detection": None})

@app.route('/api/elephant-detection/test-popup', methods=['POST'])
def test_elephant_popup():
    """Test endpoint to simulate an elephant detection for popup testing"""
    try:
        test_detection = {
            "id": f"test_{datetime.now().isoformat()}",
            "timestamp": datetime.now().isoformat(),
            "count": 2,
            "confidence": 94.7,
            "image": "elephant_20260919_211446.jpg",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S")
        }
        return jsonify({"confirmed": True, "detection": test_detection})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/elephant-detection/real', methods=['GET'])
def get_real_elephant_detection():
    """Get the latest REAL elephant detection from the detection dataset"""
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    
    if not os.path.exists(csv_path):
        return jsonify({"confirmed": False, "detection": None})
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return jsonify({"confirmed": False, "detection": None})
            
            # Get all rows
            rows = list(reader)
            if not rows:
                return jsonify({"confirmed": False, "detection": None})
            
            # Find the most recent confirmed detection
            latest_confirmed = None
            for row in reversed(rows):
                if len(row) < 6:
                    continue
                
                detected_val = row[3]
                count_val = int(row[4]) if row[4].isdigit() else 0
                
                if detected_val == "YES" and count_val > 0:
                    latest_confirmed = row
                    break
            
            if not latest_confirmed:
                return jsonify({"confirmed": False, "detection": None})
            
            date_val = latest_confirmed[0]
            time_val = latest_confirmed[1]
            timestamp_val = latest_confirmed[2]
            count_val = int(latest_confirmed[4]) if latest_confirmed[4].isdigit() else 0
            try:
                conf_val = float(latest_confirmed[5])
            except ValueError:
                conf_val = 0.0
            
            # Try to get the corresponding image
            image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
            image_val = ""
            if os.path.exists(image_dir):
                try:
                    files = os.listdir(image_dir)
                    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                    if images:
                        # Sort by modification time, get the most recent
                        images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
                        image_val = images[0]
                except Exception:
                    pass
            
            detection = {
                "id": f"{timestamp_val}_{count_val}",
                "timestamp": timestamp_val,
                "count": count_val,
                "confidence": conf_val,
                "image": image_val,
                "date": date_val,
                "time": time_val
            }
            
            return jsonify({"confirmed": True, "detection": detection})
                
    except Exception as e:
        print(f"Error reading confirmed detection: {e}")
        return jsonify({"confirmed": False, "detection": None})

@app.route('/api/detections/download', methods=['GET'])
def download_csv():
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    if not os.path.exists(csv_path):
        return "CSV file not found", 404
    directory = os.path.dirname(csv_path)
    filename = os.path.basename(csv_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/detection-images/<filename>')
def get_detection_image(filename):
    image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
    return send_from_directory(image_dir, filename)

@app.route('/service-worker.js')
def get_service_worker():
    return send_from_directory(base_dir, 'service-worker.js')

@app.route('/api/detection-images', methods=['GET'])
def list_detection_images():
    image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
    if not os.path.exists(image_dir):
        return jsonify([])
    try:
        files = os.listdir(image_dir)
        images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
        return jsonify(images)
    except Exception:
        return jsonify([])


# ==============================================================================
# ALERT SYSTEM API ENDPOINTS
# ==============================================================================

@app.route('/api/alerts/history', methods=['GET'])
def get_alerts_history():
    """Get alert history"""
    try:
        service = get_notification_service()
        limit = request.args.get('limit', type=int)
        history = service.get_alert_history(limit)
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/status', methods=['GET'])
def get_alert_status():
    """Get current alert state"""
    try:
        service = get_notification_service()
        status = service.get_current_state()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/process', methods=['POST'])
def process_alert_detection():
    """Process a detection through the confirmation layer"""
    try:
        data = request.json
        elephant_count = data.get('elephant_count', 0)
        confidence = data.get('confidence', 0)
        image_path = data.get('image_path', '')
        csv_row_data = data.get('csv_row_data', {})
        
        service = get_notification_service()
        alert_event = service.process_detection(
            elephant_count, confidence, image_path, csv_row_data
        )
        
        if alert_event:
            # Trigger web push notifications
            push_service = get_push_service()
            
            # Send web push to forest officers
            if push_service.is_configured():
                push_result = push_service.send_elephant_alert(alert_event, role="FOREST_OFFICER")
                service.update_delivery_status(
                    alert_event['alert_id'], 'web_push', 'forest_officers',
                    'sent' if push_result['success'] else 'failed'
                )
            
            # Send web push to villagers
            if push_service.is_configured():
                push_result = push_service.send_elephant_alert(alert_event, role="VILLAGER")
                service.update_delivery_status(
                    alert_event['alert_id'], 'web_push', 'villagers',
                    'sent' if push_result['success'] else 'failed'
                )
            
            return jsonify({"success": True, "alert": alert_event})
        else:
            return jsonify({"success": False, "message": "No alert created"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/update-delivery', methods=['POST'])
def update_alert_delivery():
    """Update delivery status for an alert"""
    try:
        data = request.json
        alert_id = data.get('alert_id')
        channel = data.get('channel')
        role = data.get('role')
        status = data.get('status')
        
        service = get_notification_service()
        success = service.update_delivery_status(alert_id, channel, role, status)
        
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/reset-cooldown', methods=['POST'])
def reset_alert_cooldown():
    """Reset alert cooldown (for testing)"""
    try:
        service = get_notification_service()
        service.reset_cooldown()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==============================================================================
# WEB PUSH API ENDPOINTS
# ==============================================================================

@app.route('/api/push/status', methods=['GET'])
def get_push_status():
    """Get push service status"""
    try:
        service = get_push_service()
        return jsonify({
            "configured": service.is_configured(),
            "vapid_public_key": service.get_vapid_public_key()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/vapid-key', methods=['GET'])
def get_vapid_key():
    """Get VAPID public key for push subscription"""
    try:
        service = get_push_service()
        public_key = service.get_vapid_public_key()
        print(f"VAPID public key length: {len(public_key)}")
        print(f"VAPID public key: {public_key}")
        return jsonify({"vapid_public_key": public_key})
    except Exception as e:
        print(f"Error getting VAPID key: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    """Subscribe to push notifications"""
    try:
        data = request.json
        subscription = data.get('subscription')
        if not isinstance(subscription, dict):
            return jsonify({"error": "A Push subscription object is required"}), 400
        user_role = data.get('user_role', 'VILLAGER')
        user_name = data.get('user_name', 'Unknown')
        
        service = get_push_service()
        subscription_id = service.add_subscription(subscription, user_role, user_name)
        
        return jsonify({"success": True, "subscription_id": subscription_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/unsubscribe', methods=['POST'])
def unsubscribe_push():
    """Unsubscribe from push notifications"""
    try:
        data = request.json
        subscription = data.get('subscription')
        
        service = get_push_service()
        # Find subscription by endpoint
        endpoint = subscription.get('endpoint')
        subscriptions = service._load_subscriptions()
        
        for sub in subscriptions:
            if sub.get('endpoint') == endpoint:
                service.remove_subscription(sub['id'])
                return jsonify({"success": True})
        
        return jsonify({"success": False, "error": "Subscription not found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/test', methods=['POST'])
def test_push_notification():
    """Send a test push notification"""
    try:
        data = request.json
        role = data.get('role')
        
        test_alert = {
            "alert_id": "test_alert",
            "alert_type": "TEST",
            "elephant_count": 0,
            "confidence": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        service = get_push_service()
        
        # If no role specified or role doesn't match any subscriptions, send to all
        if not role:
            result = service.send_elephant_alert(test_alert, role=None)
        else:
            # Check if there are subscriptions for the requested role
            subscriptions = service.get_subscriptions(role=role, enabled_only=True)
            if not subscriptions:
                # Fallback to all subscriptions if no specific role subscriptions exist
                print(f"No subscriptions found for role {role}, sending to all active subscriptions")
                result = service.send_elephant_alert(test_alert, role=None)
            else:
                result = service.send_elephant_alert(test_alert, role=role)
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in test push notification: {e}")
        return jsonify({"error": str(e)}), 500

# ==============================================================================
# Sensor Monitoring API Endpoints
# ==============================================================================

# In-memory sensor history storage (in production, use a database)
SENSOR_HISTORY = []
MAX_HISTORY_POINTS = 1000

# ESP32 Connection Tracking
ESP32_LAST_SEEN = None
ESP32_TIMEOUT_SECONDS = 30  # Consider ESP32 offline if no data for 30 seconds
ESP32_CONNECTED = False

# Reverse Geocoding Cache and Rate Limiting
GEOCODE_CACHE = {}
GEOCODE_LAST_REQUEST_TIME = 0
GEOCODE_MIN_INTERVAL = 5  # Minimum seconds between reverse geocoding requests

# Initialize connection tracking on startup
print("[ESP32] Connection tracking initialized - waiting for real ESP32 telemetry")

def add_sensor_reading(pir_value, sound_value):
    """Add a sensor reading to history"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reading = {
        "timestamp": timestamp,
        "pir": pir_value,
        "sound": sound_value
    }
    SENSOR_HISTORY.append(reading)
    # Keep only the last MAX_HISTORY_POINTS
    if len(SENSOR_HISTORY) > MAX_HISTORY_POINTS:
        SENSOR_HISTORY.pop(0)

# Enhanced sensor reading function that processes real node data
def process_node_data_for_history():
    """Process current node data and add to history - ONLY real ESP32 data"""
    global ESP32_CONNECTED
    
    # Only process data if ESP32 is actually connected and we have recent data
    if ESP32_CONNECTED and NODES_DATA:
        # Use first node as representative sensor data
        node = NODES_DATA[0]
        # Convert PIR boolean to numeric (0 or 1)
        pir_value = 1.0 if node.get('pir', False) else 0.0
        # Normalize acoustic_db to 0-1 range (assuming max ~100dB)
        sound_value = min(node.get('acoustic_db', 30) / 100.0, 1.0)
        add_sensor_reading(pir_value, sound_value)
        print(f"[ESP32] Processed sensor data for history: PIR={pir_value}, Sound={sound_value}")
    else:
        print("[ESP32] Not processing sensor data - ESP32 offline or no data available")

def check_esp32_connection():
    """Check if ESP32 is still connected based on last seen time"""
    global ESP32_CONNECTED
    
    if ESP32_LAST_SEEN is None:
        ESP32_CONNECTED = False
        print("[ESP32] No telemetry received yet - Device: Offline")
        return False
    
    time_since_last_seen = (datetime.now() - ESP32_LAST_SEEN).total_seconds()
    
    if time_since_last_seen > ESP32_TIMEOUT_SECONDS:
        ESP32_CONNECTED = False
        print(f"[ESP32] No telemetry for {time_since_last_seen:.1f}s - Device: Offline")
        return False
    
    print(f"[ESP32] Telemetry received {time_since_last_seen:.1f}s ago - Device: Online")
    return True

def get_location_name_from_coords(lat, lng):
    """Convert GPS coordinates to location name based on predefined regions"""
    # ESP32 Specific Sensor Field Node Locations
    if math.hypot(lat - 12.8224, lng - 77.5770) < 0.015: return "Buthanahalli (Bannerghatta NP Fringe, KA)"
    if math.hypot(lat - 12.79213, lng - 77.61622) < 0.015: return "Begihalli (Anekal Taluk, KA)"
    if math.hypot(lat - 12.5195, lng - 77.8200) < 0.015: return "Bettamugilalam (Hosur-Denkanikottai, TN)"
    if math.hypot(lat - 12.7180, lng - 77.5840) < 0.015: return "Ragihalli Village (Bengaluru Urban, KA)"
    if math.hypot(lat - 12.6100, lng - 77.7100) < 0.015: return "Thammanayakanahalli (Anekal Area, Bengaluru Urban, KA)"
    if math.hypot(lat - 12.5400, lng - 77.7800) < 0.015: return "Kadusivanapalli (Jawalagiri Area, Krishnagiri, TN)"
    
    # Broader regional mappings
    if lat >= 12.67 and lat <= 12.75 and lng >= 77.62 and lng <= 77.75: return "Anekal Taluk, Bengaluru Urban, Karnataka"
    if lat >= 12.75 and lat <= 12.82 and lng >= 77.62 and lng <= 77.68: return "Jigani Industrial Sector, Karnataka"
    if lat >= 12.70 and lat <= 12.82 and lng >= 77.50 and lng <= 77.61: return "Bannerghatta National Park Reserve Forest, Karnataka"
    if lat >= 12.83 and lat <= 13.20 and lng >= 77.45 and lng <= 77.75: return "Bengaluru Metropolitan Area, Karnataka"
    
    # Tamil Nadu regions
    if lat >= 12.65 and lng >= 77.72 and lng <= 78.10: return "Hosur Sector, Krishnagiri District, Tamil Nadu"
    if lat >= 12.40 and lat < 12.65 and lng >= 77.62 and lng <= 78.00: return "Denkanikottai / Thally Range, Tamil Nadu"
    if lat >= 12.10 and lat < 12.50 and lng >= 77.20 and lng < 77.70: return "Cauvery North Wildlife Sanctuary, Tamil Nadu"
    if lat >= 12.00 and lat < 12.60 and lng >= 77.70 and lng < 78.50: return "Krishnagiri District, Tamil Nadu"
    
    # Default fallback with coordinates
    return f"GPS Location ({lat:.4f}°, {lng:.4f}°)"

def reverse_geocode_coordinates(lat, lng):
    """Perform reverse geocoding using OpenStreetMap Nominatim API with caching and rate limiting"""
    global GEOCODE_LAST_REQUEST_TIME, GEOCODE_CACHE
    
    # Check cache first
    cache_key = f"{lat:.4f},{lng:.4f}"
    if cache_key in GEOCODE_CACHE:
        cached_result, cache_time = GEOCODE_CACHE[cache_key]
        # Use cache if less than 1 hour old
        if time.time() - cache_time < 3600:
            print(f"[GEOCODE] Using cached result for {cache_key}")
            return cached_result
    
    # Rate limiting - minimum interval between requests
    current_time = time.time()
    if current_time - GEOCODE_LAST_REQUEST_TIME < GEOCODE_MIN_INTERVAL:
        print(f"[GEOCODE] Rate limited - using fallback for {cache_key}")
        return get_location_name_from_coords(lat, lng)
    
    GEOCODE_LAST_REQUEST_TIME = current_time
    
    try:
        # Call OpenStreetMap Nominatim API
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=12"
        headers = {'User-Agent': 'WildlifeMonitoringSystem/1.0'}
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data and 'address' in data:
                addr = data['address']
                # Build location name from available fields
                place = (addr.get('village') or addr.get('town') or addr.get('city') or 
                        addr.get('suburb') or addr.get('county') or addr.get('state_district') or 
                        addr.get('district') or '')
                state = addr.get('state') or addr.get('country') or ''
                
                if place and state:
                    location_name = f"{place}, {state}"
                elif place:
                    location_name = place
                elif state:
                    location_name = state
                else:
                    location_name = data.get('display_name', '').split(',')[0]
                
                # Cache the result
                GEOCODE_CACHE[cache_key] = (location_name, current_time)
                print(f"[GEOCODE] Reverse geocoded {cache_key} -> {location_name}")
                return location_name
        
        # Fallback to predefined regions if API fails
        print(f"[GEOCODE] API failed for {cache_key}, using fallback")
        return get_location_name_from_coords(lat, lng)
        
    except Exception as e:
        print(f"[GEOCODE] Error reverse geocoding {cache_key}: {e}")
        return get_location_name_from_coords(lat, lng)

@app.route('/api/sensor/current', methods=['GET'])
def get_current_sensor_data():
    """Get current sensor values from the first node - ONLY if ESP32 is connected"""
    try:
        # Check ESP32 connection status
        check_esp32_connection()
        
        if not ESP32_CONNECTED:
            # ESP32 is offline - return offline status instead of fake data
            last_update = ESP32_LAST_SEEN.strftime("%Y-%m-%d %H:%M:%S") if ESP32_LAST_SEEN else None
            print(f"[ESP32] Device offline, returning last update: {last_update}")
            return jsonify({
                "esp32_connected": False,
                "pir": None,
                "sound": None,
                "pir_min": 0.0,
                "pir_max": 1.0,
                "pir_limit": 0.5,
                "sound_min": 0.0,
                "sound_max": 1.0,
                "sound_limit": 0.3,
                "pir_status": "OFFLINE",
                "sound_status": "OFFLINE",
                "message": "ESP32 Offline - Waiting for sensor data",
                "last_update": last_update
            })
        
        if NODES_DATA:
            node = NODES_DATA[0]  # Use first node as representative
            # Convert PIR boolean to numeric value (0 or 1)
            pir_value = 1.0 if node.get('pir', False) else 0.0
            # Normalize acoustic_db to 0-1 range (assuming max ~100dB)
            sound_value = min(node.get('acoustic_db', 30) / 100.0, 1.0)
            
            # Add to history (only if ESP32 is connected)
            add_sensor_reading(pir_value, sound_value)
            
            # Include last update timestamp
            last_update = ESP32_LAST_SEEN.strftime("%Y-%m-%d %H:%M:%S") if ESP32_LAST_SEEN else None
            print(f"[ESP32] Device online, returning data: PIR={pir_value}, Sound={sound_value}, Last update={last_update}")
            
            return jsonify({
                "esp32_connected": True,
                "pir": pir_value,
                "sound": sound_value,
                "pir_min": 0.0,
                "pir_max": 1.0,
                "pir_limit": 0.5,
                "sound_min": 0.0,
                "sound_max": 1.0,
                "sound_limit": 0.3,
                "pir_status": "ALERT" if pir_value > 0.5 else "NORMAL",
                "sound_status": "ALERT" if sound_value > 0.3 else "NORMAL",
                "last_update": last_update
            })
        return jsonify({"error": "No sensor data available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/esp32/status', methods=['GET'])
def get_esp32_status():
    """Get ESP32 connection status"""
    try:
        check_esp32_connection()
        
        if ESP32_LAST_SEEN is None:
            last_seen = "Never"
        else:
            last_seen = ESP32_LAST_SEEN.strftime("%Y-%m-%d %H:%M:%S")
        
        return jsonify({
            "connected": ESP32_CONNECTED,
            "last_seen": last_seen,
            "timeout_seconds": ESP32_TIMEOUT_SECONDS
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sensor/history', methods=['GET'])
def get_sensor_history():
    """Get sensor history data with filtering and sampling"""
    try:
        # Get query parameters
        sensor_type = request.args.get('sensor', 'pir')  # pir, sound, or combined
        limit = int(request.args.get('limit', 100))
        step = int(request.args.get('step', 1))  # sampling interval
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Filter history
        filtered_data = SENSOR_HISTORY.copy()
        
        # Apply date filtering if provided
        if from_date:
            filtered_data = [d for d in filtered_data if d['timestamp'] >= from_date]
        if to_date:
            filtered_data = [d for d in filtered_data if d['timestamp'] <= to_date]
        
        # Apply limit (take last N points)
        filtered_data = filtered_data[-limit:] if len(filtered_data) > limit else filtered_data
        
        # Apply step/sampling
        if step > 1:
            filtered_data = filtered_data[::step]
        
        # Prepare response based on sensor type
        if sensor_type == 'pir':
            return jsonify({
                "data": [{"timestamp": d['timestamp'], "value": d['pir']} for d in filtered_data],
                "sensor_type": "PIR",
                "total_points": len(filtered_data)
            })
        elif sensor_type == 'sound':
            return jsonify({
                "data": [{"timestamp": d['timestamp'], "value": d['sound']} for d in filtered_data],
                "sensor_type": "Sound",
                "total_points": len(filtered_data)
            })
        else:  # combined
            return jsonify({
                "data": filtered_data,
                "sensor_type": "Combined",
                "total_points": len(filtered_data)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sensor/export', methods=['GET'])
def export_sensor_data():
    """Export sensor data as CSV with step and date parameters"""
    try:
        sensor_type = request.args.get('sensor', 'combined')
        limit = int(request.args.get('limit', 1000))
        step = int(request.args.get('step', 1))
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Get filtered data
        filtered_data = SENSOR_HISTORY.copy()
        
        # Apply date filtering if provided
        if from_date:
            filtered_data = [d for d in filtered_data if d['timestamp'] >= from_date]
        if to_date:
            filtered_data = [d for d in filtered_data if d['timestamp'] <= to_date]
        
        # Apply limit and step
        filtered_data = filtered_data[-limit:]
        if step > 1:
            filtered_data = filtered_data[::step]
        
        # Prepare data for export
        if sensor_type == 'pir':
            data_to_export = [{"timestamp": d['timestamp'], "pir": d['pir']} for d in filtered_data]
        elif sensor_type == 'sound':
            data_to_export = [{"timestamp": d['timestamp'], "sound": d['sound']} for d in filtered_data]
        else:
            data_to_export = filtered_data
        
        # Create CSV response
        from io import StringIO
        output = StringIO()
        
        if sensor_type == 'pir':
            fieldnames = ['timestamp', 'pir']
        elif sensor_type == 'sound':
            fieldnames = ['timestamp', 'sound']
        else:
            fieldnames = ['timestamp', 'pir', 'sound']
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data_to_export)
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename=sensor_data_{sensor_type}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Integrated IoT and Edge-AI Acoustic Early Warning System Server...")
    print("Serving on http://127.0.0.1:5000")
    
    # Initialize Node 1 location with reverse geocoding on startup
    print("[GEOCODE] Initializing Node 1 location with reverse geocoding...")
    NODES_DATA[0]['location'] = reverse_geocode_coordinates(NODES_DATA[0]['lat'], NODES_DATA[0]['lng'])
    NODES_DATA[0]['name'] = f"Node 1 - {NODES_DATA[0]['location']}"
    print(f"[GEOCODE] Node 1 initial location: {NODES_DATA[0]['location']}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
