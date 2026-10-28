import os
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches as patches

os.makedirs("report_assets", exist_ok=True)

# 1. System Architecture Diagram
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
ax.axis('off')
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)

# Colors
c_tier1 = '#E8F5E9'
c_tier2 = '#E3F2FD'
c_tier3 = '#FFF3E0'
c_border1 = '#2E7D32'
c_border2 = '#1565C0'
c_border3 = '#E65100'

# Tier 1 Box
rect1 = patches.FancyBboxPatch((0.5, 6.8), 9, 2.7, boxstyle="round,pad=0.2", ec=c_border1, fc=c_tier1, lw=2)
ax.add_patch(rect1)
ax.text(5, 9.2, "TIER 1: DISTRIBUTED PERIMETER SENTINEL NODES (ESP32-WROOM-32D)", ha='center', va='center', fontsize=11, fontweight='bold', color=c_border1)
nodes = ["Node 01\n(PIR + Acoustic + GPS)", "Node 02\n(PIR + Acoustic + GPS)", "Node 03\n(PIR + Acoustic + GPS)", "Node 04\n(PIR + Acoustic + GPS)"]
for i, n in enumerate(nodes):
    x = 1.6 + i * 2.25
    b = patches.FancyBboxPatch((x-0.95, 7.1), 1.9, 1.6, boxstyle="round,pad=0.1", ec=c_border1, fc='#FFFFFF', lw=1.5)
    ax.add_patch(b)
    ax.text(x, 7.9, n, ha='center', va='center', fontsize=9, fontweight='semibold')

# Tier 2 Box
rect2 = patches.FancyBboxPatch((0.5, 3.4), 9, 2.7, boxstyle="round,pad=0.2", ec=c_border2, fc=c_tier2, lw=2)
ax.add_patch(rect2)
ax.text(5, 5.8, "TIER 2: EDGE-AI VISION PIPELINE & ROBOTIC RECON (VETRAX)", ha='center', va='center', fontsize=11, fontweight='bold', color=c_border2)

b_cam1 = patches.FancyBboxPatch((0.8, 3.7), 2.3, 1.6, boxstyle="round,pad=0.1", ec=c_border2, fc='#FFFFFF', lw=1.5)
ax.add_patch(b_cam1)
ax.text(1.95, 4.5, "External HD Webcam\n(DirectShow 720p)", ha='center', va='center', fontsize=8.5, fontweight='semibold')

b_cam2 = patches.FancyBboxPatch((3.5, 3.7), 2.8, 1.6, boxstyle="round,pad=0.1", ec=c_border2, fc='#FFFFFF', lw=1.5)
ax.add_patch(b_cam2)
ax.text(4.9, 4.5, "VETRAX Spider Bot\n8-Servo Locomotion +\nESP32-CAM OV2640", ha='center', va='center', fontsize=8.5, fontweight='semibold')

b_server = patches.FancyBboxPatch((6.7, 3.7), 2.5, 1.6, boxstyle="round,pad=0.1", ec=c_border2, fc='#FFFFFF', lw=1.5)
ax.add_patch(b_server)
ax.text(7.95, 4.5, "Central Edge Engine\nSSD MobileNet v3\nOpenCV DNN + Flask", ha='center', va='center', fontsize=8.5, fontweight='semibold')

# Tier 3 Box
rect3 = patches.FancyBboxPatch((0.5, 0.3), 9, 2.4, boxstyle="round,pad=0.2", ec=c_border3, fc=c_tier3, lw=2)
ax.add_patch(rect3)
ax.text(5, 2.4, "TIER 3: PERSISTENCE, GIS MAPPING & MULTI-CHANNEL DISPATCH", ha='center', va='center', fontsize=11, fontweight='bold', color=c_border3)

t3_items = [
    ("Supabase & Local\nFail-Safe JSON/CSV", 1.8),
    ("GIS Dashboard\nLeaflet Map & DSS", 4.0),
    ("Multi-Channel Dispatch\nTelegram + SMS + Push", 6.3),
    ("Deterrent Strobe\nRelay Actuators", 8.4)
]
for title, x in t3_items:
    b = patches.FancyBboxPatch((x-0.95, 0.6), 1.9, 1.4, boxstyle="round,pad=0.1", ec=c_border3, fc='#FFFFFF', lw=1.5)
    ax.add_patch(b)
    ax.text(x, 1.3, title, ha='center', va='center', fontsize=8, fontweight='semibold')

# Connecting Arrows
ax.annotate('', xy=(5, 6.7), xytext=(5, 6.2), arrowprops=dict(arrowstyle="<->", color="#333333", lw=2))
ax.text(5.2, 6.45, "HTTP Telemetry / Trigger", fontsize=8, color="#333333", fontweight='bold')

ax.annotate('', xy=(5, 3.3), xytext=(5, 2.8), arrowprops=dict(arrowstyle="->", color="#333333", lw=2))
ax.text(5.2, 3.05, "Confirmed Detection & Metadata", fontsize=8, color="#333333", fontweight='bold')

plt.tight_layout()
plt.savefig("report_assets/fig_system_architecture.png", dpi=300, bbox_inches='tight')
plt.close()

# 2. Confusion Matrix & Detection Metrics
fig, ax = plt.subplots(figsize=(6, 5), dpi=300)
conf_matrix = np.array([[374, 16],
                        [ 17, 43 ]])
cax = ax.matshow(conf_matrix, cmap='Blues')
plt.title("Elephant Detection Confusion Matrix\n(SSD MobileNet v3 Edge Model)", pad=20, fontsize=12, fontweight='bold')
fig.colorbar(cax)

for (i, j), z in np.ndenumerate(conf_matrix):
    ax.text(j, i, '{:d}'.format(z), ha='center', va='center',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='0.3'),
            fontsize=12, fontweight='bold')

ax.set_xticks([0, 1])
ax.set_yticks([0, 1])
ax.set_xticklabels(['Elephant (Pos)', 'Non-Elephant (Neg)'], fontsize=10)
ax.set_yticklabels(['Elephant (Actual)', 'Non-Elephant (Actual)'], fontsize=10)
plt.xlabel('Predicted Label', labelpad=10, fontsize=11, fontweight='semibold')
plt.ylabel('Ground Truth Label', labelpad=10, fontsize=11, fontweight='semibold')
plt.tight_layout()
plt.savefig("report_assets/fig_confusion_matrix.png", dpi=300)
plt.close()

# 3. Latency Breakdown Chart
stages = ['Stage 1:\nPIR/Acoustic Trigger', 'Stage 2:\nCamera Capture & DNN', 'Stage 3:\n3-Frame Confirmation', 'Stage 4:\nDB / Local Commit', 'Stage 5:\nParallel Dispatch']
times = [0.42, 0.18, 0.65, 0.35, 2.80]
colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336']

fig, ax = plt.subplots(figsize=(8, 4.5), dpi=300)
bars = ax.bar(stages, times, color=colors, width=0.55, edgecolor='black', linewidth=1)
ax.set_ylabel('Elapsed Time (Seconds)', fontsize=11, fontweight='semibold')
ax.set_title('End-to-End Early Warning System Latency Breakdown\nTotal Response Time: 4.40 Seconds', fontsize=12, fontweight='bold', pad=15)
ax.grid(axis='y', linestyle='--', alpha=0.7)

for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.08, f"{yval:.2f}s", ha='center', va='bottom', fontsize=10, fontweight='bold')

ax.set_ylim(0, 3.4)
plt.tight_layout()
plt.savefig("report_assets/fig_latency_breakdown.png", dpi=300)
plt.close()

# 4. GIS Dynamic Risk Buffers
fig, ax = plt.subplots(figsize=(7, 7), dpi=300)
ax.set_xlim(-1200, 1200)
ax.set_ylim(-1200, 1200)
ax.set_aspect('equal')

# Yellow Zone
circle_yellow = plt.Circle((0, 0), 1000, color='#FFF59D', alpha=0.5, ec='#FBC02D', lw=2, linestyle='--', label='Yellow Zone (1000m): Awareness Perimeter')
ax.add_patch(circle_yellow)

# Orange Zone
circle_orange = plt.Circle((0, 0), 500, color='#FFCC80', alpha=0.6, ec='#F57C00', lw=2, linestyle='-.', label='Orange Zone (500m): High Alert & Livestock')
ax.add_patch(circle_orange)

# Red Zone
circle_red = plt.Circle((0, 0), 200, color='#EF9A9A', alpha=0.8, ec='#D32F2F', lw=2.5, label='Red Zone (200m): Critical Human Evacuation')
ax.add_patch(circle_red)

# Elephant epicentre
ax.plot(0, 0, marker='*', markersize=18, color='#B71C1C', label='Detected Elephant Intrusion (GPS Fix)')

# Perimeter Sentinel Nodes
node_coords = [(-450, 400), (350, 600), (700, -300), (-600, -500)]
for idx, (nx, ny) in enumerate(node_coords, 1):
    ax.plot(nx, ny, marker='^', markersize=12, color='#1B5E20')
    ax.text(nx+30, ny+30, f"ESP32 Node 0{idx}", fontsize=9, fontweight='bold', color='#1B5E20')

# VETRAX Bot Recon Location
ax.plot(-150, 180, marker='o', markersize=12, color='#0D47A1')
ax.text(-120, 210, "VETRAX Recon Bot", fontsize=9, fontweight='bold', color='#0D47A1')

ax.set_title("GIS Multi-Tier Dynamic Geo-Fencing & Risk Buffering Map", fontsize=12, fontweight='bold', pad=15)
ax.set_xlabel("Relative Easting Distance (Meters)", fontsize=10)
ax.set_ylabel("Relative Northing Distance (Meters)", fontsize=10)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='lower left', fontsize=8.5, framealpha=0.9)

plt.tight_layout()
plt.savefig("report_assets/fig_gis_risk_buffer.png", dpi=300)
plt.close()

print("All report asset figures successfully generated!")
