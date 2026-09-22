"""
Notification Service for Elephant Alert System
Department of AI & ML, Sri Sairam College of Engineering

This service provides:
- Confirmation layer for elephant detections
- Alert event management
- Cooldown/debouncing logic
- Alert history tracking
"""

import json
import os
import time
from datetime import datetime
from enum import Enum
from threading import Lock

class AlertState(Enum):
    """Alert state machine states"""
    NO_DETECTION = "NO_DETECTION"
    POSSIBLE = "POSSIBLE"
    CONFIRMED = "CONFIRMED"
    ALERT_SENT = "ALERT_SENT"
    MONITORING = "MONITORING"

class NotificationService:
    """Manages elephant detection confirmation and alert events"""
    
    def __init__(self, config_path="alert_config.json", history_path="alert_history.json"):
        self.config_path = config_path
        self.history_path = history_path
        self.lock = Lock()
        
        # Load configuration
        self.config = self._load_config()
        
        # State machine
        self.current_state = AlertState.NO_DETECTION
        self.consecutive_detections = 0
        self.confidence_buffer = []
        
        # Cooldown tracking
        self.last_alert_time = 0
        self.detection_start_time = 0
        
        # Load alert history
        self.alert_history = self._load_alert_history()
    
    def _load_config(self):
        """Load alert configuration from JSON file"""
        default_config = {
            "confirmation_settings": {
                "confirmation_frames": 3,
                "min_confirmation_confidence": 0.50,
                "alert_cooldown_seconds": 300
            },
            "whatsapp_settings": {
                "csv_mode": "LATEST_RECORD",
                "enabled": True
            },
            "web_push_settings": {
                "enabled": True,
                "notification_ttl_seconds": 3600
            },
            "alert_storage": {
                "max_alerts_history": 1000
            }
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults
                    for key in default_config:
                        if key not in config:
                            config[key] = default_config[key]
                    return config
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
        
        return default_config
    
    def _load_alert_history(self):
        """Load alert history from JSON file"""
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading alert history: {e}")
        
        return []
    
    def _save_alert_history(self):
        """Save alert history to JSON file"""
        try:
            max_alerts = self.config.get("alert_storage", {}).get("max_alerts_history", 1000)
            # Keep only the most recent alerts
            self.alert_history = self.alert_history[-max_alerts:]
            
            with open(self.history_path, 'w') as f:
                json.dump(self.alert_history, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving alert history: {e}")
    
    def process_detection(self, elephant_count, confidence, image_path, csv_row_data):
        """
        Process a detection frame through the confirmation layer
        
        Args:
            elephant_count: Number of elephants detected
            confidence: Detection confidence (0-1)
            image_path: Path to detection image
            csv_row_data: Dictionary with CSV row data
            
        Returns:
            dict or None: Alert event if confirmed, None otherwise
        """
        with self.lock:
            current_time = time.time()
            
            # Get confirmation settings
            conf_frames = self.config["confirmation_settings"]["confirmation_frames"]
            min_conf = self.config["confirmation_settings"]["min_confirmation_confidence"]
            cooldown = self.config["confirmation_settings"]["alert_cooldown_seconds"]
            
            # Check if we're in cooldown
            if current_time - self.last_alert_time < cooldown:
                # Still in cooldown, don't process
                return None
            
            # State machine processing
            if elephant_count > 0:
                # Elephant detected
                if self.current_state == AlertState.NO_DETECTION:
                    # New detection starts
                    self.current_state = AlertState.POSSIBLE
                    self.consecutive_detections = 1
                    self.confidence_buffer = [confidence]
                    self.detection_start_time = current_time
                    return None
                
                elif self.current_state == AlertState.POSSIBLE:
                    # Continue checking
                    self.consecutive_detections += 1
                    self.confidence_buffer.append(confidence)
                    
                    # Check if we have enough frames
                    if self.consecutive_detections >= conf_frames:
                        # Calculate average confidence
                        avg_confidence = sum(self.confidence_buffer) / len(self.confidence_buffer)
                        
                        if avg_confidence >= min_conf:
                            # Confirmed!
                            self.current_state = AlertState.CONFIRMED
                            alert_event = self._create_alert_event(
                                elephant_count, avg_confidence, image_path, csv_row_data
                            )
                            self.current_state = AlertState.ALERT_SENT
                            self.last_alert_time = current_time
                            self._save_alert_to_history(alert_event)
                            return alert_event
                        else:
                            # Confidence too low, reset
                            self.current_state = AlertState.NO_DETECTION
                            self.consecutive_detections = 0
                            self.confidence_buffer = []
                            return None
                
                elif self.current_state == AlertState.ALERT_SENT:
                    # Already sent alert, continue monitoring
                    self.current_state = AlertState.MONITORING
                    return None
                
                elif self.current_state == AlertState.MONITORING:
                    # Still detecting, continue monitoring
                    return None
            
    
    def _create_alert_event(self, elephant_count, confidence, image_path, csv_row_data):
        """Create a structured alert event"""
        return {
            "alert_id": f"alert_{int(time.time())}",
            "alert_type": "ELEPHANT_CONFIRMED",
            "status": "ACTIVE",
            "timestamp": datetime.now().isoformat(),
            "timestamp_unix": time.time(),
            "elephant_count": elephant_count,
            "confidence": round(confidence * 100, 2),
            "image_path": image_path,
            "csv_data": csv_row_data,
            "delivery_status": {
                "web_push": {
                    "forest_officers": "pending",
                    "villagers": "pending"
                }
            }
        }
    
    def _save_alert_to_history(self, alert_event):
        """Save alert event to history"""
        self.alert_history.append(alert_event)
        self._save_alert_history()
    
    def get_alert_history(self, limit=None):
        """Get alert history"""
        with self.lock:
            if limit:
                return self.alert_history[-limit:]
            return self.alert_history.copy()
    
    def update_delivery_status(self, alert_id, channel, role, status):
        """Update delivery status for an alert"""
        with self.lock:
            for alert in self.alert_history:
                if alert["alert_id"] == alert_id:
                    if channel in alert["delivery_status"]:
                        if role in alert["delivery_status"][channel]:
                            alert["delivery_status"][channel][role] = status
                            self._save_alert_history()
                            return True
            return False
    
    def reset_cooldown(self):
        """Reset the alert cooldown (for testing)"""
        with self.lock:
            self.last_alert_time = 0
            self.current_state = AlertState.NO_DETECTION
            self.consecutive_detections = 0
            self.confidence_buffer = []
    
    def get_current_state(self):
        """Get current state information"""
        with self.lock:
            return {
                "state": self.current_state.value,
                "consecutive_detections": self.consecutive_detections,
                "avg_confidence": sum(self.confidence_buffer) / len(self.confidence_buffer) if self.confidence_buffer else 0,
                "last_alert_time": self.last_alert_time,
                "time_since_last_alert": time.time() - self.last_alert_time if self.last_alert_time > 0 else 0
            }

# Global instance
notification_service = None
service_lock = Lock()

def get_notification_service():
    """Get or create the global notification service instance"""
    global notification_service
    with service_lock:
        if notification_service is None:
            notification_service = NotificationService()
        return notification_service
