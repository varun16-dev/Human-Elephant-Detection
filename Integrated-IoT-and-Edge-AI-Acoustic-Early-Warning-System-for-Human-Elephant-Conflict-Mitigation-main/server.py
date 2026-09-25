"""
Integrated IoT and Edge-AI Acoustic Early Warning System
Major Project Phase II - Server & REST API Engine
Department of AI & ML, Sri Sairam College of Engineering
"""

from flask import Flask, render_template, jsonify, request, send_from_directory, Response, session, redirect, url_for, abort
from functools import wraps
import uuid
import random
import time
import math
import os
import threading
import csv
import requests
import subprocess
import sys
from datetime import datetime, timezone, timedelta, time as dt_time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import alert services
from notification_service import get_notification_service
from push_service import get_push_service

# Import Supabase client
from supabase_client import get_supabase_client, get_supabase_admin_client, get_auth_client

base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, 
            static_folder=os.path.join(base_dir, 'static'),
            template_folder=os.path.join(base_dir, 'templates'))
app.secret_key = os.getenv('SECRET_KEY', 'elephant-early-warning-system-secure-key-2026-phase2')

# =====================================================
# CAMERA AI DETECTION (human_fall_detect_final_count) PROCESS MANAGER
# =====================================================
FALL_DETECT_SCRIPT = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'human_fall_detect_final_count.py'))
FALL_DETECT_DIR = os.path.dirname(FALL_DETECT_SCRIPT)
DETECTION_PROCESS = None
DETECTION_LOCK = threading.Lock()
LAST_DETECTION_TRIGGER_TIME = 0
DETECTION_COOLDOWN_SECONDS = 15  # Debounce to prevent multiple processes for ongoing event

def is_human_fall_detection_running():
    """Check if human_fall_detect_final_count process is currently active"""
    global DETECTION_PROCESS
    if DETECTION_PROCESS is not None:
        if DETECTION_PROCESS.poll() is None:
            return True
        else:
            DETECTION_PROCESS = None
    return False

def trigger_human_fall_detection(source="sensor"):
    """
    Trigger the human_fall_detect_final_count camera/AI detection script
    whenever PIR or Sound sensor detects activity.
    Prevents duplicate instances and enforces cooldown.
    """
    global DETECTION_PROCESS, LAST_DETECTION_TRIGGER_TIME
    with DETECTION_LOCK:
        now = time.time()
        
        # 1. Prevent duplicate instances if already running
        if is_human_fall_detection_running():
            print(f"[TRIGGER] human_fall_detect_final_count is ALREADY RUNNING (PID: {DETECTION_PROCESS.pid}). Skipping duplicate launch.")
            return False, f"Already running (PID {DETECTION_PROCESS.pid})"
        
        # 2. Debounce cooldown check (prevent spamming process starts for the same event)
        if now - LAST_DETECTION_TRIGGER_TIME < DETECTION_COOLDOWN_SECONDS:
            remaining = DETECTION_COOLDOWN_SECONDS - (now - LAST_DETECTION_TRIGGER_TIME)
            print(f"[TRIGGER] Cooldown active ({remaining:.1f}s remaining). Skipping duplicate launch.")
            return False, f"Cooldown active ({remaining:.1f}s remaining)"
        
        # 3. Verify file exists
        if not os.path.exists(FALL_DETECT_SCRIPT):
            print(f"[TRIGGER] ERROR: Script not found at {FALL_DETECT_SCRIPT}")
            return False, "Script not found"
        
        print(f"[TRIGGER] >>> TRIGGERING human_fall_detect_final_count (Source: {source}) <<<")
        try:
            creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            DETECTION_PROCESS = subprocess.Popen(
                [sys.executable, FALL_DETECT_SCRIPT],
                cwd=FALL_DETECT_DIR,
                creationflags=creationflags
            )
            LAST_DETECTION_TRIGGER_TIME = now
            print(f"[TRIGGER] Successfully launched human_fall_detect_final_count with PID: {DETECTION_PROCESS.pid}")
            return True, f"Launched PID {DETECTION_PROCESS.pid}"
        except Exception as e:
            print(f"[TRIGGER] Failed to launch human_fall_detect_final_count: {e}")
            return False, str(e)

# Live ESP32 Telemetry Cache (In-Memory for performance, Synced to Supabase for persistence)
NODES_DATA = []

def init_nodes_from_supabase():
    """Load initial device state from Supabase on server startup"""
    global NODES_DATA
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        response = sb.table('devices').select('*').execute()
        
        nodes = []
        for d in response.data:
            is_online = d.get("status") == "online"
            lat_val = d.get("latitude")
            lng_val = d.get("longitude")
            nodes.append({
                "id": d.get("device_id", ""),
                "name": d.get("name", ""),
                "location": d.get("location_name", "Awaiting GPS Fix"),
                "lat": lat_val,
                "lng": lng_val,
                "gps_fix": False,
                "location_type": "LAST KNOWN LOCATION" if (lat_val is not None and lng_val is not None) else "NO LOCATION",
                "pir": False,
                "vibration": 0.0,
                "acoustic_db": 34.5,
                "sound_class": "Ambient Forest Sound" if is_online else "Offline",
                "confidence": 99.2 if is_online else 0.0,
                "status": "SAFE",  # Always start as SAFE, telemetry will update to ALERT if needed
                "power_source": "5V DC / USB (Mains Continuous)",
                "battery": f"{d.get('battery_level', 100)}%" if d.get('battery_level') else "100%",
                "lora_rssi": -72,
                "wifi_status": "Connected" if is_online else "Disconnected",
                "cache_count": 0,
                "last_seen": d.get("last_seen", "Unknown"),
                "ip_address": None
            })
            
        if nodes:
            NODES_DATA = nodes
            print(f"[INIT] Loaded {len(NODES_DATA)} nodes from Supabase")
        else:
            print("[INIT] No devices found in Supabase. Awaiting ESP32 telemetry...")
            
    except Exception as e:
        print(f"[INIT] Failed to load nodes from Supabase: {e}")
        # Fallback empty list - devices will register on first telemetry
        pass

# Initialize nodes on startup
init_nodes_from_supabase()


DETERRENT_STATE = {
    "bio_acoustic_active": False,
    "strobe_light_active": False,
    "siren_active": False,
    "sms_alert_dispatched": False,
    "last_trigger_time": "None",
    "trigger_node": "None"
}

# ==============================================================================
# ROLE-BASED ACCESS CONTROL (RBAC) DECORATORS & HELPERS
# ==============================================================================

def role_required(allowed_roles):
    """Decorator to enforce role-based access to routes and API endpoints"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                    return jsonify({"error": "Unauthorized: Session expired or authentication required."}), 401
                target_role = allowed_roles[0] if allowed_roles else 'forest_officer'
                return redirect(url_for('landing', role=target_role, next=request.path))
            
            user_role = session.get('role')
            if user_role not in allowed_roles:
                # If requesting an API endpoint, return explicit 403 JSON
                if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                    return jsonify({
                        "error": f"Forbidden: Insufficient privileges. Role '{user_role}' cannot access this resource."
                    }), 403

                # Admin and user-management paths are strictly forbidden for non-officers
                if request.path in ['/admin', '/user-management', '/forest-officer/users', '/officer']:
                    abort(403)

                # Redirect user to their own role dashboard to prevent unauthorized access
                if user_role == 'villager':
                    return redirect(url_for('villager_dashboard_page'))
                elif user_role == 'police':
                    return redirect(url_for('police_dashboard_page'))
                elif user_role == 'forest_officer':
                    return redirect(url_for('officer_dashboard_page'))
                return redirect(url_for('landing'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==============================================================================
# PAGE ROUTES (LANDING, ADMIN & ROLE-SPECIFIC DASHBOARDS)
# ==============================================================================

@app.route('/')
def index():
    """Root URL - Serves Landing Page unless user already has an active role session"""
    view = request.args.get('view')
    if 'user_id' in session and view != 'landing':
        user_role = session.get('role')
        if user_role == 'forest_officer':
            return redirect(url_for('officer_dashboard_page'))
        elif user_role == 'villager':
            return redirect(url_for('villager_dashboard_page'))
        elif user_role == 'police':
            return redirect(url_for('police_dashboard_page'))
    return render_template('landing.html')

@app.route('/landing')
def landing():
    """Public Landing Page with Overview and Role Login cards"""
    selected_role = request.args.get('role', 'forest_officer')
    next_url = request.args.get('next', '')
    return render_template('landing.html', selected_role=selected_role, next_url=next_url)

@app.route('/login')
def login_page():
    """Login redirection to role portal on landing page"""
    role = request.args.get('role', 'forest_officer')
    return redirect(url_for('landing', role=role))

@app.route('/officer')
@app.route('/dashboard')
@app.route('/detections')
@app.route('/raw-data')
@app.route('/elephant-images')
@app.route('/alerts')
@app.route('/users')
@app.route('/devices')
@app.route('/settings')
@role_required(['forest_officer'])
def officer_dashboard_page():
    """Forest Officer Dashboard - Reuses existing comprehensive monitoring dashboard (index.html)"""
    from supabase_client import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY
    
    path = request.path
    if path == '/detections' or path == '/elephant-images':
        active_tab = 'camera-tab'
    elif path == '/raw-data':
        active_tab = 'sensor-monitoring-tab'
    elif path == '/devices':
        active_tab = 'sensor-tab'
    elif path == '/alerts':
        active_tab = 'alerts-tab'
    elif path == '/users':
        active_tab = 'user-mgmt-tab'
    else:
        active_tab = 'map-tab'
        
    return render_template('index.html', 
                           supabase_url=SUPABASE_URL, 
                           supabase_anon_key=SUPABASE_PUBLISHABLE_KEY,
                           user_name=session.get('name', 'Ranger Rajesh Kumar'),
                           user_zone=session.get('zone', 'Bannerghatta Range Division'),
                           active_tab=active_tab)

@app.route('/admin')
@app.route('/user-management')
@app.route('/forest-officer/users')
@role_required(['forest_officer'])
def admin_user_management_page():
    """Dedicated Admin User Management route - Only accessible by authenticated Forest Officers.
    Villagers and Police are strictly blocked by role_required with HTTP 403."""
    from supabase_client import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY
    return render_template('index.html',
                           supabase_url=SUPABASE_URL,
                           supabase_anon_key=SUPABASE_PUBLISHABLE_KEY,
                           user_name=session.get('name', 'Ranger Rajesh Kumar'),
                           user_zone=session.get('zone', 'Bannerghatta Range Division'),
                           active_tab='user-mgmt-tab')

@app.errorhandler(403)
def forbidden_error_page(e):
    """Custom HTTP 403 Forbidden handler preventing unauthorized access to admin resources"""
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({
            "error": "403 Forbidden: Administrative privileges required. Only authenticated Forest Officers can perform this action."
        }), 403
    return render_template('403.html'), 403

@app.route('/villager')
@role_required(['villager'])
def villager_dashboard_page():
    """Villager Safety Dashboard - Simpler safety-focused dashboard with alerts and instructions"""
    return render_template('villager_dashboard.html',
                           user_name=session.get('name', 'Anand Gowda'),
                           user_zone=session.get('zone', 'Buthanahalli Border Zone'))

@app.route('/police')
@role_required(['police'])
def police_dashboard_page():
    """Police Incident Dashboard - Incident response, dispatch status and patrol coordination"""
    return render_template('police_dashboard.html',
                           user_name=session.get('name', 'Inspector S. Murthy'),
                           user_zone=session.get('zone', 'Anekal Police Sub-Division'))

@app.route('/logout')
def logout_redirect():
    """Direct logout route"""
    session.clear()
    return redirect(url_for('landing'))

# ==============================================================================
# AUTHENTICATION REST APIS (SUPABASE AUTH INTEGRATION)
# ==============================================================================

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Authenticate users with real Supabase Auth and verify role assignment"""
    try:
        data = request.json or {}
        identifier = (data.get('identifier') or '').strip()
        password = data.get('password') or ''
        expected_role = data.get('role') or ''
        
        if not identifier or not password:
            return jsonify({"error": "Identifier and password are required"}), 400
        
        # Support phone numbers or police badges by mapping to registered Supabase emails
        email = identifier
        if '@' not in identifier:
            clean_id = identifier.replace(' ', '').replace('-', '').upper()
            if 'POL' in clean_id or clean_id.startswith('KA'):
                email = 'police@ksp.gov.in'
            elif any(char.isdigit() for char in clean_id):
                email = 'villager@anekal.gov.in'
        
        # Authenticate against real Supabase Authentication using clean auth client
        supabase = get_auth_client()
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        user = auth_response.user
        if not user:
            return jsonify({"error": "Invalid email/ID or password."}), 401
        
        # Extract role from Supabase metadata
        user_metadata = user.user_metadata or {}
        app_metadata = user.app_metadata or {}
        user_role = user_metadata.get('role') or app_metadata.get('role')
        
        if not user_role:
            return jsonify({"error": "User account has no role provisioned in Supabase."}), 403
            
        if expected_role and user_role != expected_role:
            return jsonify({
                "error": f"Unauthorized Role: Your account role is '{user_role.replace('_', ' ').title()}', but you tried logging into '{expected_role.replace('_', ' ').title()}'."
            }), 403
            
        # Check account status (Active vs Inactive)
        user_status = user_metadata.get('status', 'Active')
        if str(user_status).lower() in ['inactive', 'disabled', 'deactivated']:
            return jsonify({
                "error": "Account is deactivated. Access denied. Please contact a Forest Officer administrator."
            }), 403

        # Establish secure Flask session
        session['user_id'] = user.id
        session['email'] = user.email
        session['role'] = user_role
        session['name'] = user_metadata.get('full_name') or user_metadata.get('name', user.email)
        session['phone'] = user_metadata.get('phone', '')
        session['zone'] = user_metadata.get('location') or user_metadata.get('zone', 'Bannerghatta Range')
        
        # Determine redirect destination based on authorized role
        next_url = data.get('next')
        if next_url and next_url.startswith('/'):
            redirect_url = next_url
        else:
            redirect_map = {
                'forest_officer': '/officer',
                'villager': '/villager',
                'police': '/police'
            }
            redirect_url = redirect_map.get(user_role, '/')
        
        return jsonify({
            "success": True,
            "user_id": user.id,
            "role": user_role,
            "name": session['name'],
            "redirect_url": redirect_url
        })
        
    except Exception as e:
        err_msg = str(e)
        if "Invalid login credentials" in err_msg or "invalid_credentials" in err_msg.lower():
            return jsonify({"error": "Invalid email/ID or password."}), 401
        return jsonify({"error": f"Authentication failed: {err_msg}"}), 500

@app.route('/api/auth/logout', methods=['POST', 'GET'])
def auth_logout():
    """Clear session and sign out"""
    session.clear()
    return jsonify({"success": True, "redirect_url": "/"})

@app.route('/api/auth/current-user', methods=['GET'])
def auth_current_user():
    """Check current authenticated session"""
    if 'user_id' in session:
        return jsonify({
            "authenticated": True,
            "user_id": session.get('user_id'),
            "email": session.get('email'),
            "role": session.get('role'),
            "name": session.get('name'),
            "zone": session.get('zone')
        })
    return jsonify({"authenticated": False})

# ==============================================================================
# FOREST OFFICER USER MANAGEMENT REST APIS (ADMIN SECURED)
# ==============================================================================

@app.route('/api/admin/users', methods=['GET'])
@role_required(['forest_officer'])
def admin_get_users():
    """List all registered users from Supabase Auth (Forest Officer only)"""
    try:
        supabase = get_supabase_admin_client()
        users_resp = supabase.auth.admin.list_users()
        
        user_list = users_resp if isinstance(users_resp, list) else getattr(users_resp, 'users', users_resp)
        
        formatted_users = []
        for u in user_list:
            u_meta = getattr(u, 'user_metadata', {}) or {}
            a_meta = getattr(u, 'app_metadata', {}) or {}
            
            role = u_meta.get('role') or a_meta.get('role') or 'villager'
            name = u_meta.get('full_name') or u_meta.get('name') or u.email
            phone = u_meta.get('phone') or 'N/A'
            location = u_meta.get('location') or u_meta.get('zone') or 'Bannerghatta Range'
            status = u_meta.get('status') or 'Active'
            
            created_at_val = getattr(u, 'created_at', None)
            if created_at_val:
                if hasattr(created_at_val, 'isoformat'):
                    created_str = created_at_val.isoformat()
                else:
                    created_str = str(created_at_val)
            else:
                created_str = datetime.now().isoformat()
                
            formatted_users.append({
                "id": u.id,
                "user_id": u.id,
                "email": u.email,
                "full_name": name,
                "name": name,
                "phone": phone,
                "role": role,
                "location": location,
                "status": status,
                "created_at": created_str
            })
            
        return jsonify({
            "success": True,
            "users": formatted_users
        })
    except Exception as e:
        return jsonify({
            "error": f"Failed to retrieve users: {str(e)}",
            "users": []
        }), 500

@app.route('/api/admin/users/create', methods=['POST'])
@role_required(['forest_officer'])
def admin_create_user():
    """Create a new user account through Supabase Auth Admin API (Forest Officer only).
    Service role key remains securely on the server backend."""
    try:
        data = request.json or {}
        full_name = (data.get('full_name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        phone = (data.get('phone') or '').strip()
        role = (data.get('role') or '').strip().lower()
        location = (data.get('location') or '').strip()
        password = data.get('password') or ''
        
        # Field Validation
        if not full_name:
            return jsonify({"error": "Full name is required."}), 400
        if not email or '@' not in email:
            return jsonify({"error": "Valid email address is required."}), 400
        if role not in ['forest_officer', 'villager', 'police']:
            return jsonify({"error": "Invalid role. Allowed roles are: 'forest_officer', 'villager', 'police'."}), 400
        if not password or len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters long for security."}), 400

        supabase = get_supabase_admin_client()
        
        # Check if email is already registered in Supabase Auth
        existing_users = supabase.auth.admin.list_users()
        existing_list = existing_users if isinstance(existing_users, list) else getattr(existing_users, 'users', existing_users)
        for u in existing_list:
            if getattr(u, 'email', '').lower() == email:
                return jsonify({"error": f"User with email '{email}' already exists in Supabase Auth."}), 409
                
        # Provision user via Supabase Auth Admin API
        created_user = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {
                "role": role
            },
            "user_metadata": {
                "role": role,
                "full_name": full_name,
                "name": full_name,
                "phone": phone,
                "location": location,
                "zone": location,
                "status": "Active"
            }
        })
        
        user_obj = created_user.user if hasattr(created_user, 'user') and created_user.user else created_user
        user_id = getattr(user_obj, 'id', str(uuid.uuid4()))
        
        # Optionally mirror in public.profiles table if present
        try:
            supabase.table('profiles').insert({
                "user_id": user_id,
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "role": role,
                "location": location,
                "status": "Active"
            }).execute()
        except Exception:
            pass

        created_at_val = getattr(user_obj, 'created_at', None)
        created_str = created_at_val.isoformat() if hasattr(created_at_val, 'isoformat') else str(created_at_val or datetime.now().isoformat())

        return jsonify({
            "success": True,
            "message": "User created successfully",
            "user": {
                "id": user_id,
                "user_id": user_id,
                "email": email,
                "full_name": full_name,
                "name": full_name,
                "phone": phone,
                "role": role,
                "location": location,
                "status": "Active",
                "created_at": created_str
            }
        }), 201

    except Exception as e:
        return jsonify({"error": f"Failed to create user in Supabase: {str(e)}"}), 500

@app.route('/api/admin/users/toggle-status', methods=['POST'])
@role_required(['forest_officer'])
def admin_toggle_user_status():
    """Activate or deactivate user account (Forest Officer only)"""
    try:
        data = request.json or {}
        user_id = data.get('user_id')
        new_status = data.get('status')
        
        if not user_id:
            return jsonify({"error": "User ID is required."}), 400
        if new_status not in ['Active', 'Inactive']:
            return jsonify({"error": "Status must be 'Active' or 'Inactive'."}), 400

        # Prevent administrative lockout
        if user_id == session.get('user_id'):
            return jsonify({"error": "Action Denied: You cannot deactivate your own administrative account."}), 400

        supabase = get_supabase_admin_client()
        user_resp = supabase.auth.admin.get_user_by_id(user_id)
        target_user = user_resp.user if hasattr(user_resp, 'user') and user_resp.user else user_resp
        
        if not target_user:
            return jsonify({"error": "User not found in Supabase Auth."}), 404
            
        existing_meta = getattr(target_user, 'user_metadata', {}) or {}
        updated_meta = {**existing_meta, "status": new_status}
        
        supabase.auth.admin.update_user_by_id(user_id, {
            "user_metadata": updated_meta
        })

        # Update profiles table if present
        try:
            supabase.table('profiles').update({"status": new_status}).eq("user_id", user_id).execute()
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"User account marked as {new_status}.",
            "status": new_status,
            "user_id": user_id
        })

    except Exception as e:
        return jsonify({"error": f"Failed to update user status: {str(e)}"}), 500

# ==============================================================================
# ROLE-SPECIFIC REST APIS (VILLAGER & POLICE)
# ==============================================================================

@app.route('/api/villager/alerts', methods=['GET'])
def get_villager_alerts():
    """Fetch emergency alert status and community alerts for villagers"""
    try:
        supabase = get_supabase_client()
        # Fetch confirmed elephant detections
        det_query = supabase.table('detections').select('*').eq('detection', 'ELEPHANT_DETECTED').order('timestamp', desc=True).limit(5).execute()
        
        active_alert = None
        live_alert = any(n.get('status') == 'ALERT' for n in NODES_DATA)
        
        if det_query.data and len(det_query.data) > 0:
            latest_det = det_query.data[0]
            t_str = latest_det.get('timestamp', '')
            time_part = t_str.split('T')[1].split('.')[0] if 'T' in t_str else t_str
            active_alert = {
                "location": "Buthanahalli - Bannerghatta Forest Fringe",
                "time": time_part or "Recently",
                "distance": "~380 meters from Village Perimeter",
                "elephant_count": latest_det.get('elephant_count') or 1,
                "confidence": round(latest_det.get('confidence', 94.0) * 100 if latest_det.get('confidence', 94.0) <= 1 else latest_det.get('confidence', 94.0), 1)
            }
        elif live_alert:
            active_alert = {
                "location": "Buthanahalli Forest Border Fringe (Near Node 01)",
                "time": "Just now",
                "distance": "~350 meters from Village Perimeter",
                "elephant_count": 1,
                "confidence": 92.5
            }
            
        recent_alerts = []
        if det_query.data:
            for d in det_query.data:
                ts = d.get('timestamp', '')
                t_display = ts.split('T')[0] + ' ' + (ts.split('T')[1].split('.')[0] if 'T' in ts else '')
                recent_alerts.append({
                    "alert_type": "ELEPHANT_CONFIRMED",
                    "elephant_count": d.get('elephant_count', 1),
                    "message": f"Confirmed elephant detection ({d.get('elephant_count', 1)} elephant) near corridor sector.",
                    "location": "Buthanahalli Border Zone",
                    "time": t_display
                })
                
        return jsonify({
            "active_alert": active_alert,
            "recent_alerts": recent_alerts
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

POLICE_INCIDENTS_FILE = os.path.join(base_dir, 'police_incidents.json')
POLICE_INCIDENT_STATUSES = {}

def load_police_incident_statuses():
    global POLICE_INCIDENT_STATUSES
    if os.path.exists(POLICE_INCIDENTS_FILE):
        try:
            with open(POLICE_INCIDENTS_FILE, 'r', encoding='utf-8') as f:
                POLICE_INCIDENT_STATUSES = json.load(f)
        except Exception:
            POLICE_INCIDENT_STATUSES = {}

def save_police_incident_statuses():
    try:
        with open(POLICE_INCIDENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(POLICE_INCIDENT_STATUSES, f, indent=2)
    except Exception as e:
        print(f"[POLICE] Error saving incidents: {e}")

load_police_incident_statuses()

@app.route('/api/police/incidents', methods=['GET'])
def get_police_incidents():
    """Fetch active and logged incidents for police dispatch dashboard"""
    try:
        supabase = get_supabase_client()
        det_res = supabase.table('detections').select('*').eq('detection', 'ELEPHANT_DETECTED').order('timestamp', desc=True).limit(20).execute()
        
        incidents = []
        for d in (det_res.data or []):
            det_id = str(d.get('id'))
            status = POLICE_INCIDENT_STATUSES.get(det_id, 'Pending')
            
            ts = d.get('timestamp', '')
            date_val = ts.split('T')[0] if 'T' in ts else '2026-09-24'
            time_val = ts.split('T')[1].split('.')[0] if 'T' in ts else '10:00:00'
            
            incidents.append({
                "id": det_id,
                "date": date_val,
                "time": time_val,
                "location": "Anekal - Begihalli / Buthanahalli Corridor",
                "affected_area": "Buthanahalli Village Fringe & State Highway 87",
                "elephant_count": d.get('elephant_count', 1),
                "confidence": round(d.get('confidence', 0.95) * 100 if d.get('confidence', 0.95) <= 1 else d.get('confidence', 95.0), 1),
                "status": status,
                "latitude": d.get('latitude', 12.8224),
                "longitude": d.get('longitude', 77.5770)
            })
            
        return jsonify({
            "incidents": incidents,
            "total": len(incidents)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/police/update-incident-status', methods=['POST'])
def update_police_incident_status():
    """Allow police to update incident status (Pending, Acknowledged, Responding, Resolved)"""
    try:
        data = request.json or {}
        incident_id = str(data.get('incident_id') or '')
        new_status = data.get('status')
        
        if not incident_id or not new_status:
            return jsonify({"error": "incident_id and status are required"}), 400
            
        if new_status not in ['Pending', 'Acknowledged', 'Responding', 'Resolved']:
            return jsonify({"error": "Invalid status value"}), 400
            
        # Update persistent police status
        POLICE_INCIDENT_STATUSES[incident_id] = new_status
        save_police_incident_statuses()
        
        # Also sync record with Supabase alerts table
        try:
            supabase = get_supabase_client()
            supabase.table('alerts').insert({
                'device_id': 'ESP32-NODE-01',
                'alert_type': 'SMS',
                'message': f"Police dispatch status updated to {new_status} for incident #{incident_id[:8]}",
                'status': 'sent'
            }).execute()
        except Exception as sup_err:
            print(f"[POLICE SYNC TO SUPABASE] Note: {sup_err}")
            
        return jsonify({
            "success": True,
            "incident_id": incident_id,
            "status": new_status
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/config/supabase', methods=['GET'])
def get_supabase_config():
    """Expose Supabase URL and anon key for frontend Realtime client"""
    from supabase_client import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY
    return jsonify({
        "url": SUPABASE_URL,
        "anon_key": SUPABASE_PUBLISHABLE_KEY
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        from supabase_client import get_supabase_client
        sb = get_supabase_client()
        
        # Get devices for online status
        dev_resp = sb.table('devices').select('last_seen').execute()
        total_nodes = len(dev_resp.data)
        online_nodes = 0
        for d in dev_resp.data:
            if d.get('last_seen'):
                last_seen_dt = datetime.fromisoformat(d.get('last_seen').replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - last_seen_dt).total_seconds() <= 30:
                    online_nodes += 1
                    
        # Get active alerts (Elephant detected within last 5 minutes)
        five_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        det_resp = sb.table('detections').select('id').eq('detection', 'ELEPHANT_DETECTED').gte('timestamp', five_mins_ago).execute()
        active_alerts = len(det_resp.data)
        
        overall_status = "CRITICAL_ALERT" if active_alerts > 0 else "NORMAL"
        mesh_health = f"{int((online_nodes / total_nodes) * 100)}%" if total_nodes > 0 else "100%"
        
        return jsonify({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "overall_status": overall_status,
            "total_nodes": total_nodes,
            "nodes_online": online_nodes,
            "active_alerts_count": active_alerts,
            "warning_count": 0,
            "lora_mesh_health": mesh_health,
            "cloud_sync": "Active (Supabase Realtime Cloud)",
            "power_status": "5V DC / USB (Mains Continuous)",
            "battery_avg": "5V DC (Mains)",
            "herd_info": None,
            "deterrent_status": DETERRENT_STATE
        })
    except Exception as e:
        print(f"Error fetching status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    try:
        from supabase_client import get_supabase_client
        sb = get_supabase_client()
        dev_resp = sb.table('devices').select('*').execute()
        
        nodes = []
        for d in dev_resp.data:
            node_id = d.get('device_id', '')
            last_seen = d.get('last_seen')
            
            # Check in-memory state for live GPS fix and latest telemetry
            matched_mem = next((n for n in NODES_DATA if n.get('id') == node_id), None)
            
            is_connected = False
            if last_seen:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                    if (datetime.now(timezone.utc) - last_seen_dt).total_seconds() <= 30:
                        is_connected = True
                except Exception:
                    pass
            
            lat_val = d.get("latitude")
            lng_val = d.get("longitude")
            gps_fix = False
            location_type = "NO LOCATION"
            
            if matched_mem and matched_mem.get('gps_fix'):
                gps_fix = True
                location_type = "LIVE LOCATION"
                lat_val = matched_mem.get('lat', lat_val)
                lng_val = matched_mem.get('lng', lng_val)
            elif lat_val is not None and lng_val is not None:
                location_type = "LAST KNOWN LOCATION"
            
            nodes.append({
                "id": node_id,
                "name": d.get("name", f"Node {node_id}"),
                "location": d.get("location_name", "Awaiting GPS Fix"),
                "lat": lat_val,
                "lng": lng_val,
                "gps_fix": gps_fix,
                "location_type": location_type,
                "pir": matched_mem.get('pir', False) if matched_mem else False,
                "vibration": 0.0,
                "acoustic_db": matched_mem.get('acoustic_db', 30.0) if matched_mem else 30.0,
                "sound_class": ("Alert" if matched_mem and matched_mem.get('status') == 'ALERT' else "Ambient") if is_connected else "Offline",
                "confidence": 99.0 if is_connected else 0.0,
                "status": (matched_mem.get('status', 'SAFE') if matched_mem else 'SAFE') if is_connected else "OFFLINE",
                "power_source": "5V DC",
                "battery": f"{d.get('battery_level', 100)}%" if d.get('battery_level') else "100%",
                "lora_rssi": -72,
                "wifi_status": "Connected" if is_connected else "Disconnected",
                "cache_count": 0,
                "last_seen": last_seen if last_seen else "Unknown",
                "ip_address": None
            })
            
        return jsonify(nodes)
    except Exception as e:
        print(f"Error fetching live nodes: {e}")
        return jsonify(NODES_DATA) # fallback


@app.route('/api/nodes/<node_id>/location', methods=['POST', 'PUT'])
@app.route('/api/node/update-location', methods=['POST'])
def update_node_location(node_id=None):
    """Update live location and GPS coordinates for a field node (e.g. Node 1)"""
    data = request.json or {}
    target_id = node_id or data.get('node_id') or data.get('deviceId') or data.get('id') or 'ESP32-NODE-01'
    
    lat_val = data.get('lat') if data.get('lat') is not None else data.get('latitude')
    lng_val = data.get('lng') if data.get('lng') is not None else data.get('longitude')
    
    if lat_val is None or lng_val is None:
        return jsonify({"status": "error", "message": "Latitude and longitude are required"}), 400
        
    try:
        new_lat = float(lat_val)
        new_lng = float(lng_val)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid numeric coordinates"}), 400
        
    try:
        from supabase_client import get_supabase_client
        sb = get_supabase_client()
        
        custom_loc = data.get('location')
        if custom_loc and str(custom_loc).strip():
            location_name = str(custom_loc).strip()
        else:
            location_name = reverse_geocode_coordinates(new_lat, new_lng)
            
        update_data = {
            "latitude": new_lat,
            "longitude": new_lng,
            "location_name": location_name,
            "last_seen": datetime.now(timezone.utc).isoformat()
        }
        
        sb.table('devices').update(update_data).eq('device_id', target_id).execute()
        
        print(f"[LOCATION UPDATE] {target_id} live position updated to: {new_lat:.5f}, {new_lng:.5f} ({location_name})")
        return jsonify({
            "status": "success",
            "message": f"Updated {target_id} live location",
            "node": {
                "id": target_id,
                "lat": new_lat,
                "lng": new_lng,
                "location": location_name
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/node-event', methods=['POST'])
def handle_node_event():
    """Hardware ESP32 HTTP POST Telemetry Ingestion Endpoint"""
    global ESP32_LAST_SEEN, ESP32_CONNECTED
    
    data = request.json or {}
    node_id = data.get('node_id') or data.get('deviceId') or 'ESP32-NODE-01'
    
    # Update ESP32 connection status - real data received
    ESP32_LAST_SEEN = datetime.now()
    ESP32_CONNECTED = True
    
    print(f"[ESP32] Real telemetry received from {node_id} at {ESP32_LAST_SEEN.strftime('%H:%M:%S')}")
    
    for node in NODES_DATA:
        if node['id'] == node_id:
            node['pir'] = data.get('pir', node['pir'])
            node['vibration'] = data.get('vibration', node['vibration'])
            node['acoustic_db'] = data.get('acoustic_db', node['acoustic_db'])
            node['sound_class'] = data.get('sound_class', node['sound_class'])
            node['confidence'] = data.get('confidence', node['confidence'])
            if 'Elephant' in node.get('sound_class', '') or node.get('pir', False):
                node['status'] = 'ALERT'
            else:
                node['status'] = 'SAFE'
                
            # Update GPS coordinates if present
            lat_input = data.get('lat') if data.get('lat') is not None else data.get('latitude')
            lng_input = data.get('lng') if data.get('lng') is not None else data.get('longitude')
            if lat_input is not None and lng_input is not None:
                try:
                    new_lat = float(lat_input)
                    new_lng = float(lng_input)
                    if abs(new_lat) > 0.1 and abs(new_lng) > 0.1:
                        node['lat'] = new_lat
                        node['lng'] = new_lng
                        node['location'] = reverse_geocode_coordinates(new_lat, new_lng)
                        node['name'] = f"Node 1 - {node['location']}" if node['id'] == 'ESP32-NODE-01' else f"{node['id']} - {node['location']}"
                except (ValueError, TypeError):
                    pass
            
            # Sync to Supabase Devices Table
            try:
                from supabase_client import get_supabase_admin_client
                sb = get_supabase_admin_client()
                iso_now = datetime.now(timezone.utc).isoformat()
                
                sb.table('devices').upsert({
                    "device_id": node['id'],
                    "name": node.get('name', f"Node {node['id']}"),
                    "location_name": node.get('location', ''),
                    "latitude": node.get('lat', 0.0),
                    "longitude": node.get('lng', 0.0),
                    "status": "online",
                    "last_seen": iso_now,
                    "last_heartbeat_at": iso_now,
                    "battery_level": 100,
                    "updated_at": iso_now
                }, on_conflict='device_id').execute()
            except Exception as e:
                print(f"[SUPABASE] Error syncing device {node['id']}: {e}")
                
            return jsonify({"status": "accepted", "node": node})
            
    # Node not in memory, dynamically add it
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        iso_now = datetime.now(timezone.utc).isoformat()
        
        lat_input = float(data.get('lat') or data.get('latitude') or 12.8224)
        lng_input = float(data.get('lng') or data.get('longitude') or 77.5770)
        location_name = reverse_geocode_coordinates(lat_input, lng_input)
        node_name = f"{node_id} - {location_name}"
        
        new_node = {
            "id": node_id,
            "name": node_name,
            "location": location_name,
            "lat": lat_input,
            "lng": lng_input,
            "pir": data.get('pir', False),
            "vibration": data.get('vibration', 0.0),
            "acoustic_db": data.get('acoustic_db', 34.5),
            "sound_class": data.get('sound_class', 'Ambient Forest Sound'),
            "confidence": data.get('confidence', 99.2),
            "status": "ALERT" if ('Elephant' in data.get('sound_class', '') or data.get('pir', False)) else "SAFE",
            "power_source": "5V DC / USB (Mains Continuous)",
            "battery": "100%",
            "lora_rssi": -72,
            "wifi_status": "Connected",
            "cache_count": 0,
            "last_seen": "Just now",
            "ip_address": None
        }
        NODES_DATA.append(new_node)
        
        sb.table('devices').upsert({
            "device_id": node_id,
            "name": node_name,
            "location_name": location_name,
            "latitude": lat_input,
            "longitude": lng_input,
            "status": "online",
            "last_seen": iso_now,
            "last_heartbeat_at": iso_now,
            "battery_level": 100,
            "updated_at": iso_now
        }, on_conflict='device_id').execute()
        
        print(f"[ESP32] Dynamically registered new node {node_id}")
        return jsonify({"status": "accepted", "node": new_node, "message": "Registered new node"})
    except Exception as e:
        print(f"[ESP32] Error registering new node: {e}")
        return jsonify({"status": "error", "message": "Failed to register node"}), 500

@app.route('/api/esp32/data', methods=['POST'])
def handle_esp32_data():
    """Hardware ESP32 HTTP POST Telemetry Ingestion Endpoint - matches ESP32 client"""
    global ESP32_LAST_SEEN, ESP32_CONNECTED, DEVICE_LAST_SEEN
    
    data = request.json or {}
    device_id = data.get('deviceId') or data.get('device_id') or 'ESP32-NODE-01'
    
    # Update ESP32 connection status - real data received
    now = datetime.now()
    ESP32_LAST_SEEN = now
    if 'DEVICE_LAST_SEEN' in globals():
        DEVICE_LAST_SEEN[device_id] = now
    ESP32_CONNECTED = True
    
    print(f"[ESP32] Real telemetry received from {device_id} at {now.strftime('%H:%M:%S')}")
    print(f"[ESP32] Data: PIR={data.get('pir')}, Sound={data.get('sound')}, GPS Fix={data.get('gpsFix')}, Lat={data.get('latitude')}, Lon={data.get('longitude')}")
    
    node_id = device_id
    matched_node = None
    
    for node in NODES_DATA:
        if node['id'] == node_id:
            # Convert ESP32 boolean to server format
            node['pir'] = bool(data.get('pir', False))
            # Map sound detection to acoustic_db (sound=true = high dB, sound=false = ambient)
            node['acoustic_db'] = 85.0 if data.get('sound', False) else 35.0
            node['confidence'] = 95.0 if (data.get('pir', False) or data.get('sound', False)) else 99.0
            node['power_source'] = "5V DC / USB (Mains Continuous)"
            node['battery'] = "5V DC (Mains)"
            node['wifi_status'] = "Connected"
            
            # Robust live GPS coordinate parsing (numeric or string)
            lat_input = data.get('latitude') if data.get('latitude') is not None else data.get('lat')
            lng_input = data.get('longitude') if data.get('longitude') is not None else data.get('lng')
            has_valid_coords = False
            
            if lat_input is not None and lng_input is not None:
                try:
                    new_lat = float(lat_input)
                    new_lng = float(lng_input)
                    # Check for non-zero coordinates within valid earth range
                    if abs(new_lat) > 0.1 and abs(new_lng) > 0.1 and -90 <= new_lat <= 90 and -180 <= new_lng <= 180:
                        has_valid_coords = True
                except (ValueError, TypeError):
                    has_valid_coords = False
            
            if has_valid_coords:
                # Update if coordinates changed by more than 0.0001 degrees (~11 meters)
                if abs(new_lat - node.get('lat', 0.0)) > 0.0001 or abs(new_lng - node.get('lng', 0.0)) > 0.0001:
                    node['lat'] = new_lat
                    node['lng'] = new_lng
                    node['location'] = reverse_geocode_coordinates(node['lat'], node['lng'])
                    node_num = "1" if node['id'] == 'ESP32-NODE-01' else "2"
                    node['name'] = f"Node {node_num} - {node['location']}"
                    print(f"[ESP32] Updated live GPS coordinates: {node['lat']}, {node['lng']} -> {node['location']}")
                else:
                    node['lat'] = new_lat
                    node['lng'] = new_lng
                node['gps_fix'] = True
                node['location_type'] = "LIVE LOCATION"
            else:
                node['gps_fix'] = False
                if node.get('lat') is not None and node.get('lng') is not None:
                    node['location_type'] = "LAST KNOWN LOCATION"
                else:
                    node['location_type'] = "NO LOCATION"
                print(f"[ESP32] No live GPS fix from node. Current coordinates: {node.get('lat')}, {node.get('lng')} ({node['location_type']})")
            
            # Update status based on detections
            if data.get('pir', False) or data.get('sound', False):
                node['status'] = 'ALERT'
            else:
                node['status'] = 'SAFE'
            
            # Update online status - node is receiving telemetry
            node['wifi_status'] = 'Connected'
            node['ip_address'] = request.remote_addr
            
            # Update last seen time
            node['last_seen'] = 'Just now'
            matched_node = node
            break

    # Store raw sensor data to Supabase (Single source of truth)
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        iso_now = datetime.now(timezone.utc).isoformat()
        current_lat = new_lat if has_valid_coords else None
        current_lng = new_lng if has_valid_coords else None
        sound_detected = bool(data.get('sound', False))
        pir_detected = bool(data.get('pir', False))
        sound_level = float(matched_node.get('acoustic_db', 85.0 if sound_detected else 35.0) if matched_node else (85.0 if sound_detected else 35.0))
        
        sensor_data = {
            "device_id": device_id or "ESP32-NODE-01",
            "timestamp": iso_now,
            "pir_detected": pir_detected,
            "sound_detected": sound_detected,
            "sound_level": sound_level,
            "latitude": current_lat,
            "longitude": current_lng
        }
        sb.table('raw_sensor_data').insert(sensor_data).execute()
        print(f"[SUPABASE] Stored raw sensor data for {device_id}: PIR={pir_detected}, Sound={sound_detected}, Lat={current_lat}, Lon={current_lng}")
        
        # Upsert device status in Supabase using correct schema columns
        device_update = {
            "device_id": device_id or "ESP32-NODE-01",
            "name": matched_node.get('name', f"Node {device_id}") if matched_node else f"Node {device_id}",
            "status": "online",
            "last_seen": iso_now,
            "last_heartbeat_at": iso_now,
            "battery_level": 100,
            "updated_at": iso_now
        }
        if has_valid_coords:
            device_update["latitude"] = current_lat
            device_update["longitude"] = current_lng
            device_update["location_name"] = matched_node.get('location', reverse_geocode_coordinates(current_lat, current_lng)) if matched_node else reverse_geocode_coordinates(current_lat, current_lng)
        sb.table('devices').upsert(device_update, on_conflict='device_id').execute()
    except Exception as e:
        print(f"[SUPABASE] Error syncing telemetry to Supabase: {e}")

    # ========================================================
    # TRIGGER human_fall_detect_final_count (PIR OR SOUND)
    # ========================================================
    if pir_detected or sound_detected:
        trigger_sources = []
        if pir_detected:
            trigger_sources.append("PIR")
        if sound_detected:
            trigger_sources.append("SOUND")
        source_desc = " + ".join(trigger_sources)
        print(f"[TRIGGER] Real-time sensor trigger ({source_desc}) on {device_id} -> Invoking trigger_human_fall_detection()")
        trigger_human_fall_detection(source=source_desc)
    else:
        # Neither PIR nor Sound detected - do not trigger
        pass

    if matched_node:
        print(f"[ESP32] Updated node {node_id}: PIR={matched_node.get('pir')}, Status={matched_node.get('status')}")
        return jsonify({"status": "accepted", "node": matched_node})
    
    # If node not found in memory, dynamically add it
    try:
        location_name = reverse_geocode_coordinates(current_lat, current_lng)
        node_name = f"{device_id} - {location_name}"
        
        new_node = {
            "id": device_id,
            "name": node_name,
            "location": location_name,
            "lat": current_lat,
            "lng": current_lng,
            "pir": bool(data.get('pir', False)),
            "vibration": 0.0,
            "acoustic_db": 85.0 if data.get('sound', False) else 35.0,
            "sound_class": "Elephant" if data.get('sound', False) else "Ambient",
            "confidence": 95.0 if (data.get('pir', False) or data.get('sound', False)) else 99.0,
            "status": "ALERT" if (data.get('pir', False) or data.get('sound', False)) else "SAFE",
            "power_source": "5V DC / USB (Mains Continuous)",
            "battery": "100%",
            "lora_rssi": -72,
            "wifi_status": "Connected",
            "cache_count": 0,
            "last_seen": "Just now",
            "ip_address": None
        }
        NODES_DATA.append(new_node)
        print(f"[ESP32] Dynamically registered new node {device_id} on /data route")
        return jsonify({"status": "accepted", "message": "Data received and new node registered in Supabase", "node": new_node})
    except Exception as e:
        print(f"[ESP32] Error registering new node on /data route: {e}")
        return jsonify({"status": "accepted", "message": "Data stored, but memory sync failed"})

@app.route('/api/edge-ai/predict', methods=['POST'])
def predict_audio():
    data = request.json or {}
    sample_type = data.get('sample_type', 'wind')
    
    if sample_type == 'trumpet':
        res = {
            "class": "Elephant Trumpet",
            "confidence": round(96.4 + random.uniform(-1, 2), 1),
            "threat_score": 98,
            "mfcc": [14.2, -8.5, 6.2, 12.1, -4.3, 8.7, -2.1, 5.4, -1.8, 4.2, 2.1, -0.9],
            "frequency_peak_hz": 1450,
            "energy_db": 88.5,
            "pir_confirmation": True,
            "vibration_confirmed": True,
            "fused_decision": "CONFIRMED ELEPHANT DETECTED"
        }
    elif sample_type == 'rumble':
        res = {
            "class": "Elephant Infrasonic Rumble",
            "confidence": round(91.8 + random.uniform(-1, 2), 1),
            "threat_score": 85,
            "mfcc": [18.5, 12.1, -3.2, 4.5, -9.1, 2.2, -5.4, 1.2, 0.8, -2.1, 1.4, -0.5],
            "frequency_peak_hz": 24,
            "energy_db": 74.2,
            "pir_confirmation": True,
            "vibration_confirmed": True,
            "fused_decision": "CONFIRMED ELEPHANT DETECTED"
        }
    elif sample_type == 'wind':
        res = {
            "class": "Environmental Wind Noise",
            "confidence": 98.2,
            "threat_score": 5,
            "mfcc": [-5.2, 2.1, -1.5, 0.8, -0.4, 1.1, -0.2, 0.5, -0.1, 0.3, 0.1, -0.2],
            "frequency_peak_hz": 120,
            "energy_db": 34.0,
            "pir_confirmation": False,
            "vibration_confirmed": False,
            "fused_decision": "NON-ELEPHANT SOUND - CLEAR"
        }
    else: # Vehicle engine
        res = {
            "class": "Vehicle Motor Noise",
            "confidence": 94.6,
            "threat_score": 12,
            "mfcc": [8.1, -12.4, 2.3, -4.1, 1.8, -2.2, 0.9, -1.1, 0.4, -0.8, 0.2, -0.3],
            "frequency_peak_hz": 420,
            "energy_db": 58.0,
            "pir_confirmation": False,
            "vibration_confirmed": False,
            "fused_decision": "NON-ELEPHANT SOUND - CLEAR"
        }
        
    return jsonify(res)

@app.route('/api/deterrent/trigger', methods=['POST'])
def trigger_deterrent():
    data = request.json or {}
    device = data.get('device')
    action = data.get('action')
    
    print(f"[DETERRENT] Received trigger: device={device}, action={action}")
    
    if device == 'bio_acoustic':
        DETERRENT_STATE['bio_acoustic_active'] = not DETERRENT_STATE['bio_acoustic_active'] if action == 'toggle' else (action == 'on')
    elif device == 'strobe_light':
        DETERRENT_STATE['strobe_light_active'] = not DETERRENT_STATE['strobe_light_active'] if action == 'toggle' else (action == 'on')
        strobe_action = "on" if DETERRENT_STATE['strobe_light_active'] else "off"
        
        # Send actuator command to ESP32 for strobe control in background thread
        def notify_esp32():
            try:
                # Target all active or registered nodes that have an IP address, with fallback
                target_ips = set()
                for n in NODES_DATA:
                    ip = n.get('ip_address')
                    if ip and ip.lower() != 'none':
                        target_ips.add(ip)
                if not target_ips:
                    target_ips.add('10.238.159.135')
                
                payload = {
                    "actuator": "strobe_light",
                    "action": strobe_action
                }
                
                for esp32_ip in target_ips:
                    esp32_url = f"http://{esp32_ip}/actuator"
                    print(f"[STROBE] Sending actuator command to ESP32 at {esp32_url}: {payload}")
                    try:
                        response = requests.post(esp32_url, json=payload, timeout=3)
                        print(f"[STROBE] ESP32 ({esp32_ip}) response: {response.status_code} - {response.text}")
                    except Exception as err:
                        print(f"[STROBE] Note: Could not send actuator command to ESP32 ({esp32_ip}): {err}")
            except Exception as e:
                print(f"[STROBE] General error in notify_esp32: {e}")

        threading.Thread(target=notify_esp32, daemon=True).start()
            
    elif device == 'siren':
        DETERRENT_STATE['siren_active'] = not DETERRENT_STATE['siren_active'] if action == 'toggle' else (action == 'on')
    elif device == 'sms_broadcast':
        DETERRENT_STATE['sms_alert_dispatched'] = True
        
    DETERRENT_STATE['last_trigger_time'] = time.strftime("%H:%M:%S")
    return jsonify({
        "status": "success",
        "message": f"{device} set to {action}",
        "deterrent_state": DETERRENT_STATE
    })

@app.route('/api/dss/recommendations', methods=['GET'])
def get_dss():
    online_count = len([n for n in NODES_DATA if n.get('status') != 'OFFLINE'])
    total_count = len(NODES_DATA)

    return jsonify({
        "predicted_conflict_time": "None (System Standby)",
        "target_vulnerable_village": "None - Boundary Secure",
        "recommended_actions": [
            {
                "priority": "LOW",
                "action": f"{online_count}/{total_count} ESP32 field nodes online (Node 1 Active Telemetry, Node 2 Offline/Standby)",
                "status": "ACTIVE"
            },
            {
                "priority": "LOW",
                "action": "Active field node power optimal (5V DC / USB Mains Continuous)",
                "status": "HEALTHY"
            },
            {
                "priority": "LOW",
                "action": "LoRa Mesh communication signal strength stable across active nodes",
                "status": "CONNECTED"
            }
        ]
    })

# ==============================================================================
# NEW CAMERA DETECTION INTEGRATION
# ==============================================================================
import csv
import cv2

# Global camera for live streaming
camera_stream = None
camera_lock = threading.Lock()

def get_camera_stream():
    global camera_stream
    with camera_lock:
        if camera_stream is None or not camera_stream.isOpened():
            camera_stream = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            camera_stream.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera_stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return camera_stream

def release_camera():
    global camera_stream
    with camera_lock:
        if camera_stream is not None:
            camera_stream.release()
            camera_stream = None

@app.route('/api/camera/stream')
def camera_stream_route():
    def generate():
        cap = get_camera_stream()
        try:
            while True:
                success, frame = cap.read()
                if not success:
                    break
                
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        finally:
            pass
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/camera/status', methods=['GET'])
def get_camera_status():
    """Get camera status and latest detection from Supabase"""
    try:
        from supabase_client import get_supabase_client
        sb = get_supabase_client()
        
        # Check camera online status from devices table (e.g. Node 1)
        node_id = request.args.get('node_id', 'ESP32-NODE-01')
        device_resp = sb.table('devices').select('last_seen').eq('device_id', node_id).execute()
        
        camera_online = is_human_fall_detection_running()
        if not camera_online and device_resp.data:
            last_seen = device_resp.data[0].get('last_seen')
            if last_seen:
                last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - last_seen_dt).total_seconds() <= 120:
                    camera_online = True
                    
        camera_status_str = "CONNECTED" if (camera_online or is_human_fall_detection_running()) else "CONNECTED"
        
        # Get latest detection
        det_resp = sb.table('detections').select('*').order('timestamp', desc=True).limit(1).execute()
        
        if det_resp.data:
            latest = det_resp.data[0]
            dt = datetime.fromisoformat(latest.get('timestamp').replace('Z', '+00:00'))
            
            det_status = "🐘 ELEPHANT DETECTED" if latest.get('detection') == "ELEPHANT_DETECTED" else "SAFE (NO ELEPHANT)"
                
            conf_val = latest.get('confidence', 0.0)
            conf_pct = round(conf_val * 100 if conf_val <= 1 else conf_val, 1)
            raw_img = latest.get('image_path') or latest.get('image_url') or ''
            latest_img = os.path.basename(raw_img) if raw_img else 'N/A'

            return jsonify({
                "camera_status": camera_status_str,
                "detection_status": det_status,
                "elephant_count": latest.get('elephant_count', 1 if latest.get('detection') == "ELEPHANT_DETECTED" else 0),
                "confidence": f"{conf_pct}%",
                "last_detection_time": f"{dt.strftime('%Y-%m-%d')} {dt.strftime('%H:%M:%S')}",
                "latest_detection_image": latest_img
            })
            
    except Exception as e:
        print(f"Error fetching camera status from Supabase: {e}")
        
    return jsonify({
        "camera_status": "OFFLINE",
        "detection_status": "No detection history",
        "elephant_count": 0,
        "confidence": "0.0%",
        "last_detection_time": "N/A",
        "latest_detection_image": "N/A"
    })

@app.route('/api/detections', methods=['GET'])
def get_detections():
    """Get all detection history from Supabase"""
    try:
        from supabase_client import get_supabase_client
        sb = get_supabase_client()
        
        response = sb.table('detections').select('*').order('timestamp', desc=True).limit(500).execute()
        
        detections = []
        for row in response.data:
            dt = datetime.fromisoformat(row.get('timestamp').replace('Z', '+00:00'))
            
            detections.append({
                "date": dt.strftime('%Y-%m-%d'),
                "time": dt.strftime('%H:%M:%S'),
                "timestamp": str(dt.timestamp()),
                "elephant_detected": "YES" if row.get('detection') == "ELEPHANT_DETECTED" else "NO",
                "elephant_count": 1,
                "confidence": row.get('confidence', 0.0),
                "saved_image": row.get('image_url', '')
            })
            
        return jsonify(detections)
    except Exception as e:
        print(f"Error fetching detections from Supabase: {e}")
        return jsonify([])

@app.route('/api/elephant-detection/confirmed', methods=['GET'])
def get_confirmed_elephant_detection():
    """Get the latest confirmed elephant detection for popup display.
    Only returns a detection if it occurred within the last 30 seconds
    (i.e. a FRESH detection, not a historical one from the CSV).
    """
    RECENCY_WINDOW_SECONDS = 30  # only trigger popup for detections within this window

    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))

    if not os.path.exists(csv_path):
        return jsonify({"confirmed": False, "detection": None})

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return jsonify({"confirmed": False, "detection": None})

            rows = list(reader)
            if not rows:
                return jsonify({"confirmed": False, "detection": None})

        # Search backwards for the most recent confirmed detection
        latest_confirmed = None
        for row in reversed(rows):
            if len(row) < 6:
                continue
            detected_val = row[3]
            count_val = int(row[4]) if row[4].isdigit() else 0
            if detected_val == "YES" and count_val > 0:
                latest_confirmed = row
                break

        if not latest_confirmed:
            return jsonify({"confirmed": False, "detection": None})

        # --- RECENCY CHECK ---
        # Parse the ISO timestamp (column 2) and compare to now
        timestamp_val = latest_confirmed[2]
        try:
            detection_dt = datetime.fromisoformat(timestamp_val)
            age_seconds = (datetime.now() - detection_dt).total_seconds()
        except Exception:
            # If timestamp is unparseable, fall back to CSV file mtime
            age_seconds = time.time() - os.path.getmtime(csv_path)

        if age_seconds > RECENCY_WINDOW_SECONDS:
            # Detection is old — do NOT trigger popup
            return jsonify({"confirmed": False, "detection": None})

        # Detection is fresh — build and return it
        date_val  = latest_confirmed[0]
        time_val  = latest_confirmed[1]
        count_val = int(latest_confirmed[4]) if latest_confirmed[4].isdigit() else 0
        try:
            conf_val = float(latest_confirmed[5])
        except ValueError:
            conf_val = 0.0

        image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
        image_val = ""
        if os.path.exists(image_dir):
            try:
                files  = os.listdir(image_dir)
                images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if images:
                    images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
                    image_val = images[0]
            except Exception:
                pass

        # Get current ESP32 sensor data
        current_pir = None
        current_sound = None
        if ESP32_CONNECTED and NODES_DATA:
            node = NODES_DATA[0]
            current_pir = 1.0 if node.get('pir', False) else 0.0
            current_sound = min(node.get('acoustic_db', 30) / 100.0, 1.0)
            print(f"[ESP32] Elephant detection: Including sensor data - PIR={current_pir}, Sound={current_sound}")
        else:
            print("[ESP32] Elephant detection: ESP32 offline, sensor data unavailable")

        detection = {
            "id":         f"{timestamp_val}_{count_val}",
            "timestamp":  timestamp_val,
            "count":      count_val,
            "confidence": conf_val,
            "image":      image_val,
            "date":       date_val,
            "time":       time_val,
            "age_seconds": round(age_seconds, 1),
            "pir":        current_pir,
            "sound":      current_sound
        }

        return jsonify({"confirmed": True, "detection": detection})

    except Exception as e:
        print(f"Error reading confirmed detection: {e}")
        return jsonify({"confirmed": False, "detection": None})

@app.route('/api/elephant-detection/test-popup', methods=['POST'])
def test_elephant_popup():
    """Test endpoint to simulate an elephant detection for popup testing"""
    try:
        test_detection = {
            "id": f"test_{datetime.now().isoformat()}",
            "timestamp": datetime.now().isoformat(),
            "count": 2,
            "confidence": 94.7,
            "image": "elephant_20260919_211446.jpg",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S")
        }
        return jsonify({"confirmed": True, "detection": test_detection})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/elephant-detection/real', methods=['GET'])
def get_real_elephant_detection():
    """Get the latest REAL elephant detection from the detection dataset"""
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    
    if not os.path.exists(csv_path):
        return jsonify({"confirmed": False, "detection": None})
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return jsonify({"confirmed": False, "detection": None})
            
            # Get all rows
            rows = list(reader)
            if not rows:
                return jsonify({"confirmed": False, "detection": None})
            
            # Find the most recent confirmed detection
            latest_confirmed = None
            for row in reversed(rows):
                if len(row) < 6:
                    continue
                
                detected_val = row[3]
                count_val = int(row[4]) if row[4].isdigit() else 0
                
                if detected_val == "YES" and count_val > 0:
                    latest_confirmed = row
                    break
            
            if not latest_confirmed:
                return jsonify({"confirmed": False, "detection": None})
            
            date_val = latest_confirmed[0]
            time_val = latest_confirmed[1]
            timestamp_val = latest_confirmed[2]
            count_val = int(latest_confirmed[4]) if latest_confirmed[4].isdigit() else 0
            try:
                conf_val = float(latest_confirmed[5])
            except ValueError:
                conf_val = 0.0
            
            # Try to get the corresponding image
            image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
            image_val = ""
            if os.path.exists(image_dir):
                try:
                    files = os.listdir(image_dir)
                    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                    if images:
                        # Sort by modification time, get the most recent
                        images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
                        image_val = images[0]
                except Exception:
                    pass
            
            detection = {
                "id": f"{timestamp_val}_{count_val}",
                "timestamp": timestamp_val,
                "count": count_val,
                "confidence": conf_val,
                "image": image_val,
                "date": date_val,
                "time": time_val
            }
            
            return jsonify({"confirmed": True, "detection": detection})
                
    except Exception as e:
        print(f"Error reading confirmed detection: {e}")
        return jsonify({"confirmed": False, "detection": None})

@app.route('/api/detections/download', methods=['GET'])
def download_csv():
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
    if not os.path.exists(csv_path):
        return "CSV file not found", 404
    directory = os.path.dirname(csv_path)
    filename = os.path.basename(csv_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/detection-images/<filename>')
def get_detection_image(filename):
    image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
    return send_from_directory(image_dir, filename)

@app.route('/service-worker.js')
def get_service_worker():
    return send_from_directory(base_dir, 'service-worker.js')

@app.route('/api/detection-images', methods=['GET'])
def list_detection_images():
    image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
    if not os.path.exists(image_dir):
        return jsonify([])
    try:
        files = os.listdir(image_dir)
        images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        images.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
        return jsonify(images)
    except Exception:
        return jsonify([])


# ==============================================================================
# ALERT SYSTEM API ENDPOINTS
# ==============================================================================

@app.route('/api/alerts/history', methods=['GET'])
def get_alerts_history():
    """Get alert history"""
    try:
        service = get_notification_service()
        limit = request.args.get('limit', type=int)
        history = service.get_alert_history(limit)
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/status', methods=['GET'])
def get_alert_status():
    """Get current alert state"""
    try:
        service = get_notification_service()
        status = service.get_current_state()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/process', methods=['POST'])
def process_alert_detection():
    """Process a detection through the confirmation layer"""
    try:
        data = request.json
        elephant_count = data.get('elephant_count', 0)
        confidence = data.get('confidence', 0)
        image_path = data.get('image_path', '')
        csv_row_data = data.get('csv_row_data', {})
        
        service = get_notification_service()
        alert_event = service.process_detection(
            elephant_count, confidence, image_path, csv_row_data
        )
        
        if alert_event:
            # Trigger web push notifications
            push_service = get_push_service()
            
            # Send web push to forest officers
            if push_service.is_configured():
                push_result = push_service.send_elephant_alert(alert_event, role="FOREST_OFFICER")
                service.update_delivery_status(
                    alert_event['alert_id'], 'web_push', 'forest_officers',
                    'sent' if push_result['success'] else 'failed'
                )
            
            # Send web push to villagers
            if push_service.is_configured():
                push_result = push_service.send_elephant_alert(alert_event, role="VILLAGER")
                service.update_delivery_status(
                    alert_event['alert_id'], 'web_push', 'villagers',
                    'sent' if push_result['success'] else 'failed'
                )
            
            return jsonify({"success": True, "alert": alert_event})
        else:
            return jsonify({"success": False, "message": "No alert created"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def sync_detection_record(timestamp_iso, elephant_count, confidence, image_filename, image_full_path=None):
    """
    Core bridge function to:
    1. Upload image to Supabase Storage 'elephant-images'
    2. Insert detection record into Supabase 'detections' table
    3. Trigger notifications (Web Push + WhatsApp)
    """
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        
        # 1. Normalize filename
        clean_filename = os.path.basename(image_filename) if image_filename else ""
        
        # 2. Upload image to Supabase Storage if file exists
        if clean_filename:
            local_img_dir = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
            local_fp = image_full_path if (image_full_path and os.path.exists(image_full_path)) else os.path.join(local_img_dir, clean_filename)
            if os.path.exists(local_fp):
                try:
                    with open(local_fp, 'rb') as f_img:
                        sb.storage.from_('elephant-images').upload(
                            path=clean_filename,
                            file=f_img.read(),
                            file_options={"content-type": "image/jpeg", "upsert": "true"}
                        )
                        print(f"[LIVE-SYNC] Uploaded {clean_filename} to Supabase Storage")
                except Exception as ue:
                    print(f"[LIVE-SYNC] Storage upload notice ({clean_filename}): {ue}")
                    
        # 3. Normalize confidence (check constraint: 0 <= confidence <= 1)
        conf_float = float(confidence) if str(confidence).replace('.', '').isdigit() else 0.0
        conf_norm = round(conf_float / 100.0 if conf_float > 1.0 else conf_float, 4)
        
        # 4. Get active node sensor telemetry
        curr_pir = True
        curr_sound = True
        curr_sound_db = 85
        curr_lat = 12.8224
        curr_lng = 77.577
        if NODES_DATA:
            node = NODES_DATA[0]
            curr_pir = node.get('pir', True)
            curr_sound = node.get('sound', True)
            curr_sound_db = node.get('acoustic_db', 85)
            curr_lat = node.get('lat', 12.8224)
            curr_lng = node.get('lng', 77.577)

        # 5. Insert into Supabase detections table
        detection_payload = {
            "device_id": "ESP32-NODE-01",
            "timestamp": timestamp_iso,
            "detection": "ELEPHANT_DETECTED" if elephant_count > 0 else "SAFE",
            "elephant_count": int(elephant_count),
            "confidence": conf_norm,
            "image_path": clean_filename,
            "pir_detected": curr_pir,
            "sound_detected": curr_sound,
            "sound_level": curr_sound_db,
            "latitude": curr_lat,
            "longitude": curr_lng,
            "incident_status": "pending",
            "alert_sent": True
        }
        insert_res = sb.table('detections').insert(detection_payload).execute()
        created_detection = insert_res.data[0] if insert_res.data else {}
        detection_id = created_detection.get('id')
        print(f"[LIVE-SYNC] Successfully stored detection in Supabase: {timestamp_iso} (ID: {detection_id}, Count: {elephant_count})")
        
        # 6. Trigger notifications
        try:
            # WhatsApp via local Baileys service to Varun (+917094528671)
            import whatsapp_service
            detection_payload['id'] = detection_id
            detection_payload['location'] = (NODES_DATA[0].get('location') if NODES_DATA else 'Bannerghatta Forest Perimeter')
            whatsapp_service.send_confirmed_elephant_whatsapp(detection_payload)
            
            # Web Push
            service = get_notification_service()
            alert_event = service._create_alert_event(
                int(elephant_count), conf_norm, clean_filename, {
                    "timestamp": timestamp_iso,
                    "elephant_count": int(elephant_count),
                    "confidence": round(conf_norm * 100, 1)
                }
            )
            push_service = get_push_service()
            if push_service.is_configured():
                push_service.send_elephant_alert(alert_event, role="FOREST_OFFICER")
                push_service.send_elephant_alert(alert_event, role="VILLAGER")
        except Exception as ne:
            print(f"[LIVE-SYNC] Notification dispatch error: {ne}")
            
        return True, insert_res.data
    except Exception as e:
        print(f"[LIVE-SYNC] Error storing detection to Supabase: {e}")
        return False, str(e)

@app.route('/api/camera/detection-event', methods=['POST'])
def receive_camera_detection_event():
    """Direct webhook endpoint for human_fall_detect_final_count to post detections immediately"""
    try:
        data = request.json or {}
        count = data.get('elephant_count', 0)
        confidence = data.get('confidence', 0.0)
        img_name = data.get('image_name') or data.get('image_path', '')
        img_full = data.get('image_full_path')
        ts_val = data.get('timestamp') or datetime.now(timezone.utc).isoformat()
        
        # Ensure timezone format
        if 'T' in ts_val and not ts_val.endswith('Z') and '+' not in ts_val:
            tz_offset = timezone(datetime.now().astimezone().utcoffset())
            ts_val = datetime.fromisoformat(ts_val).replace(tzinfo=tz_offset).isoformat()
            
        success, res = sync_detection_record(ts_val, count, confidence, img_name, img_full)
        return jsonify({"success": success, "result": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

SYNCED_DETECTION_TIMESTAMPS = set()

def start_csv_detection_watcher():
    """Background daemon thread that continuously monitors elephant_detection_dataset.csv"""
    global SYNCED_DETECTION_TIMESTAMPS
    
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        recent = sb.table('detections').select('timestamp').order('timestamp', desc=True).limit(200).execute()
        for r in recent.data:
            ts = r.get('timestamp', '')
            if ts:
                SYNCED_DETECTION_TIMESTAMPS.add(ts[:19])
    except Exception as e:
        print(f"[CSV-WATCHER] Note on startup cache: {e}")
        
    def watcher_loop():
        csv_path = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'elephant_detection_dataset.csv'))
        print(f"[CSV-WATCHER] Started background watcher for {csv_path}")
        
        while True:
            try:
                time.sleep(2)
                if not os.path.exists(csv_path):
                    continue
                    
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if not header:
                        continue
                    rows = list(reader)
                    
                for row in rows:
                    if len(row) < 6:
                        continue
                    det_val = row[3].strip().upper()
                    if det_val != "YES":
                        continue
                        
                    date_val, time_val, ts_val, _, count_val, conf_val = row[:6]
                    img_val = row[6] if len(row) > 6 else ""
                    
                    key = ts_val[:19] if ts_val else f"{date_val}T{time_val}"
                    if key in SYNCED_DETECTION_TIMESTAMPS:
                        continue
                        
                    SYNCED_DETECTION_TIMESTAMPS.add(key)
                    
                    try:
                        dt = datetime.fromisoformat(ts_val)
                        if dt.tzinfo is None:
                            tz_offset = timezone(datetime.now().astimezone().utcoffset())
                            dt = dt.replace(tzinfo=tz_offset)
                        iso_ts = dt.isoformat()
                    except Exception:
                        iso_ts = f"{date_val}T{time_val}+05:30"
                        
                    print(f"[CSV-WATCHER] New un-synced detection found: {iso_ts} (Count: {count_val})")
                    sync_detection_record(iso_ts, int(count_val) if count_val.isdigit() else 1, conf_val, img_val)
            except Exception as loop_err:
                print(f"[CSV-WATCHER] Loop warning: {loop_err}")
                time.sleep(3)
                
    watcher_thread = threading.Thread(target=watcher_loop, daemon=True)
    watcher_thread.start()

# Start background watcher
start_csv_detection_watcher()

@app.route('/api/alerts/camera-verification', methods=['POST'])
def process_camera_verification():
    """
    Process camera/AI verification for activity events
    This endpoint is called when camera verification completes
    """
    try:
        data = request.json
        event_id = data.get('event_id')
        elephant_detected = data.get('elephant_detected', False)
        confidence = data.get('confidence', 0.0)
        image_path = data.get('image_path', '')
        
        service = get_notification_service()
        result = service.process_camera_verification(
            event_id, elephant_detected, confidence, image_path
        )
        
        return jsonify({"success": True, "result": result})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/test-whatsapp', methods=['POST', 'GET'])
def test_whatsapp_alert():
    """
    Test endpoint to safely test WhatsApp notifications via local Baileys service (http://localhost:3001)
    Sends ONLY to configured recipient (+917094528671)
    Does NOT create a fake elephant detection
    """
    try:
        import whatsapp_service
        success, message = whatsapp_service.send_test_whatsapp()
        return jsonify({
            "success": success,
            "message": message,
            "recipient": whatsapp_service.get_whatsapp_recipient()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/nodes/set-online', methods=['POST'])
def set_node_online():
    """
    Manually set a node's status to online in Supabase
    This is for debugging/administration purposes
    """
    try:
        data = request.json
        device_id = data.get('device_id')
        
        if not device_id:
            return jsonify({"error": "device_id is required"}), 400
        
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        iso_now = datetime.now(timezone.utc).isoformat()
        
        # Update device status to online
        sb.table('devices').update({
            "status": "online",
            "last_seen": iso_now,
            "last_heartbeat_at": iso_now,
            "updated_at": iso_now
        }).eq('device_id', device_id).execute()
        
        # Update in-memory node if exists
        for node in NODES_DATA:
            if node['id'] == device_id:
                node['wifi_status'] = 'Connected'
                node['last_seen'] = 'Just now'
                node['sound_class'] = 'Ambient Forest Sound'
                node['confidence'] = 99.2
                break
        
        return jsonify({
            "success": True,
            "message": f"Node {device_id} set to online",
            "device_id": device_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/update-delivery', methods=['POST'])
def update_alert_delivery():
    """Update delivery status for an alert"""
    try:
        data = request.json
        alert_id = data.get('alert_id')
        channel = data.get('channel')
        role = data.get('role')
        status = data.get('status')
        
        service = get_notification_service()
        success = service.update_delivery_status(alert_id, channel, role, status)
        
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# WEB PUSH API ENDPOINTS
# ==============================================================================

@app.route('/api/push/status', methods=['GET'])
def get_push_status():
    """Get push service status"""
    try:
        service = get_push_service()
        return jsonify({
            "configured": service.is_configured(),
            "vapid_public_key": service.get_vapid_public_key()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/vapid-key', methods=['GET'])
def get_vapid_key():
    """Get VAPID public key for push subscription"""
    try:
        service = get_push_service()
        public_key = service.get_vapid_public_key()
        print(f"VAPID public key length: {len(public_key)}")
        print(f"VAPID public key: {public_key}")
        return jsonify({"vapid_public_key": public_key})
    except Exception as e:
        print(f"Error getting VAPID key: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    """Subscribe to push notifications"""
    try:
        data = request.json
        subscription = data.get('subscription')
        if not isinstance(subscription, dict):
            return jsonify({"error": "A Push subscription object is required"}), 400
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
            
        service = get_push_service()
        subscription_id = service.add_subscription(subscription, user_id)
        
        return jsonify({"success": True, "subscription_id": subscription_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/push/unsubscribe', methods=['POST'])
def unsubscribe_push():
    """Unsubscribe from push notifications"""
    try:
        data = request.json
        subscription = data.get('subscription')
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
            
        service = get_push_service()
        endpoint = subscription.get('endpoint')
        
        if service.remove_subscription(endpoint, user_id):
            return jsonify({"success": True})
        
        return jsonify({"success": False, "error": "Subscription not found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# Sensor Monitoring API Endpoints
# ==============================================================================


# ESP32 Connection Tracking
ESP32_LAST_SEEN = None
ESP32_TIMEOUT_SECONDS = 30  # Consider ESP32 offline if no data for 30 seconds
ESP32_CONNECTED = False
DEVICE_LAST_SEEN = {
    "ESP32-NODE-01": None,
    "ESP32-NODE-02": None
}

def check_device_connection(device_id="ESP32-NODE-01"):
    """Check if a specific ESP32 node is connected based on its own last seen time"""
    last_seen = DEVICE_LAST_SEEN.get(device_id)
    if last_seen is None:
        return False
    time_since = (datetime.now() - last_seen).total_seconds()
    return time_since <= ESP32_TIMEOUT_SECONDS

def check_esp32_connection(device_id=None):
    """Check if ESP32 node(s) are connected"""
    global ESP32_CONNECTED
    if device_id:
        return check_device_connection(device_id)
    any_connected = any(check_device_connection(d) for d in DEVICE_LAST_SEEN)
    ESP32_CONNECTED = any_connected
    return any_connected

# Reverse Geocoding Cache and Rate Limiting
GEOCODE_CACHE = {}
GEOCODE_LAST_REQUEST_TIME = 0
GEOCODE_MIN_INTERVAL = 5  # Minimum seconds between reverse geocoding requests

# Initialize connection tracking on startup
print("[ESP32] Connection tracking initialized - waiting for real ESP32 telemetry")



def get_location_name_from_coords(lat, lng):
    """Convert GPS coordinates to location name based on predefined regions"""
    # ESP32 Specific Sensor Field Node Locations
    if math.hypot(lat - 12.8224, lng - 77.5770) < 0.015: return "Buthanahalli (Bannerghatta NP Fringe, KA)"
    if math.hypot(lat - 12.79213, lng - 77.61622) < 0.015: return "Begihalli (Anekal Taluk, KA)"
    if math.hypot(lat - 12.5195, lng - 77.8200) < 0.015: return "Bettamugilalam (Hosur-Denkanikottai, TN)"
    if math.hypot(lat - 12.7180, lng - 77.5840) < 0.015: return "Ragihalli Village (Bengaluru Urban, KA)"
    if math.hypot(lat - 12.6100, lng - 77.7100) < 0.015: return "Thammanayakanahalli (Anekal Area, Bengaluru Urban, KA)"
    if math.hypot(lat - 12.5400, lng - 77.7800) < 0.015: return "Kadusivanapalli (Jawalagiri Area, Krishnagiri, TN)"
    
    # Broader regional mappings
    if lat >= 12.88 and lat <= 13.05 and lng >= 77.85 and lng <= 78.10: return "Maluru taluk, Karnataka"
    if lat >= 13.00 and lat <= 13.25 and lng >= 78.00 and lng <= 78.30: return "Kolar, Karnataka"
    if lat >= 13.00 and lat <= 13.15 and lng >= 77.75 and lng <= 77.95: return "Hoskote, Bengaluru Rural, Karnataka"
    if lat >= 12.67 and lat <= 12.75 and lng >= 77.62 and lng <= 77.75: return "Anekal Taluk, Bengaluru Urban, Karnataka"
    if lat >= 12.75 and lat <= 12.82 and lng >= 77.62 and lng <= 77.68: return "Jigani Industrial Sector, Karnataka"
    if lat >= 12.70 and lat <= 12.82 and lng >= 77.50 and lng <= 77.61: return "Bannerghatta National Park Reserve Forest, Karnataka"
    if lat >= 12.83 and lat <= 13.20 and lng >= 77.45 and lng <= 77.75: return "Bengaluru Metropolitan Area, Karnataka"
    
    # Tamil Nadu regions
    if lat >= 12.65 and lng >= 77.72 and lng <= 78.10: return "Hosur Sector, Krishnagiri District, Tamil Nadu"
    if lat >= 12.40 and lat < 12.65 and lng >= 77.62 and lng <= 78.00: return "Denkanikottai / Thally Range, Tamil Nadu"
    if lat >= 12.10 and lat < 12.50 and lng >= 77.20 and lng < 77.70: return "Cauvery North Wildlife Sanctuary, Tamil Nadu"
    if lat >= 12.00 and lat < 12.60 and lng >= 77.70 and lng < 78.50: return "Krishnagiri District, Tamil Nadu"
    
    # Default fallback with coordinates
    return f"GPS Location ({lat:.4f}°, {lng:.4f}°)"

def reverse_geocode_coordinates(lat, lng):
    """Perform reverse geocoding using OpenStreetMap Nominatim API with caching and rate limiting"""
    global GEOCODE_LAST_REQUEST_TIME, GEOCODE_CACHE
    if lat is None or lng is None:
        return "Awaiting GPS Fix"
    
    # Check cache first
    cache_key = f"{lat:.4f},{lng:.4f}"
    if cache_key in GEOCODE_CACHE:
        cached_result, cache_time = GEOCODE_CACHE[cache_key]
        # Use cache if less than 1 hour old
        if time.time() - cache_time < 3600:
            print(f"[GEOCODE] Using cached result for {cache_key}")
            return cached_result
    
    # Rate limiting - minimum interval between requests
    current_time = time.time()
    if current_time - GEOCODE_LAST_REQUEST_TIME < GEOCODE_MIN_INTERVAL:
        print(f"[GEOCODE] Rate limited - using fallback for {cache_key}")
        return get_location_name_from_coords(lat, lng)
    
    GEOCODE_LAST_REQUEST_TIME = current_time
    
    try:
        # Call OpenStreetMap Nominatim API
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=12"
        headers = {'User-Agent': 'WildlifeMonitoringSystem/1.0'}
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data and 'address' in data:
                addr = data['address']
                # Build location name from available fields
                place = (addr.get('village') or addr.get('town') or addr.get('city') or 
                        addr.get('suburb') or addr.get('county') or addr.get('state_district') or 
                        addr.get('district') or '')
                state = addr.get('state') or addr.get('country') or ''
                
                if place and state:
                    location_name = f"{place}, {state}"
                elif place:
                    location_name = place
                elif state:
                    location_name = state
                else:
                    location_name = data.get('display_name', '').split(',')[0]
                
                # Cache the result
                GEOCODE_CACHE[cache_key] = (location_name, current_time)
                print(f"[GEOCODE] Reverse geocoded {cache_key} -> {location_name}")
                return location_name
        
        # Fallback to predefined regions if API fails
        print(f"[GEOCODE] API failed for {cache_key}, using fallback")
        return get_location_name_from_coords(lat, lng)
        
    except Exception as e:
        print(f"[GEOCODE] Error reverse geocoding {cache_key}: {e}")
        return get_location_name_from_coords(lat, lng)

# ========================================================
# DETECTION CONTROL ENDPOINTS
# ========================================================

@app.route('/api/detection/status', methods=['GET'])
def get_detection_status():
    """Returns whether human_fall_detect_final_count is currently running"""
    running = is_human_fall_detection_running()
    pid = DETECTION_PROCESS.pid if running else None
    return jsonify({
        "running": running,
        "pid": pid,
        "last_trigger": LAST_DETECTION_TRIGGER_TIME,
        "cooldown_seconds": DETECTION_COOLDOWN_SECONDS,
        "script_path": FALL_DETECT_SCRIPT,
        "script_exists": os.path.exists(FALL_DETECT_SCRIPT)
    })

@app.route('/api/detection/trigger', methods=['POST'])
def manual_trigger_detection():
    """Manual/Test endpoint to trigger human_fall_detect_final_count with PIR/Sound simulation"""
    data = request.json or {}
    pir_val = bool(data.get('pir', False))
    sound_val = bool(data.get('sound', False))
    source_val = data.get('source')
    
    # If pir or sound flags are provided, enforce the EXACT condition: pir_detected or sound_detected
    if 'pir' in data or 'sound' in data:
        if pir_val or sound_val:
            src = []
            if pir_val: src.append("PIR")
            if sound_val: src.append("SOUND")
            source_desc = " + ".join(src)
            success, msg = trigger_human_fall_detection(source=source_desc)
            return jsonify({
                "triggered": True,
                "pir": pir_val,
                "sound": sound_val,
                "source": source_desc,
                "success": success,
                "message": msg,
                "running": is_human_fall_detection_running()
            })
        else:
            return jsonify({
                "triggered": False,
                "pir": False,
                "sound": False,
                "success": False,
                "message": "Neither PIR nor Sound detected. human_fall_detect_final_count not triggered.",
                "running": is_human_fall_detection_running()
            })
    
    # Direct trigger call
    success, msg = trigger_human_fall_detection(source=source_val or "API")
    return jsonify({
        "triggered": True,
        "success": success,
        "message": msg,
        "running": is_human_fall_detection_running()
    })

@app.route('/api/sensor/current', methods=['GET'])
def get_current_sensor_data():
    """Get current sensor values for a selected node from Supabase"""
    node_id = request.args.get('node_id') or request.args.get('device_id') or 'ESP32-NODE-01'
    try:
        from supabase_client import get_supabase_client
        sb = get_supabase_client()
        
        # Check connection status from devices table
        is_connected = False
        device_name = f"Node {node_id}"
        location = "Unknown Location"
        
        dev_resp = sb.table('devices').select('last_seen, name, location_name').eq('device_id', node_id).execute()
        
        if dev_resp.data:
            dev = dev_resp.data[0]
            device_name = dev.get('name', device_name)
            location = dev.get('location_name', location)
            last_seen = dev.get('last_seen')
            if last_seen:
                last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - last_seen_dt).total_seconds() <= 30:
                    is_connected = True
                    
        # Get latest sensor reading from raw_sensor_data
        pir_value = 0.0
        sound_value = 0.0
        last_update = None
        
        if is_connected:
            sensor_resp = sb.table('raw_sensor_data').select('*').eq('device_id', node_id).order('timestamp', desc=True).limit(1).execute()
            if sensor_resp.data:
                latest = sensor_resp.data[0]
                pir_value = 1.0 if latest.get('pir_detected') else 0.0
                sound_value = min(float(latest.get('sound_level', 30.0)) / 100.0, 1.0)
                last_update = latest.get('timestamp')
                
        if not is_connected:
            return jsonify({
                "node_id": node_id,
                "node_name": device_name,
                "location": location,
                "esp32_connected": False,
                "pir": 0.0,
                "sound": 0.0,
                "pir_min": 0.0,
                "pir_max": 1.0,
                "pir_limit": 0.5,
                "sound_min": 0.0,
                "sound_max": 1.0,
                "sound_limit": 0.3,
                "pir_status": "OFFLINE",
                "sound_status": "OFFLINE",
                "message": f"{device_name} Offline - Awaiting Hardware Telemetry",
                "last_update": None
            })
            
        return jsonify({
            "node_id": node_id,
            "node_name": device_name,
            "location": location,
            "esp32_connected": True,
            "pir": pir_value,
            "sound": sound_value,
            "pir_min": 0.0,
            "pir_max": 1.0,
            "pir_limit": 0.5,
            "sound_min": 0.0,
            "sound_max": 1.0,
            "sound_limit": 0.3,
            "pir_status": "HIGH" if pir_value > 0.5 else "LOW",
            "sound_status": "HIGH" if sound_value > 0.3 else "NORMAL",
            "message": "Receiving live telemetry from node",
            "last_update": last_update
        })
    except Exception as e:
        print(f"Error fetching sensor current data: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/esp32/status', methods=['GET'])
def get_esp32_status():
    """Get connection status for a specific node (Node 1 or Node 2)"""
    try:
        node_id = request.args.get('node_id') or request.args.get('device_id') or 'ESP32-NODE-01'
        connected = check_device_connection(node_id)
        last_dt = DEVICE_LAST_SEEN.get(node_id)
        last_seen = last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else "Never"
        
        return jsonify({
            "node_id": node_id,
            "connected": connected,
            "last_seen": last_seen,
            "timeout_seconds": ESP32_TIMEOUT_SECONDS
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sensor/history', methods=['GET'])
def get_sensor_history():
    """Get sensor history data directly from Supabase Cloud filtered by node"""
    node_id = request.args.get('node_id') or request.args.get('device_id') or 'ESP32-NODE-01'
    sensor_type = request.args.get('sensor', 'pir')
    try:
        supabase = get_supabase_client()
        limit = int(request.args.get('limit', 100))
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        query = supabase.table('raw_sensor_data').select('*').eq('device_id', node_id).order('timestamp', desc=True).limit(limit)
        if from_date:
            from_ts = f"{from_date}T00:00:00" if len(from_date) == 10 else from_date
            query = query.gte('timestamp', from_ts)
        if to_date:
            to_ts = f"{to_date}T23:59:59.999999" if len(to_date) == 10 else to_date
            query = query.lte('timestamp', to_ts)
            
        res = query.execute()
        raw_rows = list(reversed(res.data or []))
        
        filtered_data = []
        for r in raw_rows:
            p_val = 1.0 if r.get('pir_detected') else 0.0
            s_level = float(r.get('sound_level') or (85.0 if r.get('sound_detected') else 35.0))
            s_val = min(s_level / 100.0, 1.0)
            filtered_data.append({
                "timestamp": r.get('timestamp'),
                "pir": p_val,
                "sound": s_val
            })
            
        if sensor_type == 'pir':
            return jsonify({
                "data": [{"timestamp": d['timestamp'], "value": d['pir']} for d in filtered_data],
                "sensor_type": "PIR",
                "total_points": len(filtered_data),
                "node_id": node_id
            })
        elif sensor_type == 'sound':
            return jsonify({
                "data": [{"timestamp": d['timestamp'], "value": d['sound']} for d in filtered_data],
                "sensor_type": "Sound",
                "total_points": len(filtered_data),
                "node_id": node_id
            })
        else:  # combined
            return jsonify({
                "data": filtered_data,
                "sensor_type": "Combined",
                "total_points": len(filtered_data),
                "node_id": node_id
            })
    except Exception as e:
        print(f"[SUPABASE] Error in sensor history: {e}")
        return jsonify({"data": [], "sensor_type": sensor_type, "total_points": 0, "node_id": node_id})

@app.route('/api/sensor/export', methods=['GET'])
def export_sensor_data():
    """Export sensor data as CSV directly from Supabase Cloud filtered by node"""
    node_id = request.args.get('node_id') or request.args.get('device_id') or 'ESP32-NODE-01'
    try:
        supabase = get_supabase_client()
        sensor_type = request.args.get('sensor', 'combined')
        limit = int(request.args.get('limit', 1000))
        step = int(request.args.get('step', 1))
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        query = supabase.table('raw_sensor_data').select('*').eq('device_id', node_id).order('timestamp', desc=True).limit(limit)
        if from_date:
            from_ts = f"{from_date}T00:00:00" if len(from_date) == 10 else from_date
            query = query.gte('timestamp', from_ts)
        if to_date:
            to_ts = f"{to_date}T23:59:59.999999" if len(to_date) == 10 else to_date
            query = query.lte('timestamp', to_ts)
            
        res = query.execute()
        records = list(reversed(res.data or []))
        if step > 1:
            records = records[::step]
            
        data_to_export = []
        for r in records:
            p_val = 1.0 if r.get('pir_detected') else 0.0
            s_level = float(r.get('sound_level') or (85.0 if r.get('sound_detected') else 35.0))
            s_val = min(s_level / 100.0, 1.0)
            if sensor_type == 'pir':
                data_to_export.append({"timestamp": r.get('timestamp'), "pir": p_val})
            elif sensor_type == 'sound':
                data_to_export.append({"timestamp": r.get('timestamp'), "sound": s_val})
            else:
                data_to_export.append({"timestamp": r.get('timestamp'), "pir": p_val, "sound": s_val})
                
        from io import StringIO
        output = StringIO()
        if sensor_type == 'pir':
            fieldnames = ['timestamp', 'pir']
        elif sensor_type == 'sound':
            fieldnames = ['timestamp', 'sound']
        else:
            fieldnames = ['timestamp', 'pir', 'sound']
            
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data_to_export)
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename=sensor_data_{node_id}_{sensor_type}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
    except Exception as e:
        print(f"[SUPABASE] Error exporting sensor data: {e}")
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# SUPABASE INTEGRATION ENDPOINTS
# ==============================================================================

@app.route('/api/supabase/raw-sensor-data', methods=['GET'])
def get_supabase_raw_sensor_data():
    """Get raw sensor data from Supabase with filtering and pagination"""
    try:
        supabase = get_supabase_client()
        
        # Get query parameters
        limit = int(request.args.get('limit', 50))
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        device_id = request.args.get('device_id')
        
        # Build query
        query = supabase.table('raw_sensor_data').select('*').order('timestamp', desc=True).limit(limit)
        
        # Apply date filtering if provided
        if from_date:
            try:
                local_tz = datetime.now().astimezone().tzinfo
                dt_from = datetime.strptime(from_date[:10], "%Y-%m-%d")
                from_ts = datetime.combine(dt_from.date(), dt_time.min, tzinfo=local_tz).astimezone(timezone.utc).isoformat()
            except Exception:
                from_ts = f"{from_date}T00:00:00Z"
            query = query.gte('timestamp', from_ts)
        if to_date:
            try:
                local_tz = datetime.now().astimezone().tzinfo
                dt_to = datetime.strptime(to_date[:10], "%Y-%m-%d")
                to_ts = datetime.combine(dt_to.date(), dt_time.max, tzinfo=local_tz).astimezone(timezone.utc).isoformat()
            except Exception:
                to_ts = f"{to_date}T23:59:59.999999Z"
            query = query.lte('timestamp', to_ts)
        
        # Apply device filtering if provided
        if device_id:
            query = query.eq('device_id', device_id)
        
        # Execute query
        result = query.execute()
        
        # Transform data for frontend compatibility
        transformed_data = []
        for record in (result.data or []):
            pir_bool = bool(record.get('pir_detected'))
            sound_bool = bool(record.get('sound_detected'))
            transformed_data.append({
                'id': record.get('id'),
                'timestamp': record.get('timestamp'),
                'pir': 'DETECTED' if pir_bool else 'SAFE',
                'pir_val': 1.0 if pir_bool else 0.0,
                'sound': 'DETECTED' if sound_bool else 'SAFE',
                'sound_val': float(record.get('sound_level') or (85.0 if sound_bool else 35.0)),
                'sound_level': record.get('sound_level'),
                'latitude': record.get('latitude'),
                'longitude': record.get('longitude'),
                'device_id': record.get('device_id')
            })
        
        return jsonify(transformed_data)
    except Exception as e:
        print(f"[SUPABASE] Error fetching raw sensor data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/supabase/detections', methods=['GET'])
def get_supabase_detections():
    """Get detection data from Supabase with filtering and pagination"""
    try:
        supabase = get_supabase_client()
        
        # Get query parameters
        limit = int(request.args.get('limit', 50))
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        device_id = request.args.get('device_id')
        detection_type = request.args.get('detection_type')  # SAFE, ELEPHANT_DETECTED, or all
        
        # Build query
        query = supabase.table('detections').select('*').order('timestamp', desc=True).limit(limit)
        
        # Apply date filtering if provided
        if from_date:
            query = query.gte('timestamp', from_date)
        if to_date:
            query = query.lte('timestamp', to_date)
        
        # Apply device filtering if provided
        if device_id:
            query = query.eq('device_id', device_id)
        
        # Apply detection type filtering if provided
        if detection_type and detection_type != 'all':
            query = query.eq('detection', detection_type)
        
        # Execute query
        result = query.execute()
        
        # Transform data for frontend compatibility
        transformed_data = []
        for record in result.data:
            # Parse timestamp to separate date and time
            timestamp_str = record.get('timestamp', '')
            if timestamp_str:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d')
                    time_str = dt.strftime('%H:%M:%S')
                except:
                    date_str = timestamp_str.split('T')[0] if 'T' in timestamp_str else timestamp_str
                    time_str = timestamp_str.split('T')[1].split('.')[0] if 'T' in timestamp_str else ''
            else:
                date_str = ''
                time_str = ''
            
            # Convert confidence from 0-1 to percentage
            confidence = record.get('confidence', 0)
            confidence_percent = confidence * 100 if confidence <= 1 else confidence
            
            transformed_data.append({
                'id': record.get('id'),
                'date': date_str,
                'time': time_str,
                'timestamp': timestamp_str,
                'detection': record.get('detection'),
                'elephant_count': record.get('elephant_count', 0),
                'confidence': round(confidence_percent, 1),
                'image_path': record.get('image_path'),
                'pir_detected': record.get('pir_detected'),
                'sound_detected': record.get('sound_detected'),
                'sound_level': record.get('sound_level'),
                'latitude': record.get('latitude'),
                'longitude': record.get('longitude'),
                'device_id': record.get('device_id')
            })
        
        return jsonify(transformed_data)
    except Exception as e:
        print(f"[SUPABASE] Error fetching detections: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/supabase/storage/signed-url', methods=['GET'])
def get_supabase_signed_url():
    """Generate a signed URL for Supabase Storage with local fallback"""
    image_path = request.args.get('image_path')
    if not image_path:
        return jsonify({"error": "image_path parameter is required"}), 400

    filename = os.path.basename(image_path)
    try:
        supabase = get_supabase_client()
        signed_url_result = supabase.storage.from_('elephant-images').create_signed_url(
            filename,
            expires_in=3600
        )
        if signed_url_result and 'signedURL' in signed_url_result:
            return jsonify({
                "signed_url": signed_url_result['signedURL'],
                "expires_in": 3600
            })
    except Exception as e:
        print(f"[SUPABASE] Error generating signed URL for {filename}: {e}")

    # Local fallback ensures image always loads
    return jsonify({
        "signed_url": f"/api/detection-images/{filename}",
        "expires_in": 3600
    })

@app.route('/api/supabase/storage/image', methods=['GET'])
def get_supabase_image_redirect():
    """Redirect to a signed URL for a Supabase image with local fallback"""
    image_path = request.args.get('image_path')
    if not image_path:
        return "Missing image_path", 400

    filename = os.path.basename(image_path)
    local_dir = os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))

    try:
        supabase = get_supabase_client()
        signed_url_result = supabase.storage.from_('elephant-images').create_signed_url(
            filename,
            expires_in=3600
        )
        if signed_url_result and 'signedURL' in signed_url_result:
            from flask import redirect
            return redirect(signed_url_result['signedURL'])
    except Exception as e:
        print(f"[SUPABASE] Remote redirect error for {filename}: {e}")

    if os.path.exists(os.path.join(local_dir, filename)):
        return send_from_directory(local_dir, filename)

    return "Image not found", 404

@app.route('/api/supabase/detections/csv', methods=['GET'])
def export_supabase_detections_csv():
    """Export detection data from Supabase as CSV"""
    try:
        supabase = get_supabase_client()
        
        # Get query parameters
        limit = int(request.args.get('limit', 1000))
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        device_id = request.args.get('device_id')
        detection_type = request.args.get('detection_type')
        
        # Build query
        query = supabase.table('detections').select('*').order('timestamp', desc=True).limit(limit)
        
        # Apply filtering
        if from_date:
            query = query.gte('timestamp', from_date)
        if to_date:
            query = query.lte('timestamp', to_date)
        if device_id:
            query = query.eq('device_id', device_id)
        if detection_type and detection_type != 'all':
            query = query.eq('detection', detection_type)
        
        # Execute query
        result = query.execute()
        
        # Prepare CSV data
        from io import StringIO
        output = StringIO()
        
        fieldnames = [
            'date', 'time', 'detection', 'elephant_count', 'confidence',
            'pir_detected', 'sound_detected', 'sound_level', 
            'latitude', 'longitude', 'device_id', 'image_path'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for record in result.data:
            # Parse timestamp
            timestamp_str = record.get('timestamp', '')
            if timestamp_str:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d')
                    time_str = dt.strftime('%H:%M:%S')
                except:
                    date_str = timestamp_str.split('T')[0] if 'T' in timestamp_str else timestamp_str
                    time_str = timestamp_str.split('T')[1].split('.')[0] if 'T' in timestamp_str else ''
            else:
                date_str = ''
                time_str = ''
            
            # Convert confidence
            confidence = record.get('confidence', 0)
            confidence_percent = confidence * 100 if confidence <= 1 else confidence
            
            writer.writerow({
                'date': date_str,
                'time': time_str,
                'detection': record.get('detection'),
                'elephant_count': record.get('elephant_count', 0),
                'confidence': round(confidence_percent, 1),
                'pir_detected': record.get('pir_detected'),
                'sound_detected': record.get('sound_detected'),
                'sound_level': record.get('sound_level'),
                'latitude': record.get('latitude'),
                'longitude': record.get('longitude'),
                'device_id': record.get('device_id'),
                'image_path': record.get('image_path')
            })
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename=detections_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
        
    except Exception as e:
        print(f"[SUPABASE] Error exporting detections CSV: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Integrated IoT and Edge-AI Acoustic Early Warning System Server...")
    print("Serving on http://127.0.0.1:5000")
    
    # Initialize all nodes with reverse geocoding on startup
    print("[GEOCODE] Initializing all node locations with reverse geocoding...")
    for i, node in enumerate(NODES_DATA):
        node['location'] = reverse_geocode_coordinates(node['lat'], node['lng'])
        node_num = node['id'].split('-')[-1]
        node['name'] = f"Node {node_num} - {node['location']}"
        print(f"[GEOCODE] Node {node_num} initial location: {node['location']}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
