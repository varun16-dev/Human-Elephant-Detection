"""
Root Directory Launcher for start_system.py
Automatically switches to the project directory and launches preflight & server.
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

    script_path = os.path.join(TARGET_DIR, "start_system.py")
    ret = subprocess.call([sys.executable, script_path] + sys.argv[1:], cwd=TARGET_DIR)
    sys.exit(ret)
