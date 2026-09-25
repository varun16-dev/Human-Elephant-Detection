"""
Supabase Production Schema Migration
Generates SQL file + syncs auth users
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from supabase_client import get_supabase_admin_client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

def main():
    print("=" * 72)
    print("  SUPABASE PRODUCTION SCHEMA MIGRATION")
    print("=" * 72)
    
    sb = get_supabase_admin_client()
    
    # ----------------------------------------------------------
    # STEP 1: Try exec_sql RPC, create it if missing
    # ----------------------------------------------------------
    print("\n[SETUP] Checking exec_sql function...")
    
    rpc_available = False
    try:
        test = sb.rpc('exec_sql', {'query': 'SELECT 1 as test'}).execute()
        print("  [OK] exec_sql RPC function available")
        rpc_available = True
    except Exception as e:
        print(f"  [MISSING] exec_sql not found - will generate SQL file for manual steps")
    
    if not rpc_available:
        # Generate the SQL file containing everything including exec_sql creation
        sql_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migration_v1_production.sql')
        generate_full_sql(sql_file)
        
        print(f"\n  >> SQL file saved to: {sql_file}")
        print(f"  >> INSTRUCTIONS:")
        print(f"     1. Open Supabase Dashboard -> SQL Editor")
        print(f"     2. Paste the contents of migration_v1_production.sql")
        print(f"     3. Click 'Run'")
        print(f"     4. Then re-run this script to sync users (Step 8)")
        print(f"\n  Attempting Step 8 (sync users) now anyway...")
    
    # ----------------------------------------------------------
    # If RPC is available, execute migration steps via RPC
    # ----------------------------------------------------------
    if rpc_available:
        run_migration_via_rpc(sb)
    
    # ----------------------------------------------------------
    # STEP 8: SYNC AUTH USERS (always runs, doesn't need DDL)
    # ----------------------------------------------------------
    print("\n" + "=" * 72)
    print("  STEP 8: SYNC AUTH USERS INTO PROFILES")
    print("=" * 72)
    
    try:
        users = sb.auth.admin.list_users()
        user_list = users if isinstance(users, list) else getattr(users, 'users', users)
        
        for u in user_list:
            um = getattr(u, 'user_metadata', {}) or {}
            am = getattr(u, 'app_metadata', {}) or {}
            
            profile_data = {
                'user_id': u.id,
                'full_name': um.get('full_name') or um.get('name') or u.email,
                'email': u.email,
                'phone': um.get('phone', ''),
                'role': um.get('role') or am.get('role', 'villager'),
                'location': um.get('location') or um.get('zone', ''),
                'status': 'active',
            }
            
            try:
                sb.table('profiles').upsert(profile_data, on_conflict='user_id').execute()
                print(f"  [OK] Synced: {u.email} (role={profile_data['role']})")
            except Exception as e:
                err_msg = str(e)
                if 'not found in the schema cache' in err_msg or 'PGRST' in err_msg:
                    print(f"  [SKIP] profiles table doesn't exist yet - run SQL first!")
                    break
                else:
                    print(f"  [FAIL] {u.email}: {err_msg[:100]}")
    except Exception as e:
        print(f"  [FAIL] Could not list users: {str(e)[:100]}")
    
    # ----------------------------------------------------------
    # VERIFICATION
    # ----------------------------------------------------------
    print("\n" + "=" * 72)
    print("  VERIFICATION: POST-MIGRATION AUDIT")
    print("=" * 72)
    
    all_tables = [
        'raw_sensor_data', 'devices', 'detections', 'alerts',
        'profiles', 'system_settings', 'notification_config', 'notification_history'
    ]
    
    for t in all_tables:
        try:
            r = sb.table(t).select('*', count='exact').limit(0).execute()
            ct = r.count if hasattr(r, 'count') and r.count is not None else '?'
            print(f"  [OK] {t}: accessible ({ct} rows)")
        except Exception as e:
            err_msg = str(e)
            if 'not found' in err_msg.lower() or 'PGRST' in err_msg:
                print(f"  [MISSING] {t}: table doesn't exist yet - run SQL first!")
            else:
                print(f"  [FAIL] {t}: {err_msg[:80]}")
    
    # Verify profiles
    print("\n  Profiles:")
    try:
        profiles = sb.table('profiles').select('*').execute()
        for p in profiles.data:
            print(f"    -> {p.get('email')} | role={p.get('role')} | status={p.get('status')}")
        if not profiles.data:
            print("    (empty - run SQL migration first, then re-run this script)")
    except Exception as e:
        print(f"    [SKIP] {str(e)[:80]}")
    
    # Verify system settings
    print("\n  System settings:")
    try:
        settings = sb.table('system_settings').select('setting_key, setting_value').execute()
        for s in settings.data:
            print(f"    -> {s['setting_key']} = {s['setting_value']}")
        if not settings.data:
            print("    (empty - run SQL migration first)")
    except Exception as e:
        print(f"    [SKIP] {str(e)[:80]}")
    
    print("\n" + "=" * 72)
    print("  MIGRATION SCRIPT COMPLETE")
    print("=" * 72)


def run_migration_via_rpc(sb):
    """Execute all DDL statements via the exec_sql RPC function"""
    
    statements = get_all_statements()
    
    total = len(statements)
    success = 0
    skipped = 0
    failed = 0
    
    for i, (desc, sql) in enumerate(statements, 1):
        sql = sql.strip()
        if not sql:
            continue
        
        print(f"\n  [{i}/{total}] {desc}...")
        
        try:
            result = sb.rpc('exec_sql', {'query': sql}).execute()
            data = result.data
            if isinstance(data, dict) and data.get('success') is False:
                error = data.get('error', 'Unknown error')
                if 'already exists' in error.lower() or 'duplicate' in error.lower():
                    print(f"    [SKIP] Already exists: {error[:80]}")
                    skipped += 1
                else:
                    print(f"    [FAIL] {error[:120]}")
                    failed += 1
            else:
                print(f"    [OK] Done")
                success += 1
        except Exception as e:
            err = str(e)
            if 'already exists' in err.lower() or 'duplicate' in err.lower():
                print(f"    [SKIP] Already exists")
                skipped += 1
            else:
                print(f"    [FAIL] {err[:120]}")
                failed += 1
    
    print(f"\n  Summary: {success} succeeded, {skipped} skipped, {failed} failed (out of {total})")
    
    # Insert system settings via Python client (not DDL)
    print("\n  Inserting default system settings...")
    settings = [
        ('NOTIFICATION_COOLDOWN_SECONDS', '300', 'Minimum seconds between duplicate alerts per device'),
        ('MAX_ALERTS_PER_DETECTION', '5', 'Maximum alerts per single detection event'),
        ('DEVICE_OFFLINE_TIMEOUT_MINUTES', '15', 'Mark device offline after N minutes without heartbeat'),
        ('DEFAULT_CONFIDENCE_THRESHOLD', '75', 'Minimum confidence for elephant detection alerts'),
        ('ENABLE_SMS_NOTIFICATIONS', 'true', 'Enable SMS alerts via Twilio'),
        ('ENABLE_EMAIL_NOTIFICATIONS', 'true', 'Enable Email alerts'),
        ('ENABLE_WHATSAPP_NOTIFICATIONS', 'false', 'Enable WhatsApp alerts via Twilio'),
    ]
    for key, val, desc_text in settings:
        try:
            sb.table('system_settings').upsert({
                'setting_key': key,
                'setting_value': val,
                'description': desc_text,
            }, on_conflict='setting_key').execute()
            print(f"    [OK] {key} = {val}")
        except Exception as e:
            print(f"    [FAIL] {key}: {str(e)[:80]}")


def get_all_statements():
    """Return all DDL statements as (description, sql) tuples"""
    stmts = []
    
    # STEP 1: ALTER existing tables
    stmts.append(("Add last_heartbeat_at to devices",
        "ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ"))
    stmts.append(("Add battery_level to devices",
        "ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS battery_level INTEGER"))
    stmts.append(("Add firmware_version to devices",
        "ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(50)"))
    stmts.append(("Add updated_at to devices",
        "ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"))
    stmts.append(("Add incident_status to detections",
        "ALTER TABLE public.detections ADD COLUMN IF NOT EXISTS incident_status VARCHAR(50) DEFAULT 'pending'"))
    stmts.append(("Add alert_sent to detections",
        "ALTER TABLE public.detections ADD COLUMN IF NOT EXISTS alert_sent BOOLEAN DEFAULT FALSE"))
    stmts.append(("Add recipient to alerts",
        "ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS recipient VARCHAR(255)"))
    stmts.append(("Add error_message to alerts",
        "ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS error_message TEXT"))
    stmts.append(("Add cooldown_triggered_at to alerts",
        "ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS cooldown_triggered_at TIMESTAMPTZ"))
    
    # STEP 2: CREATE profiles table
    stmts.append(("Create profiles table", """
        CREATE TABLE IF NOT EXISTS public.profiles (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
          full_name VARCHAR(255),
          email VARCHAR(255),
          phone VARCHAR(20),
          role VARCHAR(50) NOT NULL DEFAULT 'villager',
          location VARCHAR(255),
          area_coverage VARCHAR(255),
          status VARCHAR(50) DEFAULT 'active',
          created_by UUID,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    stmts.append(("Create profiles role index",
        "CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role)"))
    stmts.append(("Create profiles status index",
        "CREATE INDEX IF NOT EXISTS idx_profiles_status ON public.profiles(status)"))
    stmts.append(("Create profiles user_id index",
        "CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON public.profiles(user_id)"))
    
    # STEP 3: CREATE system_settings table
    stmts.append(("Create system_settings table", """
        CREATE TABLE IF NOT EXISTS public.system_settings (
          id BIGSERIAL PRIMARY KEY,
          setting_key VARCHAR(255) UNIQUE NOT NULL,
          setting_value TEXT,
          description TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    
    # STEP 4: CREATE notification tables
    stmts.append(("Create notification_config table", """
        CREATE TABLE IF NOT EXISTS public.notification_config (
          id BIGSERIAL PRIMARY KEY,
          user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
          alert_type VARCHAR(50) NOT NULL,
          recipient VARCHAR(255) NOT NULL,
          enabled BOOLEAN DEFAULT TRUE,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    stmts.append(("Create notification_config user index",
        "CREATE INDEX IF NOT EXISTS idx_notification_config_user ON public.notification_config(user_id)"))
    stmts.append(("Create notification_history table", """
        CREATE TABLE IF NOT EXISTS public.notification_history (
          id BIGSERIAL PRIMARY KEY,
          alert_id UUID,
          user_id UUID,
          alert_type VARCHAR(50) NOT NULL,
          recipient VARCHAR(255),
          message TEXT,
          status VARCHAR(50) DEFAULT 'pending',
          error_message TEXT,
          attempts INTEGER DEFAULT 0,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          sent_at TIMESTAMPTZ
        )"""))
    stmts.append(("Create notification_history alert index",
        "CREATE INDEX IF NOT EXISTS idx_notification_history_alert ON public.notification_history(alert_id)"))
    stmts.append(("Create notification_history user index",
        "CREATE INDEX IF NOT EXISTS idx_notification_history_user ON public.notification_history(user_id)"))
    stmts.append(("Create notification_history created index",
        "CREATE INDEX IF NOT EXISTS idx_notification_history_created ON public.notification_history(created_at DESC)"))
    
    # STEP 5: ADD missing indexes
    indexes = [
        ("raw_sensor_data(device_id)", "idx_raw_sensor_device", "raw_sensor_data", "device_id"),
        ("raw_sensor_data(timestamp)", "idx_raw_sensor_timestamp", "raw_sensor_data", "timestamp DESC"),
        ("raw_sensor_data(created_at)", "idx_raw_sensor_created", "raw_sensor_data", "created_at DESC"),
        ("devices(status)", "idx_devices_status", "devices", "status"),
        ("devices(last_seen)", "idx_devices_last_seen", "devices", "last_seen DESC"),
        ("detections(device_id)", "idx_detections_device", "detections", "device_id"),
        ("detections(timestamp)", "idx_detections_timestamp", "detections", "timestamp DESC"),
        ("detections(incident_status)", "idx_detections_status", "detections", "incident_status"),
        ("detections(created_at)", "idx_detections_created", "detections", "created_at DESC"),
        ("alerts(detection_id)", "idx_alerts_detection", "alerts", "detection_id"),
        ("alerts(status)", "idx_alerts_status", "alerts", "status"),
        ("alerts(created_at)", "idx_alerts_created", "alerts", "created_at DESC"),
        ("alerts(device_id)", "idx_alerts_device", "alerts", "device_id"),
    ]
    for desc, idx_name, table, cols in indexes:
        stmts.append((f"Index {desc}",
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON public.{table}({cols})"))
    
    # STEP 6: ENABLE RLS + CREATE POLICIES
    rls_tables = ['raw_sensor_data', 'devices', 'detections', 'alerts',
                  'profiles', 'notification_config', 'notification_history', 'system_settings']
    for t in rls_tables:
        stmts.append((f"Enable RLS on {t}",
            f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY"))
    
    # Forest Officer full access
    fo_policies = {
        'raw_sensor_data': 'fo_full_raw_sensor',
        'devices': 'fo_full_devices',
        'detections': 'fo_full_detections',
        'alerts': 'fo_full_alerts',
        'profiles': 'fo_full_profiles',
        'notification_config': 'fo_full_notification_config',
        'notification_history': 'fo_full_notification_history',
        'system_settings': 'fo_full_system_settings',
    }
    for table, policy_name in fo_policies.items():
        stmts.append((f"FO full access -> {table}",
            f"""CREATE POLICY "{policy_name}" ON public.{table} FOR ALL
              USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'))"""))
    
    # Police policies
    stmts.append(("Police read confirmed detections",
        """CREATE POLICY "police_read_confirmed_detections" ON public.detections FOR SELECT
          USING (
            auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active')
            AND detection = 'ELEPHANT_DETECTED'
            AND confidence >= 75
          )"""))
    stmts.append(("Police update incident_status",
        """CREATE POLICY "police_update_incident_status" ON public.detections FOR UPDATE
          USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active'))
          WITH CHECK (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active'))"""))
    stmts.append(("Police read alerts",
        """CREATE POLICY "police_read_alerts" ON public.alerts FOR SELECT
          USING (
            auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active')
            AND status != 'failed'
          )"""))
    stmts.append(("Police read devices",
        """CREATE POLICY "police_read_devices" ON public.devices FOR SELECT
          USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active'))"""))
    
    # Villager policy
    stmts.append(("Villager read active alerts",
        """CREATE POLICY "villager_read_active_alerts" ON public.detections FOR SELECT
          USING (
            auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'villager' AND status = 'active')
            AND detection = 'ELEPHANT_DETECTED'
            AND confidence >= 75
            AND incident_status NOT IN ('pending', 'resolved')
          )"""))
    
    # Shared policies
    stmts.append(("Users read own profile",
        """CREATE POLICY "users_read_own_profile" ON public.profiles FOR SELECT
          USING (auth.uid() = user_id)"""))
    stmts.append(("Users manage own notification config",
        """CREATE POLICY "users_manage_own_notif_config" ON public.notification_config FOR ALL
          USING (auth.uid() = user_id)"""))
    stmts.append(("Users read own notification history",
        """CREATE POLICY "users_read_own_notif_history" ON public.notification_history FOR SELECT
          USING (auth.uid() = user_id)"""))
    stmts.append(("Authenticated read system settings",
        """CREATE POLICY "authenticated_read_settings" ON public.system_settings FOR SELECT
          USING (auth.role() = 'authenticated')"""))
    
    # STEP 7: AUTH -> PROFILE SYNC TRIGGER
    stmts.append(("Create handle_new_auth_user function", """
        CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
        RETURNS trigger AS $$
        BEGIN
          INSERT INTO public.profiles (user_id, full_name, email, phone, role, location, status, created_at)
          VALUES (
            NEW.id,
            COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', NEW.email),
            NEW.email,
            COALESCE(NEW.raw_user_meta_data->>'phone', ''),
            COALESCE(NEW.raw_app_meta_data->>'role', NEW.raw_user_meta_data->>'role', 'villager'),
            COALESCE(NEW.raw_user_meta_data->>'location', NEW.raw_user_meta_data->>'zone', ''),
            COALESCE(NEW.raw_user_meta_data->>'status', 'active'),
            NOW()
          )
          ON CONFLICT (user_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            email = EXCLUDED.email,
            role = EXCLUDED.role,
            phone = EXCLUDED.phone,
            location = EXCLUDED.location,
            status = EXCLUDED.status,
            updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER"""))
    stmts.append(("Drop existing auth trigger",
        "DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users"))
    stmts.append(("Create auth user sync trigger",
        """CREATE TRIGGER on_auth_user_created
          AFTER INSERT OR UPDATE ON auth.users
          FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user()"""))
    
    return stmts


def generate_full_sql(filepath):
    """Generate the complete SQL file for Supabase Dashboard"""
    
    full_sql = """-- ================================================================
-- PRODUCTION SCHEMA MIGRATION v1.0
-- Integrated IoT & Edge-AI Acoustic Early Warning System
-- Execute in: Supabase Dashboard -> SQL Editor -> Run
-- ================================================================

-- Create exec_sql helper (enables future programmatic migrations)
CREATE OR REPLACE FUNCTION public.exec_sql(query text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
  EXECUTE query;
  RETURN json_build_object('success', true);
EXCEPTION WHEN OTHERS THEN
  RETURN json_build_object('success', false, 'error', SQLERRM);
END;
$$;

-- ============================================
-- STEP 1: ALTER EXISTING TABLES
-- ============================================
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ;
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS battery_level INTEGER;
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(50);
ALTER TABLE public.devices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE public.detections ADD COLUMN IF NOT EXISTS incident_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE public.detections ADD COLUMN IF NOT EXISTS alert_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS recipient VARCHAR(255);
ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS cooldown_triggered_at TIMESTAMPTZ;

-- ============================================
-- STEP 2: CREATE PROFILES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name VARCHAR(255),
  email VARCHAR(255),
  phone VARCHAR(20),
  role VARCHAR(50) NOT NULL DEFAULT 'villager',
  location VARCHAR(255),
  area_coverage VARCHAR(255),
  status VARCHAR(50) DEFAULT 'active',
  created_by UUID,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);
CREATE INDEX IF NOT EXISTS idx_profiles_status ON public.profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON public.profiles(user_id);

-- ============================================
-- STEP 3: CREATE SYSTEM_SETTINGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS public.system_settings (
  id BIGSERIAL PRIMARY KEY,
  setting_key VARCHAR(255) UNIQUE NOT NULL,
  setting_value TEXT,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.system_settings (setting_key, setting_value, description) VALUES
  ('NOTIFICATION_COOLDOWN_SECONDS', '300', 'Minimum seconds between duplicate alerts per device'),
  ('MAX_ALERTS_PER_DETECTION', '5', 'Maximum alerts per single detection event'),
  ('DEVICE_OFFLINE_TIMEOUT_MINUTES', '15', 'Mark device offline after N minutes without heartbeat'),
  ('DEFAULT_CONFIDENCE_THRESHOLD', '75', 'Minimum confidence for elephant detection alerts'),
  ('ENABLE_SMS_NOTIFICATIONS', 'true', 'Enable SMS alerts via Twilio'),
  ('ENABLE_EMAIL_NOTIFICATIONS', 'true', 'Enable Email alerts'),
  ('ENABLE_WHATSAPP_NOTIFICATIONS', 'false', 'Enable WhatsApp alerts via Twilio')
ON CONFLICT (setting_key) DO NOTHING;

-- ============================================
-- STEP 4: CREATE NOTIFICATION TABLES
-- ============================================
CREATE TABLE IF NOT EXISTS public.notification_config (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  alert_type VARCHAR(50) NOT NULL,
  recipient VARCHAR(255) NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notification_config_user ON public.notification_config(user_id);

CREATE TABLE IF NOT EXISTS public.notification_history (
  id BIGSERIAL PRIMARY KEY,
  alert_id UUID,
  user_id UUID,
  alert_type VARCHAR(50) NOT NULL,
  recipient VARCHAR(255),
  message TEXT,
  status VARCHAR(50) DEFAULT 'pending',
  error_message TEXT,
  attempts INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notification_history_alert ON public.notification_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_notification_history_user ON public.notification_history(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_history_created ON public.notification_history(created_at DESC);

-- ============================================
-- STEP 5: ADD MISSING INDEXES
-- ============================================
CREATE INDEX IF NOT EXISTS idx_raw_sensor_device ON public.raw_sensor_data(device_id);
CREATE INDEX IF NOT EXISTS idx_raw_sensor_timestamp ON public.raw_sensor_data(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_sensor_created ON public.raw_sensor_data(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_devices_status ON public.devices(status);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON public.devices(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_detections_device ON public.detections(device_id);
CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON public.detections(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_detections_status ON public.detections(incident_status);
CREATE INDEX IF NOT EXISTS idx_detections_created ON public.detections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_detection ON public.alerts(detection_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON public.alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON public.alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON public.alerts(device_id);

-- ============================================
-- STEP 6: ENABLE RLS ON ALL TABLES
-- ============================================
ALTER TABLE public.raw_sensor_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

-- FOREST OFFICER: Full access to everything
CREATE POLICY "fo_full_raw_sensor" ON public.raw_sensor_data FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_devices" ON public.devices FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_detections" ON public.detections FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_alerts" ON public.alerts FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_profiles" ON public.profiles FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_notification_config" ON public.notification_config FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_notification_history" ON public.notification_history FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));
CREATE POLICY "fo_full_system_settings" ON public.system_settings FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'forest_officer' AND status = 'active'));

-- POLICE: Read confirmed detections + update incident status
CREATE POLICY "police_read_confirmed_detections" ON public.detections FOR SELECT
  USING (
    auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active')
    AND detection = 'ELEPHANT_DETECTED' AND confidence >= 75
  );
CREATE POLICY "police_update_incident_status" ON public.detections FOR UPDATE
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active'))
  WITH CHECK (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active'));
CREATE POLICY "police_read_alerts" ON public.alerts FOR SELECT
  USING (
    auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active')
    AND status != 'failed'
  );
CREATE POLICY "police_read_devices" ON public.devices FOR SELECT
  USING (auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'police' AND status = 'active'));

-- VILLAGER: Read active elephant alerts only
CREATE POLICY "villager_read_active_alerts" ON public.detections FOR SELECT
  USING (
    auth.uid() IN (SELECT user_id FROM public.profiles WHERE role = 'villager' AND status = 'active')
    AND detection = 'ELEPHANT_DETECTED' AND confidence >= 75
    AND incident_status NOT IN ('pending', 'resolved')
  );

-- ALL USERS: Read own data
CREATE POLICY "users_read_own_profile" ON public.profiles FOR SELECT
  USING (auth.uid() = user_id);
CREATE POLICY "users_manage_own_notif_config" ON public.notification_config FOR ALL
  USING (auth.uid() = user_id);
CREATE POLICY "users_read_own_notif_history" ON public.notification_history FOR SELECT
  USING (auth.uid() = user_id);
CREATE POLICY "authenticated_read_settings" ON public.system_settings FOR SELECT
  USING (auth.role() = 'authenticated');

-- ============================================
-- STEP 7: AUTH USER -> PROFILE SYNC TRIGGER
-- ============================================
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (user_id, full_name, email, phone, role, location, status, created_at)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'phone', ''),
    COALESCE(NEW.raw_app_meta_data->>'role', NEW.raw_user_meta_data->>'role', 'villager'),
    COALESCE(NEW.raw_user_meta_data->>'location', NEW.raw_user_meta_data->>'zone', ''),
    COALESCE(NEW.raw_user_meta_data->>'status', 'active'),
    NOW()
  )
  ON CONFLICT (user_id) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    email = EXCLUDED.email,
    role = EXCLUDED.role,
    phone = EXCLUDED.phone,
    location = EXCLUDED.location,
    status = EXCLUDED.status,
    updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT OR UPDATE ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();

-- ============================================
-- MIGRATION COMPLETE
-- After running this, re-run migrate_production_schema.py
-- to sync existing auth users into profiles (Step 8)
-- ============================================
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_sql)


if __name__ == '__main__':
    main()
