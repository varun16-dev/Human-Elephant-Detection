"""
Notification Service for Elephant Alert System
Department of AI & ML, Sri Sairam College of Engineering

This service provides:
- Two-stage detection system (Activity → Camera → Elephant)
- Activity event management for PIR/sound detection
- Camera verification state machine
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

class ActivityEventState(Enum):
    """Activity event states for two-stage detection"""
    IDLE = "IDLE"
    ACTIVITY_DETECTED = "ACTIVITY_DETECTED"
    CAMERA_PENDING = "CAMERA_PENDING"
    CAMERA_VERIFYING = "CAMERA_VERIFYING"
    CAMERA_VERIFIED_NO_ELEPHANT = "CAMERA_VERIFIED_NO_ELEPHANT"
    CAMERA_VERIFIED_ELEPHANT = "CAMERA_VERIFIED_ELEPHANT"
    CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"

class NotificationService:
    """Manages two-stage detection: Activity → Camera → Elephant"""
    
    def __init__(self, config_path="alert_config.json", history_path="alert_history.json"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, config_path) if not os.path.isabs(config_path) else config_path
        self.history_path = os.path.join(base_dir, history_path) if not os.path.isabs(history_path) else history_path
        self.lock = Lock()
        
        # Load configuration
        self.config = self._load_config()
        
        # Elephant detection state machine
        self.current_state = AlertState.NO_DETECTION
        self.consecutive_detections = 0
        self.confidence_buffer = []
        
        # Activity event state machine
        self.activity_state = ActivityEventState.IDLE
        self.current_activity_event = None
        self.activity_cooldown_time = 0
        
        # Cooldown tracking
        self.last_alert_time = 0
        self.detection_start_time = 0
        self.last_activity_time = 0
        
        # In-memory history for state machine (loaded from disk)
        self.alert_history = self._load_history()

    def _load_history(self):
        """Load persistent alert history from JSON file"""
        if os.path.exists(self.history_path) and os.path.getsize(self.history_path) > 0:
            try:
                with open(self.history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"Error loading alert history from disk: {e}")
        return []

    def _save_alert_to_history(self, alert_event):
        """Persist alert event into local alert_history.json"""
        if not alert_event:
            return
        self.alert_history.append(alert_event)
        max_h = self.config.get("alert_storage", {}).get("max_alerts_history", 1000)
        if len(self.alert_history) > max_h:
            self.alert_history = self.alert_history[-max_h:]

        # Skip writing to disk if in unit test environment
        if os.getenv("TESTING", "").lower() in ("true", "1") or "unittest" in sys.modules or "pytest" in sys.modules:
            return

        try:
            with open(self.history_path, 'w', encoding='utf-8') as f:
                json.dump(self.alert_history, f, indent=2)
        except Exception as e:
            print(f"Error saving alert history to disk: {e}")
    
    def _load_config(self):
        """Load alert configuration from JSON file"""
        default_config = {
            "confirmation_settings": {
                "confirmation_frames": 3,
                "min_confirmation_confidence": 0.50,
                "alert_cooldown_seconds": 300
            },
            "activity_settings": {
                "activity_cooldown_seconds": 60,
                "camera_verification_timeout_seconds": 30
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
    
    def _save_alert_to_supabase(self, alert_event, is_elephant=False):
        """Save alert event to Supabase and local history"""
        self._save_alert_to_history(alert_event)
        try:
            from supabase_client import get_supabase_admin_client
            sb = get_supabase_admin_client()
            
            # Insert into alerts table
            sb.table('alerts').insert({
                "device_id": alert_event.get('node_id', 'ESP32-NODE-01'),
                "alert_type": alert_event.get('event_type') or alert_event.get('alert_type'),
                "message": alert_event.get('sms_message', 'Alert generated'),
                "status": 'active',
                "created_at": alert_event.get('timestamp') or datetime.now().isoformat()
            }).execute()
        except Exception as e:
            pass
            
    def dispatch_whatsapp_alert(self, alert_event):
        """
        Dispatch customized WhatsApp alert via local Baileys service (http://localhost:3001)
        ONLY to configured recipient (+917094528671)
        """
        try:
            import whatsapp_service
            success, msg = whatsapp_service.send_confirmed_elephant_whatsapp(alert_event)
            return success
        except Exception as e:
            print(f"[WHATSAPP] Error in dispatch_whatsapp_alert: {e}")
    def process_activity_detection(self, node_id, pir_detected, sound_detected, location, lat, lng):
        """
        Process PIR/sound activity detection (Stage 1: Activity Event)
        
        Args:
            node_id: Node identifier
            pir_detected: Boolean PIR detection status
            sound_detected: Boolean sound detection status
            location: Location name
            lat: Latitude
            lng: Longitude
            
        Returns:
            dict or None: Activity event if new detection, None if in cooldown
        """
        with self.lock:
            current_time = time.time()
            
            # Check activity cooldown
            activity_cooldown = self.config.get("activity_settings", {}).get("activity_cooldown_seconds", 60)
            if current_time - self.last_activity_time < activity_cooldown:
                # Still in cooldown, don't create new event
                return None
            
            # Check if there's actual activity
            if not (pir_detected or sound_detected):
                return None
            
            # Determine trigger source
            trigger_source = []
            if pir_detected:
                trigger_source.append("PIR")
            if sound_detected:
                trigger_source.append("SOUND")
            
            # Create activity event
            activity_event = {
                "event_id": f"activity_{int(time.time())}",
                "event_type": "ACTIVITY_DETECTED",
                "node_id": node_id,
                "timestamp": datetime.now().isoformat(),
                "timestamp_unix": current_time,
                "pir_detected": pir_detected,
                "sound_detected": sound_detected,
                "trigger_source": " + ".join(trigger_source),
                "location": location,
                "latitude": lat,
                "longitude": lng,
                "camera_verification": "PENDING",
                "elephant_detected": False,
                "notification_sent": False,
                "sms_sent": False,
                "delivery_status": {
                    "web_push": "pending",
                    "sms": "pending"
                },
                "sms_message": self._generate_activity_sms(trigger_source, location)
            }
            
            self.current_activity_event = activity_event
            self.activity_state = ActivityEventState.ACTIVITY_DETECTED
            self.last_activity_time = current_time
            self.activity_cooldown_time = current_time + activity_cooldown
            
            # In-memory append for state machine
            self.alert_history.append(activity_event)
            # Limit size
            if len(self.alert_history) > 100:
                self.alert_history = self.alert_history[-100:]
                
            # Save to Supabase
            self._save_alert_to_supabase(activity_event)
            
            return activity_event
    
    def process_camera_verification(self, event_id, elephant_detected, confidence=0.0, image_path=""):
        """
        Process camera/AI verification result (Stage 2: Elephant Confirmation)
        
        Args:
            event_id: Activity event ID to verify
            elephant_detected: Boolean whether elephant was found
            confidence: Detection confidence (0-1)
            image_path: Path to verification image
            
        Returns:
            dict: Updated event with verification result
        """
        with self.lock:
            # Find the activity event
            event = None
            for alert in self.alert_history:
                if alert.get("event_id") == event_id:
                    event = alert
                    break
            
            if not event:
                return {"error": "Event not found"}
            
            # Update verification status
            if elephant_detected:
                event["camera_verification"] = "COMPLETED"
                event["elephant_detected"] = True
                event["event_type"] = "ELEPHANT_DETECTED"
                event["confidence"] = round(confidence * 100, 2)
                event["image_path"] = image_path
                event["sms_message"] = self._generate_elephant_sms(event.get("location", "Unknown"))
                self.activity_state = ActivityEventState.CAMERA_VERIFIED_ELEPHANT
            else:
                event["camera_verification"] = "COMPLETED"
                event["elephant_detected"] = False
                event["event_type"] = "ACTIVITY_VERIFIED_NO_ELEPHANT"
                self.activity_state = ActivityEventState.CAMERA_VERIFIED_NO_ELEPHANTANT
            
            event["verification_timestamp"] = datetime.now().isoformat()
            
            # Update Supabase - since we don't track the UUID of the activity event locally,
            # we'll just insert a new alert if it's an elephant
            if elephant_detected:
                self._save_alert_to_supabase(event, is_elephant=True)
                # Dispatch customized WhatsApp via local Baileys service to Varun (+917094528671)
                self.dispatch_whatsapp_alert(event)
            
            return event
    
    def process_detection(self, elephant_count, confidence, image_path, csv_row_data):
        """
        Process a detection frame through the confirmation layer (legacy method)
        
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
                            self._save_alert_to_supabase(alert_event, is_elephant=True)
                            self.dispatch_whatsapp_alert(alert_event)
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
        loc = "Anekal, Karnataka"
        if isinstance(csv_row_data, dict) and csv_row_data.get("location"):
            loc = csv_row_data.get("location")

        return {
            "alert_id": f"alert_{int(time.time())}",
            "event_id": f"alert_{int(time.time())}",
            "alert_type": "ELEPHANT_CONFIRMED",
            "event_type": "ELEPHANT_CONFIRMED",
            "status": "ACTIVE",
            "timestamp": datetime.now().isoformat(),
            "timestamp_unix": time.time(),
            "elephant_count": elephant_count,
            "elephant_detected": True,
            "confidence": round(confidence * 100, 2),
            "image_path": image_path,
            "trigger_source": "AI Camera Stream",
            "location": loc,
            "camera_verification": f"Verified ({elephant_count})",
            "csv_data": csv_row_data,
            "delivery_status": {
                "web_push": {
                    "forest_officers": "sent",
                    "villagers": "sent"
                }
            }
        }
    
    def get_alert_history(self, limit=None):
        """Get alert history from Supabase with resilient local file and detection store fallback"""
        with self.lock:
            # 1. Try Supabase first if available
            try:
                from supabase_client import get_supabase_admin_client
                sb = get_supabase_admin_client()
                query = sb.table('alerts').select('*').order('created_at', desc=True)
                if limit:
                    query = query.limit(limit)
                data = query.execute().data
                if data and len(data) > 0:
                    return data
            except Exception:
                pass

            # 2. Local fallback from alert_history.json / in-memory history
            combined_history = list(self.alert_history)

            # 3. Also merge from local_detections.json (ground truth of confirmed camera detections)
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                loc_path = os.path.join(base_dir, 'local_detections.json')
                if os.path.exists(loc_path) and os.path.getsize(loc_path) > 0:
                    with open(loc_path, 'r', encoding='utf-8') as f:
                        loc_detections = json.load(f)

                    existing_ts = set()
                    for h in combined_history:
                        ts_val = str(h.get('timestamp') or h.get('created_at') or '')[:19]
                        if ts_val:
                            existing_ts.add(ts_val)

                    for d in loc_detections:
                        d_ts = str(d.get('timestamp', ''))
                        d_key = d_ts[:19] if d_ts else ''
                        if d_key and d_key in existing_ts:
                            continue

                        count = d.get('elephant_count', 1 if d.get('detection') == 'ELEPHANT_DETECTED' else 0)
                        conf = d.get('confidence', 0.8)
                        if isinstance(conf, (int, float)) and conf <= 1.0:
                            conf = round(conf * 100, 1)

                        is_elephant = (d.get('detection') == 'ELEPHANT_DETECTED') or (count > 0)
                        loc_name = d.get('location') or "Anekal, Karnataka"

                        combined_history.append({
                            "event_id": f"loc_{d_key or int(time.time())}",
                            "alert_id": f"alert_loc_{d_key}",
                            "event_type": "ELEPHANT_CONFIRMED" if is_elephant else "ACTIVITY_DETECTED",
                            "alert_type": "ELEPHANT_CONFIRMED" if is_elephant else "ACTIVITY_DETECTED",
                            "timestamp": d_ts or datetime.now().isoformat(),
                            "location": loc_name,
                            "trigger_source": "PIR + Sound" if (d.get('pir_detected') or d.get('sound_detected')) else "AI Camera Stream",
                            "camera_verification": f"Verified ({count})" if is_elephant else "Completed",
                            "confidence": conf,
                            "elephant_detected": is_elephant,
                            "elephant_count": count,
                            "image_path": d.get('image_path', ''),
                            "delivery_status": {
                                "web_push": "sent" if d.get('alert_sent') else "pending"
                            }
                        })
            except Exception as e:
                print(f"Notice loading local_detections for alert history: {e}")

            # Sort descending by timestamp (newest first)
            def _extract_ts(item):
                val = item.get('timestamp') or item.get('created_at') or ''
                return str(val)

            combined_history.sort(key=_extract_ts, reverse=True)

            if limit:
                return combined_history[:limit]
            return combined_history
    
    def update_delivery_status(self, alert_id, channel, role, status):
        """Update delivery status for an alert in Supabase (legacy stub)"""
        return True
    
    def reset_cooldown(self):
        """Reset the alert cooldown (for testing)"""
        with self.lock:
            self.last_alert_time = 0
            self.current_state = AlertState.NO_DETECTION
            self.consecutive_detections = 0
            self.confidence_buffer = []
            self.last_activity_time = 0
    
    def _generate_activity_sms(self, trigger_source, location):
        """Generate SMS message for activity detection"""
        trigger = " + ".join(trigger_source)
        # Use "Unknown Location" if location is not available
        safe_location = location if location else "Unknown Location"
        return f"⚠️ Activity detected at {safe_location}. {trigger} detected. Please check the camera for verification."
    
    def _generate_elephant_sms(self, location):
        """Generate SMS message for elephant confirmation"""
        return f"🐘 ELEPHANT DETECTED at {location}. Camera verification confirmed an elephant. Please take immediate action."
    
    def _generate_whatsapp_message(self, alert_event):
        """
        Generate WhatsApp message for elephant detection
        
        Format:
        🚨 ELEPHANT ALERT
        
        An elephant has been detected in the monitored area.
        
        Time: <actual detection timestamp>
        Location: <actual location if available>
        Elephant Count: <actual count>
        Confidence: <actual confidence>
        
        Please take necessary safety precautions.
        """
        timestamp = alert_event.get('timestamp', alert_event.get('verification_timestamp', 'Unknown'))
        location = alert_event.get('location', 'Unknown Location')
        elephant_count = alert_event.get('elephant_count', alert_event.get('csv_data', {}).get('elephant_count', 'Unknown'))
        confidence = alert_event.get('confidence', 'Unknown')
        
        message = f"""🚨 ELEPHANT ALERT

An elephant has been detected in the monitored area.

Time: {timestamp}
Location: {location}
Elephant Count: {elephant_count}
Confidence: {confidence}%

Please take necessary safety precautions."""
        
        return message
    
    def _is_detection_already_processed(self, detection_id):
        """
        Check if a detection has already been processed for WhatsApp
        Uses Supabase alerts table to check for existing delivery records
        """
        try:
            from supabase_client import get_supabase_admin_client
            sb = get_supabase_admin_client()
            
            # Check if any delivery records exist for this detection_id with channel=WHATSAPP
            result = sb.table('alerts').select('*').eq('alert_type', 'WHATSAPP').eq('message', detection_id).execute()
            
            return len(result.data) > 0
        except Exception as e:
            print(f"[WHATSAPP] Error checking detection processing status: {e}")
            return False
    
    def _mark_detection_as_processed(self, detection_id):
        """
        Mark a detection as processed for WhatsApp idempotency
        Inserts a marker record in Supabase alerts table
        """
        try:
            from supabase_client import get_supabase_admin_client
            sb = get_supabase_admin_client()
            
            # Insert a marker record to indicate this detection was processed
            sb.table('alerts').insert({
                "alert_type": "WHATSAPP",
                "message": detection_id,  # Use message field to store detection_id as marker
                "status": "processed",
                "created_at": datetime.now().isoformat()
            }).execute()
            
            print(f"[WHATSAPP] Marked detection {detection_id} as processed")
        except Exception as e:
            print(f"[WHATSAPP] Error marking detection as processed: {e}")
    
    def _track_delivery_status(self, detection_id, recipient, channel, status, message_sid=None, error_message=None):
        """
        Track delivery status for each recipient in Supabase alerts table
        
        Args:
            detection_id: The detection ID for idempotency
            recipient: The recipient phone number
            channel: Communication channel (WHATSAPP)
            status: Delivery status (pending, sent, delivered, failed)
            message_sid: Provider message identifier if available
            error_message: Error message if failed
        """
        try:
            from supabase_client import get_supabase_admin_client
            sb = get_supabase_admin_client()
            
            # Insert delivery tracking record
            delivery_record = {
                "alert_type": channel,
                "message": f"{detection_id}|{recipient}",  # Combined for tracking
                "status": status,
                "created_at": datetime.now().isoformat()
            }
            
            if message_sid:
                delivery_record["message"] = f"{detection_id}|{recipient}|{message_sid}"
            
            if error_message:
                delivery_record["message"] = f"{detection_id}|{recipient}|ERROR:{error_message}"
            
            sb.table('alerts').insert(delivery_record).execute()
            
            print(f"[WHATSAPP] Tracked delivery: {recipient} -> {status}")
        except Exception as e:
            print(f"[WHATSAPP] Error tracking delivery status: {e}")
    
    def get_current_state(self):
        """Get current state information"""
        with self.lock:
            return {
                "state": self.current_state.value,
                "activity_state": self.activity_state.value,
                "consecutive_detections": self.consecutive_detections,
                "avg_confidence": sum(self.confidence_buffer) / len(self.confidence_buffer) if self.confidence_buffer else 0,
                "last_alert_time": self.last_alert_time,
                "time_since_last_alert": time.time() - self.last_alert_time if self.last_alert_time > 0 else 0,
                "last_activity_time": self.last_activity_time,
                "time_since_last_activity": time.time() - self.last_activity_time if self.last_activity_time > 0 else 0
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
