"""
Root Directory Launcher for Human-Elephant Conflict Mitigation System
Automatically sets the working directory and launches the main Flask server.
"""

import os
import sys

TARGET_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Integrated-IoT-and-Edge-AI-Acoustic-Early-Warning-System-for-Human-Elephant-Conflict-Mitigation-main"
)

import subprocess

if __name__ == "__main__":
    if not os.path.exists(TARGET_DIR):
        print(f"Error: Target project directory not found at: {TARGET_DIR}")
        sys.exit(1)

    os.chdir(TARGET_DIR)
    sys.path.insert(0, TARGET_DIR)

    server_script = os.path.join(TARGET_DIR, "server.py")
    ret = subprocess.call([sys.executable, server_script] + sys.argv[1:], cwd=TARGET_DIR)
    sys.exit(ret)
