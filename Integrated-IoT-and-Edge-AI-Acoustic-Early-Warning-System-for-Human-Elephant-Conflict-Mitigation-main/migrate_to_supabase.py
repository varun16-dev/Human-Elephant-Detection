"""
Migration script: Populate Supabase Cloud with genuine historical records and images
- Uploads detected elephant photos to 'elephant-images' storage bucket
- Migrates genuine detection records from elephant_detection_dataset.csv to public.detections
- Registers nodes in public.devices
"""

import os
import csv
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

# Load environment
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, '.env'))

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

# Initialize client with service role key for admin migration
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def register_initial_devices():
    """Register initial node devices in public.devices"""
    print("\n--- [1/3] Registering Initial Devices ---")
    devices = [
        {
            "device_id": "ESP32-NODE-01",
            "name": "Node 01 - Buthanahalli (Bannerghatta NP)",
            "location_name": "Buthanahalli, Bannerghatta NP Fringe, KA",
            "latitude": 12.8224,
            "longitude": 77.5770,
            "status": "online",
            "last_seen": datetime.now().isoformat()
        },
        {
            "device_id": "ESP32-NODE-02",
            "name": "Node 02 - Begihalli",
            "location_name": "Begihalli (Anekal Taluk, KA)",
            "latitude": 12.7921,
            "longitude": 77.6162,
            "status": "offline",
            "last_seen": None
        }
    ]
    
    for dev in devices:
        try:
            existing = supabase.table('devices').select('id').eq('device_id', dev['device_id']).execute()
            if existing.data and len(existing.data) > 0:
                supabase.table('devices').update(dev).eq('device_id', dev['device_id']).execute()
                print(f"Updated existing device: {dev['device_id']}")
            else:
                supabase.table('devices').insert(dev).execute()
                print(f"Inserted new device: {dev['device_id']}")
        except Exception as e:
            print(f"Error registering {dev['device_id']}: {e}")

def upload_detected_images():
    """Upload detected elephant photos to Supabase Storage bucket 'elephant-images'"""
    print("\n--- [2/3] Uploading Elephant Images to Supabase Storage ---")
    images_dir = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
    if not os.path.exists(images_dir):
        print(f"Images directory not found: {images_dir}")
        return {}
    
    files = [f for f in os.listdir(images_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    print(f"Found {len(files)} local images to upload.")
    
    # List existing files in bucket
    try:
        existing_files = {item['name'] for item in supabase.storage.from_('elephant-images').list()}
    except Exception as e:
        print(f"Could not list bucket files: {e}")
        existing_files = set()
        
    uploaded_map = {}
    for i, filename in enumerate(files):
        file_path = os.path.join(images_dir, filename)
        storage_path = filename  # Stored directly as filename in bucket
        
        if filename in existing_files:
            uploaded_map[filename] = storage_path
            continue
            
        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
                
            res = supabase.storage.from_('elephant-images').upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"}
            )
            uploaded_map[filename] = storage_path
            if (i + 1) % 15 == 0 or (i + 1) == len(files):
                print(f"Uploaded {i + 1}/{len(files)}: {filename}")
        except Exception as e:
            print(f"Failed to upload {filename}: {e}")
            
    print(f"Image upload complete. Total mapped: {len(uploaded_map)}")
    return uploaded_map

def migrate_detection_records(uploaded_images):
    """Import genuine elephant detection records into public.detections"""
    print("\n--- [3/3] Migrating Detection Records from CSV ---")
    csv_path = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    if not os.path.exists(csv_path):
        print(f"CSV file not found: {csv_path}")
        return

    # Check if detections already populated
    try:
        current = supabase.table('detections').select('id', count='exact').limit(1).execute()
        if current.count and current.count > 50:
            print(f"Detections table already has {current.count} records. Skipping CSV re-import.")
            return
    except Exception as e:
        print(f"Notice on checking detections count: {e}")

    records_to_insert = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        
        for row in reader:
            if len(row) < 4:
                continue
                
            date_val = row[0]
            time_val = row[1]
            timestamp_val = row[2]
            detected_val = row[3]  # 'YES' or 'NO'
            
            # Format timestamp ISO
            try:
                dt = datetime.strptime(timestamp_val, "%Y-%m-%dT%H:%M:%S")
                iso_ts = dt.isoformat() + "Z"
            except Exception:
                iso_ts = datetime.now().isoformat()
                
            count_val = int(row[4]) if len(row) > 4 and row[4].isdigit() else 0
            try:
                conf_val = float(row[5]) if len(row) > 5 else 0.0
                if conf_val > 1.0:
                    conf_val = round(conf_val / 100.0, 4)
            except ValueError:
                conf_val = 0.0
                
            img_filename = ""
            if len(row) > 6 and row[6].strip():
                raw_img = row[6].strip().replace('\\', '/')
                if 'elephant_' in raw_img:
                    img_filename = os.path.basename(raw_img)
            elif len(row) > 7 and row[7].strip():
                raw_img = row[7].strip().replace('\\', '/')
                if 'elephant_' in raw_img:
                    img_filename = os.path.basename(raw_img)
                    
            image_path = img_filename if img_filename in uploaded_images else (img_filename if img_filename.endswith('.jpg') else None)
            
            # Only keep YES detections and sample of NO detections to avoid bloat
            if detected_val.upper() == 'YES' or len(records_to_insert) < 20:
                is_detected = (detected_val.upper() == 'YES')
                rec = {
                    "device_id": "ESP32-NODE-01",
                    "timestamp": iso_ts,
                    "detection": "ELEPHANT_DETECTED" if is_detected else "SAFE",
                    "elephant_count": count_val if is_detected else 0,
                    "confidence": conf_val,
                    "image_path": image_path,
                    "pir_detected": is_detected,
                    "sound_detected": is_detected,
                    "sound_level": 85.0 if is_detected else 35.0,
                    "latitude": 12.8224,
                    "longitude": 77.5770
                }
                records_to_insert.append(rec)
                
            # Insert in batches of 50
            if len(records_to_insert) >= 50:
                try:
                    supabase.table('detections').insert(records_to_insert).execute()
                    print(f"Batch inserted {len(records_to_insert)} detections into Supabase...")
                except Exception as e:
                    print(f"Batch insert error: {e}")
                records_to_insert = []
                
    if records_to_insert:
        try:
            supabase.table('detections').insert(records_to_insert).execute()
            print(f"Final batch of {len(records_to_insert)} detections inserted.")
        except Exception as e:
            print(f"Final batch insert error: {e}")

if __name__ == '__main__':
    print("=== SUPABASE DATA MIGRATION STARTED ===")
    register_initial_devices()
    uploaded_images = upload_detected_images()
    migrate_detection_records(uploaded_images)
    print("=== SUPABASE DATA MIGRATION FINISHED ===")
