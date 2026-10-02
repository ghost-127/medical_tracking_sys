-- ========================================================================
-- MEDIPULSE MEDICAL TRACKING SYSTEM - SUPABASE DATABASE SCHEMA
-- ========================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. PROFILES TABLE (Linked with Supabase Auth Users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('ADMIN', 'NURSE', 'STAFF')),
    department VARCHAR(100) DEFAULT 'General Ward',
    shift VARCHAR(50) DEFAULT 'Morning (07:00 - 15:00)',
    employee_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    avatar_url TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. LOCATIONS TABLE
CREATE TABLE IF NOT EXISTS public.locations (
    location_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building VARCHAR(100) NOT NULL,
    floor VARCHAR(50) NOT NULL,
    department VARCHAR(100) NOT NULL,
    room VARCHAR(50) NOT NULL,
    bed_or_station VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. EQUIPMENT TABLE
CREATE TABLE IF NOT EXISTS public.equipment (
    equipment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_name VARCHAR(150) NOT NULL,
    category VARCHAR(100) NOT NULL,
    model_number VARCHAR(100) DEFAULT '',
    serial_number VARCHAR(100) DEFAULT '',
    manufacturer VARCHAR(100) DEFAULT '',
    current_location_id UUID REFERENCES public.locations(location_id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'IN_USE', 'RESERVED', 'UNDER_MAINTENANCE', 'MISSING', 'OUT_OF_SERVICE')),
    operational_status VARCHAR(50) DEFAULT 'OPTIMAL' CHECK (operational_status IN ('OPTIMAL', 'MINOR_ISSUE', 'CRITICAL_ERROR', 'NEEDS_SANITIZING')),
    maintenance_status VARCHAR(50) DEFAULT 'NORMAL' CHECK (maintenance_status IN ('NORMAL', 'UNDER_MAINTENANCE', 'SCHEDULED', 'OVERDUE')),
    battery_level INT CHECK (battery_level IS NULL OR (battery_level >= 0 AND battery_level <= 100)),
    is_wall_powered BOOLEAN DEFAULT FALSE,
    is_sanitized BOOLEAN DEFAULT TRUE,
    last_maintained_date TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    next_maintenance_date TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now() + interval '90 days'),
    current_assigned_patient VARCHAR(100),
    notes TEXT DEFAULT '',
    last_updated_by VARCHAR(100) DEFAULT 'System',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. QR CODES TABLE
CREATE TABLE IF NOT EXISTS public.qr_codes (
    qr_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES public.equipment(equipment_id) ON DELETE CASCADE,
    qr_url TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'REPLACED')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. MAINTENANCE TABLE
CREATE TABLE IF NOT EXISTS public.maintenance (
    maintenance_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES public.equipment(equipment_id) ON DELETE CASCADE,
    scheduled_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(30) DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    remarks TEXT DEFAULT '',
    technician_name VARCHAR(100),
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. COMPLAINTS TABLE
CREATE TABLE IF NOT EXISTS public.complaints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_number VARCHAR(50) NOT NULL UNIQUE,
    equipment_id UUID REFERENCES public.equipment(equipment_id) ON DELETE SET NULL,
    equipment_name VARCHAR(150),
    equipment_code VARCHAR(100),
    equipment_category VARCHAR(100),
    type VARCHAR(50) DEFAULT 'EQUIPMENT_PROBLEM',
    severity VARCHAR(30) DEFAULT 'MEDIUM' CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'EMERGENCY')),
    status VARCHAR(30) DEFAULT 'SUBMITTED' CHECK (status IN ('SUBMITTED', 'UNDER_REVIEW', 'ASSIGNED_TO_TECH', 'IN_PROGRESS', 'RESOLVED', 'ESCALATED', 'REJECTED')),
    nurse_id VARCHAR(100),
    nurse_name VARCHAR(100),
    nurse_department VARCHAR(100),
    reported_location VARCHAR(150),
    description TEXT NOT NULL,
    error_code VARCHAR(50),
    assigned_tech_name VARCHAR(100),
    resolution_summary TEXT,
    reported_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 7. NOTIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) DEFAULT 'GENERAL' CHECK (type IN ('GENERAL', 'COMPLAINT', 'MAINTENANCE', 'ALERT', 'ASSIGNMENT')),
    severity VARCHAR(30) DEFAULT 'INFO' CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL', 'SUCCESS')),
    target_role VARCHAR(20),
    target_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    reference_id VARCHAR(100),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 8. EQUIPMENT TELEMETRY TABLE (BLE / Sensor Readings)
CREATE TABLE IF NOT EXISTS public.equipment_telemetry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES public.equipment(equipment_id) ON DELETE CASCADE,
    battery_level INT,
    temperature_celsius NUMERIC(5,2),
    signal_rssi INT,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Row Level Security (RLS) policies
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equipment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qr_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Allow read access for authenticated profiles
CREATE POLICY "Public Profiles are viewable by authenticated users" ON public.profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Equipment viewable by authenticated users" ON public.equipment FOR SELECT TO authenticated USING (true);
CREATE POLICY "Locations viewable by authenticated users" ON public.locations FOR SELECT TO authenticated USING (true);
CREATE POLICY "QR codes viewable by authenticated users" ON public.qr_codes FOR SELECT TO authenticated USING (true);
CREATE POLICY "Maintenance viewable by authenticated users" ON public.maintenance FOR SELECT TO authenticated USING (true);
CREATE POLICY "Complaints viewable by authenticated users" ON public.complaints FOR SELECT TO authenticated USING (true);
CREATE POLICY "Notifications viewable by target or role" ON public.notifications FOR SELECT TO authenticated USING (true);
