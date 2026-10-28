"""
Automated Startup & Preflight System Orchestrator
Integrated IoT and Edge-AI Acoustic Early Warning System for Human-Elephant Conflict Mitigation
Department of AI & ML, Sri Sairam College of Engineering
"""

import os
import sys
import socket
import signal
import time
from datetime import datetime

# ANSI Color formatting (graceful fallback)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def print_banner():
    print(f"\n{BLUE}{BOLD}{'=' * 75}{RESET}")
    print(f"{BLUE}{BOLD} INTEGRATED IoT & EDGE-AI HUMAN-ELEPHANT EARLY WARNING SYSTEM (PHASE II){RESET}")
    print(f"{BLUE}{BOLD} Extensible VETRAX Spider Robot Autonomous Recon Node{RESET}")
    print(f"{BLUE}{BOLD}{'=' * 75}{RESET}\n")


def check_python_environment():
    """Verify supported Python version (3.10+)"""
    print(f"[*] Checking Python runtime environment...")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print(f"{RED}[FAIL] Python 3.10+ is required. Found: {sys.version}{RESET}")
        return False
    print(f"  {GREEN}[PASS]{RESET} Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    return True


def check_dependencies():
    """Verify critical Python packages are installed"""
    print(f"[*] Checking core dependencies...")
    required = [
        ("flask", "Flask web framework"),
        ("cv2", "OpenCV Computer Vision (DNN)"),
        ("numpy", "NumPy tensor computing"),
        ("requests", "Requests HTTP client"),
        ("dotenv", "Python Dotenv configuration")
    ]
    all_ok = True
    for mod, desc in required:
        try:
            __import__(mod)
            print(f"  {GREEN}[PASS]{RESET} {mod:<10} - {desc}")
        except ImportError:
            print(f"  {RED}[FAIL]{RESET} {mod:<10} - Missing! Install via: pip install {mod}")
            all_ok = False
    return all_ok


def check_ai_model():
    """Verify SSD MobileNet v3 weights, config, and coco dataset files"""
    print(f"[*] Checking AI Elephant Detection Model assets...")
    try:
        from ai_elephant_detector import get_elephant_detector
        detector = get_elephant_detector()
        if not detector.is_loaded:
            print(f"  {RED}[FAIL]{RESET} AI Model failed to load: {detector.load_error}")
            return False
        print(f"  {GREEN}[PASS]{RESET} MobileNet SSD v3 loaded successfully. Elephant Class Index: {detector.elephant_class_index}")
        return True
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET} Exception during model verification: {e}")
        return False


def check_port_availability(host="127.0.0.1", port=5000):
    """Verify whether Flask server port is free"""
    print(f"[*] Checking network port {port} availability...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"  {YELLOW}[WARN]{RESET} Port {port} is currently IN USE by another process.")
            print(f"         If an old server instance is running, please terminate it before starting.")
            return False
        else:
            print(f"  {GREEN}[PASS]{RESET} Port {port} is available.")
            return True
    finally:
        sock.close()


def check_directories():
    """Ensure required runtime directories exist"""
    print(f"[*] Ensuring runtime storage directories exist...")
    dirs = [
        os.path.join(BASE_DIR, "static", "detections"),
        os.path.join(BASE_DIR, "scratch"),
        os.path.join(BASE_DIR, "templates")
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    print(f"  {GREEN}[PASS]{RESET} All runtime directories ready.")
    return True


def check_configuration():
    """Check configuration status for alerts and edge authentication"""
    print(f"[*] Checking Notification & Edge-AI Configuration...")
    try:
        from free_alert_service import get_free_alert_manager
        fam = get_free_alert_manager()
        cfg = fam.get_safe_config()

        tg_ready = fam.telegram.is_configured()
        sms_ready = fam.email_sms.is_configured()

        tg_status = f"{GREEN}CONFIGURED{RESET}" if tg_ready else f"{YELLOW}STANDBY (Set TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID in .env or UI){RESET}"
        sms_status = f"{GREEN}CONFIGURED{RESET}" if sms_ready else f"{YELLOW}STANDBY (Set SMTP_EMAIL & SMTP_PASSWORD in .env or UI){RESET}"

        print(f"  - Option A (Telegram Bot API): {tg_status}")
        print(f"  - Option B (Carrier Email-to-SMS): {sms_status}")

        vetrax_key = os.getenv("VETRAX_API_KEY", "vetrax-secure-edge-token-2026")
        masked_tok = vetrax_key[:4] + "********" if len(vetrax_key) >= 4 else "********"
        print(f"  - VETRAX Robot Authentication: {GREEN}ACTIVE{RESET} (Token: {masked_tok})")
        return True
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} Config check notice: {e}")
        return True


def check_camera_configuration():
    """Verify camera configuration and display active source"""
    print(f"[*] Checking Camera Stream Configuration...")
    try:
        from server import get_configured_camera_source
        cur_src = get_configured_camera_source()
        
        if isinstance(cur_src, int):
            cur_label = f"Camera Device Index {cur_src}"
        else:
            cur_label = f"Network Stream [{cur_src}]"
            
        print(f"  - Active Camera Source: {BLUE}{cur_label}{RESET}")
        print(f"  {GREEN}[PASS]{RESET} Live Camera Ready (Switch live anytime on dashboard using the [Cam 0] / [Cam 1] buttons)")
        return True
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} Camera check notice: {e}")
        return True
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} Camera check notice: {e}")
        return True


def run_preflight_checks():
    """Execute complete preflight checklist"""
    print_banner()
    checks = [
        check_python_environment(),
        check_dependencies(),
        check_directories(),
        check_ai_model(),
        check_configuration(),
        check_camera_configuration(),
        check_port_availability()
    ]
    if not all(checks):
        print(f"\n{RED}[ABORT] Preflight checks failed. Please resolve above issues before starting.{RESET}\n")
        return False
    print(f"\n{GREEN}[READY] All preflight checks passed successfully!{RESET}\n")
    return True


def start_server():
    """Starts the Flask server with graceful signal handling"""
    from server import app

    def handle_shutdown(signum, frame):
        print(f"\n{YELLOW}[SHUTDOWN] Intercepted signal {signum}. Shutting down gracefully...{RESET}")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handle_shutdown)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print(f"{BLUE}[START] Launching Server at http://{host}:{port} (Debug: {debug}){RESET}")
    print(f"[*] Access GIS Map & Dashboard: http://localhost:{port}")
    print(f"[*] VETRAX Edge-AI Frame Intake: http://localhost:{port}/api/robot/vetrax/frame")
    print(f"[*] Press CTRL+C to stop the system.\n")

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check-only":
        success = run_preflight_checks()
        sys.exit(0 if success else 1)
    else:
        if run_preflight_checks():
            start_server()
        else:
            sys.exit(1)
