"""
Camera Alert Monitor for Elephant Alert System
Department of AI & ML, Sri Sairam College of Engineering

This script monitors the elephant detection CSV file and sends confirmed
detections to the alert system via the Flask API.

This is a NON-INVASIVE integration - it does NOT modify the existing detector.
It simply monitors the CSV output and forwards detections to the alert system.
"""

import csv
import os
import time
import requests
import sys
from datetime import datetime

# Configuration
CSV_PATH = r"c:\Users\micva\Downloads\Complete System\WelcomeScreen\fall_final\elephant_detection_dataset.csv"

API_URL = "http://127.0.0.1:5000/api/alerts/process"
POLL_INTERVAL_SECONDS = 1

class CameraAlertMonitor:
    """Monitors CSV and forwards detections to alert system"""
    
    def __init__(self):
        self.last_processed_line = 0
        self.last_processed_timestamp = None
        
    def get_csv_line_count(self):
        """Get the number of lines in the CSV file"""
        if not os.path.exists(CSV_PATH):
            return 0
        
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    
    def read_new_detections(self):
        """Read new detections since last check"""
        if not os.path.exists(CSV_PATH):
            return []
        
        new_detections = []
        
        try:
            with open(CSV_PATH, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                
                # Skip to the last processed line
                for _ in range(self.last_processed_line):
                    next(reader, None)
                
                # Read new lines
                for row in reader:
                    if len(row) >= 6:
                        new_detections.append(row)
                        self.last_processed_line += 1
        
        except Exception as e:
            print(f"Error reading CSV: {e}", flush=True)
        
        return new_detections
    
    def process_detection(self, row):
        """Process a single detection row and send to alert system"""
        try:
            # Parse CSV row
            date_val = row[0]
            time_val = row[1]
            timestamp_val = row[2]
            detected_val = row[3]
            count_val = int(row[4]) if row[4].isdigit() else 0
            conf_val = float(row[5]) if row[5].replace('.', '').isdigit() else 0.0
            image_val = row[6] if len(row) > 6 else ""
            
            # Only process if elephant detected
            if detected_val != "YES" or count_val == 0:
                return
            
            # Prepare data for API
            csv_row_data = {
                "date": date_val,
                "time": time_val,
                "timestamp": timestamp_val,
                "elephant_detected": detected_val,
                "elephant_count": count_val,
                "confidence": conf_val
            }
            
            # Convert confidence to 0-1 range
            confidence_normalized = conf_val / 100.0 if conf_val > 1 else conf_val
            
            # Get full image path if available
            image_path = ""
            if image_val:
                # Image path might be relative or absolute
                if os.path.isabs(image_val):
                    image_path = image_val
                else:
                    # Assume it's relative to the detector folder
                    image_path = os.path.abspath(os.path.join(
                        os.path.dirname(CSV_PATH),
                        image_val
                    ))
            else:
                # If no image in CSV, try to get the latest image from detected_elephants folder
                image_dir = os.path.join(os.path.dirname(CSV_PATH), "detected_elephants")
                if os.path.exists(image_dir):
                    try:
                        files = os.listdir(image_dir)
                        images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        if images:
                            # Sort by modification time, get the most recent
                            images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
                            image_path = os.path.join(image_dir, images[0])
                    except Exception:
                        pass
            
            # Send to alert system
            payload = {
                "elephant_count": count_val,
                "confidence": confidence_normalized,
                "image_path": image_path,
                "csv_row_data": csv_row_data
            }
            
            response = requests.post(API_URL, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Alert created: {result.get('alert', {}).get('alert_id')}", flush=True)
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No alert created: {result.get('message')}", flush=True)
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] API error: {response.status_code}", flush=True)
        
        except Exception as e:
            print(f"Error processing detection: {e}", flush=True)
    
    def run(self):
        """Main monitoring loop"""
        print("Camera Alert Monitor started", flush=True)
        print(f"Monitoring CSV: {CSV_PATH}", flush=True)
        print(f"API Endpoint: {API_URL}", flush=True)
        print("Press Ctrl+C to stop", flush=True)
        
        # Initialize line count
        self.last_processed_line = self.get_csv_line_count()
        print(f"Starting from line: {self.last_processed_line}", flush=True)
        
        # Check if CSV exists
        if not os.path.exists(CSV_PATH):
            print(f"ERROR: CSV file not found at {CSV_PATH}", flush=True)
            return
        
        try:
            while True:
                # Check for new detections
                new_detections = self.read_new_detections()
                
                # Process each new detection
                for detection in new_detections:
                    self.process_detection(detection)
                
                # Wait before next check
                time.sleep(POLL_INTERVAL_SECONDS)
        
        except KeyboardInterrupt:
            print("\nCamera Alert Monitor stopped", flush=True)
        except Exception as e:
            print(f"Fatal error: {e}", flush=True)

if __name__ == "__main__":
    monitor = CameraAlertMonitor()
    monitor.run()
