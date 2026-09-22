"""
Web Push Service for Elephant Alert System
Department of AI & ML, Sri Sairam College of Engineering

Manages web push subscriptions and sends browser notifications.
"""

import os
import json
import pywebpush
from datetime import datetime
from threading import Lock

class PushService:
    """Manages web push subscriptions and notifications"""
    
    def __init__(self, subscriptions_path="push_subscriptions.json"):
        self.subscriptions_path = subscriptions_path
        self.lock = Lock()
        
        # Load VAPID keys from environment
        self.vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY", "")
        self.vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
        self.vapid_claims = {
            "sub": f"mailto:{os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@example.com')}"
        }
        
        # Load subscriptions
        self.subscriptions = self._load_subscriptions()
    
    def _load_subscriptions(self):
        """Load push subscriptions from JSON file"""
        if os.path.exists(self.subscriptions_path):
            try:
                with open(self.subscriptions_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading subscriptions: {e}")
        
        return []
    
    def _save_subscriptions(self):
        """Save subscriptions to JSON file"""
        try:
            with open(self.subscriptions_path, 'w') as f:
                json.dump(self.subscriptions, f, indent=2)
        except Exception as e:
            print(f"Error saving subscriptions: {e}")
    
    def is_configured(self):
        """Check if VAPID keys are configured"""
        return bool(self.vapid_public_key and self.vapid_private_key)
    
    def get_vapid_public_key(self):
        """Get the VAPID public key for frontend subscription"""
        return self.vapid_public_key
    
    def add_subscription(self, subscription_data, user_role="VILLAGER", user_name="Unknown"):
        """Add a new push subscription"""
        with self.lock:
            subscription_id = f"sub_{len(self.subscriptions) + 1:03d}"
            
            new_subscription = {
                "id": subscription_id,
                "endpoint": subscription_data.get("endpoint"),
                "keys": subscription_data.get("keys", {}),
                "user_role": user_role,
                "user_name": user_name,
                "enabled": True,
                "created_at": datetime.now().isoformat()
            }
            
            self.subscriptions.append(new_subscription)
            self._save_subscriptions()
            
            return subscription_id
    
    def remove_subscription(self, subscription_id):
        """Remove a push subscription"""
        with self.lock:
            self.subscriptions = [s for s in self.subscriptions if s["id"] != subscription_id]
            self._save_subscriptions()
            return True
    
    def disable_subscription(self, subscription_id):
        """Disable a subscription without removing it"""
        with self.lock:
            for sub in self.subscriptions:
                if sub["id"] == subscription_id:
                    sub["enabled"] = False
                    self._save_subscriptions()
                    return True
            return False
    
    def get_subscriptions(self, role=None, enabled_only=True):
        """Get subscriptions, optionally filtered by role"""
        with self.lock:
            subscriptions = self.subscriptions
            
            if enabled_only:
                subscriptions = [s for s in subscriptions if s.get("enabled", False)]
            
            if role:
                subscriptions = [s for s in subscriptions if s.get("user_role") == role]
            
            return subscriptions

    def send_notification(self, subscription, data):
        """Send a push notification to a single subscription"""
        if not self.is_configured():
            return {"success": False, "error": "VAPID not configured"}
        
        try:
            # Prepare subscription data
            subscription_info = {
                "endpoint": subscription["endpoint"],
                "keys": subscription["keys"]
            }
            
            # Send notification
            pywebpush.webpush(
                subscription_info,
                data=json.dumps(data),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims
            )
            
            return {"success": True}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def send_elephant_alert(self, alert_event, role=None):
        """Send elephant alert to all subscribed users"""
        if not self.is_configured():
            return {"success": False, "error": "VAPID not configured", "recipients": []}
        
        # Get subscriptions
        subscriptions = self.get_subscriptions(role=role, enabled_only=True)
        
        if not subscriptions:
            return {"success": False, "error": "No active subscriptions", "recipients": []}
        
        # Prepare notification data based on alert type
        if alert_event.get("alert_type") == "TEST":
            notification_data = {
                "title": "⚠️ TEST NOTIFICATION",
                "body": "This is only a test of the Elephant Monitoring Web Push system.",
                "data": {
                    "alert_id": alert_event.get("alert_id"),
                    "url": "/#alerts-tab"
                },
                "timestamp": alert_event.get("timestamp")
            }
        else:
            notification_data = {
                "title": "🐘 Elephant Confirmed",
                "body": f"Count: {alert_event.get('elephant_count', 0)} | Confidence: {alert_event.get('confidence', 0)}%",
                "data": {
                    "alert_id": alert_event.get("alert_id"),
                    "url": "/#camera-tab"
                },
                "timestamp": alert_event.get("timestamp")
            }
        
        # Send to each subscription
        results = []
        for subscription in subscriptions:
            result = self.send_notification(subscription, notification_data)
            
            results.append({
                "subscription_id": subscription["id"],
                "user_name": subscription.get("user_name", "Unknown"),
                "user_role": subscription.get("user_role", "Unknown"),
                "sent": result.get("success", False),
                "error": result.get("error")
            })
            
            # Disable subscription if it fails repeatedly
            if not result.get("success", False):
                self.disable_subscription(subscription["id"])
        
        success_count = sum(1 for r in results if r["sent"])
        
        return {
            "success": success_count > 0,
            "total_subscriptions": len(subscriptions),
            "successful": success_count,
            "failed": len(subscriptions) - success_count,
            "results": results
        }

# Global instance
push_service = None
service_lock = Lock()

def get_push_service():
    """Get or create the global push service instance"""
    global push_service
    with service_lock:
        if push_service is None:
            push_service = PushService()
        return push_service
