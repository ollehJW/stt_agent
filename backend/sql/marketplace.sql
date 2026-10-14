CREATE TABLE IF NOT EXISTS wiavoice.market_voices (
 voice_id TEXT PRIMARY KEY CHECK (voice_id ~ '^[a-f0-9]{32}$'),
 user_id TEXT NOT NULL REFERENCES platform.users(user_id) ON DELETE RESTRICT,
 source_job_id TEXT NOT NULL,
 name VARCHAR(100) NOT NULL CHECK(length(btrim(name))>0),
 description VARCHAR(300) NOT NULL DEFAULT '',
 sample_text TEXT NOT NULL,
 reference_seconds DOUBLE PRECISION NOT NULL,
 sample_seconds DOUBLE PRECISION NOT NULL,
 consent_version TEXT NOT NULL,
 consent_text TEXT NOT NULL,
 consent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 deleted_at TIMESTAMPTZ,
 UNIQUE(user_id,source_job_id)
);
CREATE INDEX IF NOT EXISTS market_voices_created ON wiavoice.market_voices(created_at DESC) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS wiavoice.market_favorites (
 user_id TEXT NOT NULL REFERENCES platform.users(user_id) ON DELETE CASCADE,
 voice_id TEXT NOT NULL REFERENCES wiavoice.market_voices(voice_id) ON DELETE CASCADE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,voice_id)
);

ALTER TABLE wiavoice.market_voices ADD COLUMN IF NOT EXISTS gender TEXT CHECK (gender IN ('male','female'));

ALTER TABLE wiavoice.market_voices ADD COLUMN IF NOT EXISTS download_count BIGINT NOT NULL DEFAULT 0 CHECK (download_count >= 0);
CREATE INDEX IF NOT EXISTS market_voices_popular ON wiavoice.market_voices(download_count DESC,created_at DESC,voice_id) WHERE deleted_at IS NULL;
