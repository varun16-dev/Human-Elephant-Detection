-- ================================================================
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
  recipient TEXT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notification_config_user ON public.notification_config(user_id);

CREATE TABLE IF NOT EXISTS public.notification_history (
  id BIGSERIAL PRIMARY KEY,
  alert_id UUID,
  user_id UUID,
  alert_type VARCHAR(50) NOT NULL,
  recipient TEXT,
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
