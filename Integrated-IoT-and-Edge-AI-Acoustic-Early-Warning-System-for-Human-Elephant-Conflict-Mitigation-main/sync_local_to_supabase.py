"""
Phase 5: Sync Local to Supabase Utility
Migrates local CSV detection history to the new Supabase `detections` table.
"""

import os
import csv
from datetime import datetime, timezone
from supabase_client import get_supabase_admin_client

def migrate_csv_to_supabase():
    print("Starting migration of local CSV detections to Supabase...")
    sb = get_supabase_admin_client()
    
    # Locate the CSV file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found at {csv_path}")
        return
        
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            success_count = 0
            skip_count = 0
            
            for row in reader:
                # CSV Format typically has: Date,Time,Timestamp,Elephant_Detected,Count,Confidence
                try:
                    # Parse timestamp or fallback to combining date/time
                    if row.get('Timestamp'):
                        ts = row.get('Timestamp')
                        try:
                            # Try to parse as float (Unix timestamp)
                            ts_float = float(ts)
                            dt = datetime.fromtimestamp(ts_float, tz=timezone.utc).isoformat()
                        except ValueError:
                            # It's likely already an ISO string or similar
                            # If it lacks timezone, append Z for UTC
                            if 'T' in ts and not ts.endswith('Z') and '+' not in ts:
                                dt = f"{ts}Z"
                            else:
                                dt = ts
                    else:
                        dt = datetime.now(timezone.utc).isoformat()
                        
                    detected = row.get('Elephant_Detected', '').upper() == 'YES'
                    count = int(row.get('Count', 0))
                    confidence = float(row.get('Confidence', 0))
                    
                    if not detected:
                        skip_count += 1
                        continue
                        
                    # We need to map this to the detections table
                    # detections table columns: id, device_id, timestamp, detection, confidence, image_url, created_at, incident_status, alert_sent
                    
                    detection_data = {
                        "device_id": "ESP32-NODE-01", # Assume node 1 for historical data
                        "timestamp": dt,
                        "detection": "ELEPHANT_DETECTED",
                        "confidence": confidence,
                        "incident_status": "resolved", # Historical data is resolved
                        "alert_sent": True
                    }
                    
                    sb.table('detections').insert(detection_data).execute()
                    success_count += 1
                    
                except Exception as e:
                    print(f"Error parsing row {row}: {e}")
                    
        print(f"\nMigration Complete!")
        print(f"- Successfully migrated: {success_count} detections")
        print(f"- Skipped (no elephant): {skip_count} records")
        
    except Exception as e:
        print(f"Fatal error during migration: {e}")

if __name__ == "__main__":
    migrate_csv_to_supabase()
