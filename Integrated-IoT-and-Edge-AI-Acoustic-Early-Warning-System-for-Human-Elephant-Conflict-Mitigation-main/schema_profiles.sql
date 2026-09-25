-- ==============================================================================
-- ELEPHANT EARLY WARNING SYSTEM - PROFILES & USER MANAGEMENT SCHEMA
-- Supabase PostgreSQL Table with Row Level Security (RLS)
-- ==============================================================================

-- 1. Create profiles table
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    role TEXT NOT NULL CHECK (role IN ('forest_officer', 'villager', 'police')),
    location TEXT,
    status TEXT DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 3. RLS Policies
-- Policy A: Forest Officers have full access (select, insert, update, delete) to manage users
CREATE POLICY "Forest Officers have administrative access to all profiles"
ON public.profiles
FOR ALL
USING (
    coalesce(auth.jwt() ->> 'role', '') = 'forest_officer' OR
    coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'forest_officer' OR
    coalesce(auth.jwt() -> 'user_metadata' ->> 'role', '') = 'forest_officer'
);

-- Policy B: Villagers and Police can only view their own profile
CREATE POLICY "Villagers and Police can view only their own profile"
ON public.profiles
FOR SELECT
USING (
    auth.uid() = user_id
);

-- Policy C: Service Role key bypasses RLS for administrative server backend operations
-- (Built-in Supabase behavior when using service_role key server-side)

-- 4. Automatically sync new Auth users into Profiles table
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger AS $$
BEGIN
    INSERT INTO public.profiles (user_id, full_name, email, phone, role, location, status, created_at)
    VALUES (
        new.id,
        COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email),
        new.email,
        COALESCE(new.raw_user_meta_data->>'phone', ''),
        COALESCE(new.raw_app_meta_data->>'role', new.raw_user_meta_data->>'role', 'villager'),
        COALESCE(new.raw_user_meta_data->>'location', new.raw_user_meta_data->>'zone', 'Bannerghatta Range'),
        COALESCE(new.raw_user_meta_data->>'status', 'Active'),
        now()
    )
    ON CONFLICT (user_id) DO UPDATE SET
        full_name = EXCLUDED.full_name,
        role = EXCLUDED.role,
        phone = EXCLUDED.phone,
        location = EXCLUDED.location,
        status = EXCLUDED.status,
        updated_at = now();
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger on auth.users table
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();
