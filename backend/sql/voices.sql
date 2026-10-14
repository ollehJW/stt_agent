CREATE TABLE IF NOT EXISTS wiavoice.voices (
    voice_id TEXT PRIMARY KEY CHECK (voice_id ~ '^[a-f0-9]{32}$'),
    user_id TEXT NOT NULL REFERENCES platform.users(user_id) ON DELETE RESTRICT,
    source_job_id TEXT NOT NULL CHECK (source_job_id ~ '^[a-f0-9]{32}$'),
    name VARCHAR(100) NOT NULL CHECK (length(btrim(name)) > 0),
    model TEXT NOT NULL CHECK (model IN ('qwen','fish','higgs')),
    speaker TEXT NOT NULL,
    emotion TEXT NOT NULL,
    text TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    generation_options JSONB NOT NULL DEFAULT '{}'::jsonb,
    duration_seconds DOUBLE PRECISION NOT NULL CHECK (duration_seconds > 0),
    sample_rate INTEGER NOT NULL CHECK (sample_rate > 0),
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    audio_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, source_job_id)
);
CREATE INDEX IF NOT EXISTS voices_user_created ON wiavoice.voices(user_id, created_at DESC, voice_id);
COMMENT ON TABLE wiavoice.voices IS 'User-saved TTS outputs, retained independently of platform login sessions';
