"""
Fix existing timestamps in Supabase raw_sensor_data table.
Shifts timestamps that were saved with naive local time (+5h30m ahead in UTC)
back to proper UTC, so they align with created_at and display the true local time.
"""
from supabase_client import get_supabase_client
from datetime import datetime, timezone, timedelta
import time

def fix_timestamps():
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc).isoformat()
    
    print(f"Fetching rows with future/offset timestamps relative to {now_utc}...")
    
    # Process in batches of 100
    total_fixed = 0
    while True:
        rows = supabase.table('raw_sensor_data').select('*').gt('timestamp', now_utc).limit(100).execute().data
        if not rows:
            break
            
        updates = []
        for r in rows:
            orig_ts = r['timestamp']
            dt = datetime.fromisoformat(orig_ts)
            fixed_dt = dt - timedelta(hours=5, minutes=30)
            r['timestamp'] = fixed_dt.isoformat()
            updates.append(r)
            
        supabase.table('raw_sensor_data').upsert(updates).execute()
        total_fixed += len(updates)
        print(f"Fixed batch of {len(updates)} rows (Total: {total_fixed})...")
        time.sleep(0.2)
        
    print(f"Successfully corrected {total_fixed} timestamps in public.raw_sensor_data!")

if __name__ == '__main__':
    fix_timestamps()
