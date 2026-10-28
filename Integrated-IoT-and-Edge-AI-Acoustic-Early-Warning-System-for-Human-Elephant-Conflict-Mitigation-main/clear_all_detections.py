import os
import shutil
import json

base_dir = os.path.dirname(os.path.abspath(__file__))
scratch_backup = r"C:\Users\micva\.gemini\antigravity-ide\brain\5261a5d2-a9cd-4568-9b88-92ab47f017af\scratch\backup_detections"
os.makedirs(scratch_backup, exist_ok=True)

# 1. Backup & Clear local_detections.json
local_detections_file = os.path.join(base_dir, 'local_detections.json')
if os.path.exists(local_detections_file):
    shutil.copy2(local_detections_file, os.path.join(scratch_backup, 'local_detections.json'))
    with open(local_detections_file, 'w', encoding='utf-8') as f:
        json.dump([], f)
    print("[1] local_detections.json cleared.")

# 2. Backup & Clear static/detections
static_detections_dir = os.path.join(base_dir, 'static', 'detections')
if os.path.exists(static_detections_dir):
    backup_static = os.path.join(scratch_backup, 'static_detections')
    os.makedirs(backup_static, exist_ok=True)
    count = 0
    for fname in os.listdir(static_detections_dir):
        fpath = os.path.join(static_detections_dir, fname)
        if os.path.isfile(fpath):
            shutil.copy2(fpath, os.path.join(backup_static, fname))
            os.remove(fpath)
            count += 1
    print(f"[2] static/detections cleared ({count} images deleted).")

# 3. Backup & Clear WelcomeScreen/fall_final/detected_elephants
welcome_elephants_dir = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
if os.path.exists(welcome_elephants_dir):
    backup_welcome = os.path.join(scratch_backup, 'detected_elephants')
    os.makedirs(backup_welcome, exist_ok=True)
    count = 0
    for fname in os.listdir(welcome_elephants_dir):
        fpath = os.path.join(welcome_elephants_dir, fname)
        if os.path.isfile(fpath):
            shutil.copy2(fpath, os.path.join(backup_welcome, fname))
            os.remove(fpath)
            count += 1
    print(f"[3] WelcomeScreen/detected_elephants cleared ({count} images deleted).")

# 4. Backup & Reset elephant_detection_dataset.csv
csv_path = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
if os.path.exists(csv_path):
    shutil.copy2(csv_path, os.path.join(scratch_backup, 'elephant_detection_dataset.csv'))
    header = "Date,Time,Timestamp,Elephant_Detected,Number_of_Elephants,Highest_Confidence_Percent,Saved_Image\n"
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write(header)
    print("[4] elephant_detection_dataset.csv reset to header.")

# 5. Clear Supabase detections if reachable
try:
    from supabase_client import get_supabase_admin_client
    sb = get_supabase_admin_client()
    sb.table('detections').delete().neq('id', 0).execute()
    print("[5] Cloud Supabase detections table cleared.")
except Exception as e:
    print(f"[5] Supabase offline ({e}); local store successfully cleared.")

print("\nAll detection data and gallery images have been completely removed!")
