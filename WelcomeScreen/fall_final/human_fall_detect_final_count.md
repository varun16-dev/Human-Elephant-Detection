# Elephant Detection System — `human_fall_detect_final_count.py`

Real-time webcam-based elephant detection using MobileNet SSD (COCO), with CSV logging, image capture, and voice alerts.

---

## Settings

| Parameter | Value |
|---|---|
| Confidence Threshold | `0.45` |
| Camera Index | `0` |
| Log Interval | `1 second` |
| Model Input Size | `320 × 320` |
| CSV File | `elephant_detection_dataset.csv` |
| Image Folder | `detected_elephants/` |

---

## Required Files

```
coco.data
ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt.txt
frozen_inference_graph.pb
```

All three must be in the **same folder** as this script.

---

## How It Works

### 1. Startup Checks
- Verifies all required model files exist
- Confirms `elephant` class is present in `coco.data`
- Opens webcam at `1280 × 720` via DirectShow (`CAP_DSHOW`)
- Creates `detected_elephants/` folder if it doesn't exist
- Appends to (or creates) the CSV with headers

### 2. Detection Loop (per frame)

```
Read frame → Run MobileNet SSD → Filter elephants → Count
```

**If elephants detected:**
- Draws a red bounding box around each elephant
- Labels each box: `Elephant N — XX.X%`
- Displays count overlay on frame
- On new event start (first frame of a new sighting):
  - Saves a `.jpg` snapshot to `detected_elephants/`
  - Triggers a threaded voice alert via `pyttsx3`
- Every second: writes a `YES` row to CSV

**If no elephants:**
- Resets event state
- Displays `No Elephant Detected` in green
- Every second: writes a `NO` row to CSV

### 3. CSV Row Format

| Date | Time | Timestamp | Elephant_Detected | Number_of_Elephants | Highest_Confidence_Percent | Saved_Image |
|---|---|---|---|---|---|---|
| `2026-09-19` | `23:35:51` | `2026-09-19T23:35:51` | `YES` / `NO` | `1` | `48.40` | `detected_elephants/elephant_20260919_233551.jpg` |

### 4. Image Naming

```
elephant_YYYYMMDD_HHMMSS.jpg
```

One image is saved per **detection event** (not per frame). A new event begins only after elephants fully leave the frame and reappear.

### 5. Voice Alert

- Runs in a background `daemon` thread
- Prevents overlapping speech via `voice_lock`
- Says: `"Warning! Elephant detected."` or `"Warning! N elephants detected."`

---

## Controls

| Key | Action |
|---|---|
| `Q` | Stop detection and close window |

---

## Output

```
detected_elephants/
    elephant_20260919_233551.jpg
    elephant_20260919_233612.jpg
    ...

elephant_detection_dataset.csv
```

---

## Dependencies

```
opencv-python
pyttsx3
```

---

## Notes

- Camera must not be in use by another app (Zoom, Meet, WhatsApp, Camera)
- Check Windows camera permissions if the camera fails to open
- The script appends to the CSV on each run — it does not overwrite existing data
