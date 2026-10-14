ALTER TABLE wiavoice.voices ALTER COLUMN source_job_id DROP NOT NULL;
ALTER TABLE wiavoice.voices DROP CONSTRAINT IF EXISTS voices_model_check;
ALTER TABLE wiavoice.voices ADD CONSTRAINT voices_model_check CHECK(model IN ('qwen','fish','higgs','merged'));
CREATE TABLE IF NOT EXISTS wiavoice.merge_action (
    action_id TEXT PRIMARY KEY CHECK(action_id ~ '^[a-f0-9]{32}$'),
    user_id TEXT NOT NULL REFERENCES platform.users(user_id) ON DELETE RESTRICT,
    request_id TEXT NOT NULL CHECK(request_id ~ '^[a-f0-9]{32}$'),
    request_hash CHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL CHECK(length(btrim(name))>0),
    input_voices JSONB NOT NULL CHECK(jsonb_typeof(input_voices)='array' AND jsonb_array_length(input_voices) BETWEEN 2 AND 20),
    gaps_seconds JSONB NOT NULL CHECK(jsonb_typeof(gaps_seconds)='array' AND jsonb_array_length(gaps_seconds)=jsonb_array_length(input_voices)-1),
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed')),
    progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
    result_voice_id TEXT REFERENCES wiavoice.voices(voice_id) ON DELETE RESTRICT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id,request_id)
);
CREATE INDEX IF NOT EXISTS merge_action_user_created ON wiavoice.merge_action(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS merge_action_queue ON wiavoice.merge_action(created_at) WHERE status='queued';
