-- ==============================================================================
-- Migration: 001_create_notifications_tables.sql
-- Description: Creates notifications, push_subscriptions, notification_preferences,
--              and notification_deliveries tables with indexes and RLS policies.
-- Target DB: Supabase PostgreSQL / Standard PostgreSQL 13+
-- ==============================================================================

-- 1. Ensure required extensions exist for UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- Table A: notifications
-- ==============================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP WITH TIME ZONE NULL
);

-- Indexes for notifications
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);

-- ==============================================================================
-- Table B: push_subscriptions
-- ==============================================================================
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    device_name VARCHAR(100) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE NULL,
    disabled_at TIMESTAMP WITH TIME ZONE NULL
);

-- Unique index to prevent duplicate active subscriptions for the same endpoint
CREATE UNIQUE INDEX IF NOT EXISTS uq_push_subscriptions_active_endpoint 
ON push_subscriptions(endpoint) 
WHERE disabled_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id);

-- ==============================================================================
-- Table C: notification_preferences
-- ==============================================================================
CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    push_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    category_settings JSONB NOT NULL DEFAULT '{"ai": true, "finance": true, "security": true, "reminders": true, "system": true}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ==============================================================================
-- Table D: notification_deliveries
-- ==============================================================================
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id VARCHAR(36) PRIMARY KEY,
    notification_id VARCHAR(36) NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    subscription_id VARCHAR(36) NOT NULL REFERENCES push_subscriptions(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMP WITH TIME ZONE NULL,
    sent_at TIMESTAMP WITH TIME ZONE NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for pending deliveries and worker retry scheduling
CREATE INDEX IF NOT EXISTS idx_notification_deliveries_pending 
ON notification_deliveries(status, next_retry_at) 
WHERE status IN ('pending', 'retrying');

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_notification ON notification_deliveries(notification_id);

-- ==============================================================================
-- Row-Level Security (RLS) Policies (For Supabase Direct-Access Security)
-- ==============================================================================
-- Enable RLS on all notification tables
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_deliveries ENABLE ROW LEVEL SECURITY;

-- Notifications Policy: Users can only view/update their own notifications
DROP POLICY IF EXISTS notifications_user_isolation ON notifications;
CREATE POLICY notifications_user_isolation ON notifications
    FOR ALL
    USING (user_id = (NULLIF(current_setting('request.jwt.claims', true)::jsonb->>'user_id', '')::INTEGER));

-- Push Subscriptions Policy: Users can only manage their own subscriptions
DROP POLICY IF EXISTS push_subscriptions_user_isolation ON push_subscriptions;
CREATE POLICY push_subscriptions_user_isolation ON push_subscriptions
    FOR ALL
    USING (user_id = (NULLIF(current_setting('request.jwt.claims', true)::jsonb->>'user_id', '')::INTEGER));

-- Preferences Policy: Users can only manage their own preferences
DROP POLICY IF EXISTS notification_preferences_user_isolation ON notification_preferences;
CREATE POLICY notification_preferences_user_isolation ON notification_preferences
    FOR ALL
    USING (user_id = (NULLIF(current_setting('request.jwt.claims', true)::jsonb->>'user_id', '')::INTEGER));

-- Deliveries Policy: Restrict direct client access; backend service role manages deliveries
DROP POLICY IF EXISTS notification_deliveries_service_only ON notification_deliveries;
CREATE POLICY notification_deliveries_service_only ON notification_deliveries
    FOR ALL
    USING (current_setting('request.jwt.claims', true)::jsonb->>'role' = 'service_role');

-- ==============================================================================
-- Rollback Instructions (Execute in reverse order if needed):
-- 
-- DROP TABLE IF EXISTS notification_deliveries CASCADE;
-- DROP TABLE IF EXISTS notification_preferences CASCADE;
-- DROP TABLE IF EXISTS push_subscriptions CASCADE;
-- DROP TABLE IF EXISTS notifications CASCADE;
-- ==============================================================================
