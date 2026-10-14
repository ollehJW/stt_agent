CREATE TABLE IF NOT EXISTS wiavoice.generation_runs (
 job_id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES platform.users(user_id) ON DELETE CASCADE,
 model TEXT NOT NULL,
 voice TEXT NOT NULL,
 emotion TEXT NOT NULL,
 purpose TEXT NOT NULL DEFAULT 'generation',
 character_count INTEGER NOT NULL,
 status TEXT NOT NULL,
 audio_seconds DOUBLE PRECISION,
 generation_seconds DOUBLE PRECISION,
 trimmed_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
 error_message TEXT,
 created_at TIMESTAMPTZ NOT NULL,
 started_at TIMESTAMPTZ,
 completed_at TIMESTAMPTZ,
 recorded_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE wiavoice.generation_runs ADD COLUMN IF NOT EXISTS text TEXT;
CREATE INDEX IF NOT EXISTS generation_runs_created ON wiavoice.generation_runs(created_at DESC,job_id);
CREATE INDEX IF NOT EXISTS generation_runs_user_created ON wiavoice.generation_runs(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS wiavoice.admin_audit (
 audit_id BIGSERIAL PRIMARY KEY,
 actor_id TEXT REFERENCES platform.users(user_id) ON DELETE SET NULL,
 target_id TEXT NOT NULL,
 action TEXT NOT NULL,
 reason TEXT NOT NULL,
 before_state JSONB NOT NULL,
 after_state JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS admin_audit_target ON wiavoice.admin_audit(target_id,created_at DESC);
ALTER TABLE wiavoice.market_voices ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ;
ALTER TABLE wiavoice.market_voices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE TABLE IF NOT EXISTS wiavoice.download_events (
 event_id BIGSERIAL PRIMARY KEY,
 voice_id TEXT NOT NULL REFERENCES wiavoice.market_voices(voice_id) ON DELETE CASCADE,
 user_id TEXT REFERENCES platform.users(user_id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS download_events_created ON wiavoice.download_events(created_at DESC);
CREATE TABLE IF NOT EXISTS wiavoice.admin_metadata (
 key TEXT PRIMARY KEY,
 value TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO wiavoice.admin_metadata(key) VALUES ('tracking_started_at') ON CONFLICT DO NOTHING;
