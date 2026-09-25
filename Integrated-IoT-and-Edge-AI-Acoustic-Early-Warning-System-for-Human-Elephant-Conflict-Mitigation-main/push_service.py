"""
Web Push Service for Elephant Alert System
Department of AI & ML, Sri Sairam College of Engineering

Manages web push subscriptions using Supabase notification_config table
and logs outcomes to notification_history table.
"""

import os
import json
import pywebpush
from datetime import datetime
from threading import Lock
from supabase_client import get_supabase_admin_client

class PushService:
    """Manages web push subscriptions and notifications via Supabase"""
    
    def __init__(self):
        self.lock = Lock()
        
        # Load VAPID keys from environment
        self.vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY", "")
        self.vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
        self.vapid_claims = {
            "sub": f"mailto:{os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@example.com')}"
        }
    
    def is_configured(self):
        """Check if VAPID keys are configured"""
        return bool(self.vapid_public_key and self.vapid_private_key)
    
    def get_vapid_public_key(self):
        """Get the VAPID public key for frontend subscription"""
        return self.vapid_public_key
    
    def add_subscription(self, subscription_data, user_id):
        """Add a new push subscription to Supabase notification_config"""
        if not user_id:
            return None
            
        with self.lock:
            sb = get_supabase_admin_client()
            
            # Upsert into notification_config
            # We assume one web_push subscription per user for simplicity,
            # or we can just insert.
            # To handle multiple devices, we would need to check if it exists.
            recipient_data = json.dumps(subscription_data)
            
            # Check if this exact subscription already exists for this user
            existing = sb.table('notification_config').select('*').eq('user_id', user_id).eq('alert_type', 'web_push').execute()
            
            for config in existing.data:
                if config['recipient'] == recipient_data:
                    return config['id']
                    
            # Insert new
            res = sb.table('notification_config').insert({
                "user_id": user_id,
                "alert_type": "web_push",
                "recipient": recipient_data,
                "enabled": True
            }).execute()
            
            if res.data:
                return res.data[0]['id']
            return None
    
    def disable_subscription(self, config_id):
        """Disable a subscription"""
        with self.lock:
            sb = get_supabase_admin_client()
            sb.table('notification_config').update({"enabled": False}).eq('id', config_id).execute()
            return True

    def remove_subscription(self, endpoint, user_id):
        """Remove a subscription from Supabase notification_config"""
        if not user_id:
            return False
            
        with self.lock:
            sb = get_supabase_admin_client()
            # Find the subscription for this user
            existing = sb.table('notification_config').select('*').eq('user_id', user_id).eq('alert_type', 'web_push').execute()
            
            for config in existing.data:
                try:
                    sub_data = json.loads(config['recipient'])
                    if sub_data.get('endpoint') == endpoint:
                        sb.table('notification_config').delete().eq('id', config['id']).execute()
                        return True
                except:
                    pass
            return False
    
    def get_subscriptions(self, role=None, enabled_only=True):
        """Get subscriptions, optionally filtered by user role from profiles"""
        with self.lock:
            sb = get_supabase_admin_client()
            
            # Get all web push configs
            query = sb.table('notification_config').select('id, user_id, recipient, enabled').eq('alert_type', 'web_push')
            if enabled_only:
                query = query.eq('enabled', True)
                
            configs = query.execute().data
            
            if not configs:
                return []
                
            if role:
                # We need to filter by role. Let's fetch profiles for these user_ids.
                user_ids = [c['user_id'] for c in configs if c.get('user_id')]
                if not user_ids:
                    return []
                
                profiles_res = sb.table('profiles').select('user_id, role, full_name').in_('user_id', user_ids).execute()
                profiles = {p['user_id']: p for p in profiles_res.data}
                
                # Filter configs where the user's role matches
                filtered_configs = []
                for c in configs:
                    p = profiles.get(c['user_id'])
                    # role might be case insensitive or exact match based on the system
                    if p and p['role'].upper() == role.upper():
                        c['user_name'] = p['full_name']
                        c['user_role'] = p['role']
                        filtered_configs.append(c)
                        
                configs = filtered_configs
            
            # Format the output to match what the old method returned
            formatted_subs = []
            for c in configs:
                try:
                    sub_data = json.loads(c['recipient'])
                    formatted_subs.append({
                        "id": c['id'],
                        "user_id": c['user_id'],
                        "user_name": c.get('user_name', 'Unknown'),
                        "user_role": c.get('user_role', 'Unknown'),
                        "endpoint": sub_data.get("endpoint"),
                        "keys": sub_data.get("keys", {})
                    })
                except:
                    pass
                    
            return formatted_subs

    def send_notification(self, subscription, data):
        """Send a push notification to a single subscription"""
        if not self.is_configured():
            return {"success": False, "error": "VAPID not configured"}
        
        try:
            subscription_info = {
                "endpoint": subscription["endpoint"],
                "keys": subscription["keys"]
            }
            
            pywebpush.webpush(
                subscription_info,
                data=json.dumps(data),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def _log_notification_history(self, alert_id, user_id, recipient, message, status, error_message=None):
        sb = get_supabase_admin_client()
        sb.table('notification_history').insert({
            "alert_id": alert_id,
            "user_id": user_id,
            "alert_type": "web_push",
            "recipient": recipient,
            "message": json.dumps(message),
            "status": status,
            "error_message": error_message,
            "sent_at": datetime.now().isoformat() if status == 'sent' else None
        }).execute()
    
    def send_activity_alert(self, activity_event, role=None):
        """Send activity detection alert to all subscribed users"""
        if not self.is_configured():
            return {"success": False, "error": "VAPID not configured", "recipients": []}
        
        subscriptions = self.get_subscriptions(role=role, enabled_only=True)
        if not subscriptions:
            return {"success": False, "error": "No active subscriptions", "recipients": []}
        
        trigger_source = activity_event.get("trigger_source", "PIR")
        location = activity_event.get("location", "Unknown")
        event_id = activity_event.get("event_id")
        
        notification_data = {
            "title": "⚠️ Activity Detected",
            "body": f"{trigger_source} detected at {location}. Please check the camera.",
            "data": {
                "event_id": event_id,
                "event_type": "ACTIVITY_DETECTED",
                "trigger_source": trigger_source,
                "location": location,
                "camera_verification": activity_event.get("camera_verification", "PENDING"),
                "url": "/#camera-tab"
            },
            "timestamp": activity_event.get("timestamp")
        }
        
        results = []
        for sub in subscriptions:
            result = self.send_notification(sub, notification_data)
            status = 'sent' if result.get("success") else 'failed'
            
            self._log_notification_history(
                alert_id=None, # Not an elephant alert yet
                user_id=sub['user_id'],
                recipient=sub['endpoint'],
                message=notification_data,
                status=status,
                error_message=result.get("error")
            )
            
            results.append({
                "subscription_id": sub["id"],
                "sent": result.get("success", False),
                "error": result.get("error")
            })
            
            if not result.get("success", False):
                self.disable_subscription(sub["id"])
        
        success_count = sum(1 for r in results if r["sent"])
        return {
            "success": success_count > 0,
            "successful": success_count,
            "failed": len(subscriptions) - success_count,
        }

    def send_elephant_alert(self, alert_event, role=None):
        """Send elephant alert to all subscribed users"""
        if not self.is_configured():
            return {"success": False, "error": "VAPID not configured", "recipients": []}
        
        subscriptions = self.get_subscriptions(role=role, enabled_only=True)
        if not subscriptions:
            return {"success": False, "error": "No active subscriptions", "recipients": []}
        
        location = alert_event.get("location", "Unknown")
        alert_id = alert_event.get("event_id") or alert_event.get("alert_id")
        
        notification_data = {
            "title": "🐘 ELEPHANT DETECTED",
            "body": f"Camera verification confirmed an elephant at {location}. Immediate attention required.",
            "data": {
                "event_id": alert_id,
                "event_type": "ELEPHANT_DETECTED",
                "location": location,
                "confidence": alert_event.get("confidence", 0),
                "image_path": alert_event.get("image_path", ""),
                "url": "/#camera-tab"
            },
            "timestamp": alert_event.get("timestamp")
        }
        
        results = []
        for sub in subscriptions:
            result = self.send_notification(sub, notification_data)
            status = 'sent' if result.get("success") else 'failed'
            
            # We assume alert_id is a valid UUID if it comes from the alerts table.
            # If not, we might need to handle it gracefully, but usually it's tied to an alert in the DB.
            # In Phase 4, the alert system should generate UUIDs.
            try:
                import uuid
                valid_uuid = str(uuid.UUID(str(alert_id)))
            except:
                valid_uuid = None
                
            self._log_notification_history(
                alert_id=valid_uuid,
                user_id=sub['user_id'],
                recipient=sub['endpoint'],
                message=notification_data,
                status=status,
                error_message=result.get("error")
            )
            
            results.append({
                "subscription_id": sub["id"],
                "sent": result.get("success", False)
            })
            
            if not result.get("success", False):
                self.disable_subscription(sub["id"])
        
        success_count = sum(1 for r in results if r["sent"])
        return {
            "success": success_count > 0,
            "successful": success_count,
            "failed": len(subscriptions) - success_count,
        }

# Global instance
push_service = None
service_lock = Lock()

def get_push_service():
    global push_service
    with service_lock:
        if push_service is None:
            push_service = PushService()
        return push_service
