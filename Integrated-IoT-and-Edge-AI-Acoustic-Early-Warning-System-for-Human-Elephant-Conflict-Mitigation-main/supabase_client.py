"""
Supabase Client Configuration
Integrated IoT and Edge-AI Acoustic Early Warning System
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_PUBLISHABLE_KEY = os.getenv('SUPABASE_PUBLISHABLE_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

# Validate environment variables
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is not set")

# Use service role key for backend operations to bypass RLS policies
SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_PUBLISHABLE_KEY
if not SUPABASE_KEY:
    raise ValueError("Neither SUPABASE_SERVICE_ROLE_KEY nor SUPABASE_PUBLISHABLE_KEY is set")

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase_client() -> Client:
    """Get the Supabase client instance"""
    return supabase

def get_supabase_admin_client() -> Client:
    """Get an isolated Supabase client initialized with service_role key for administrative operations"""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY)

def get_auth_client() -> Client:
    """Get an isolated client instance for user authentication without polluting admin credentials"""
    return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY or SUPABASE_KEY)

def get_supabase_url() -> str:
    """Get the Supabase URL"""
    return SUPABASE_URL

def get_supabase_key() -> str:
    """Get the Supabase publishable key"""
    return SUPABASE_PUBLISHABLE_KEY