-- Sentinel persistence. SQLite for the demo; DDL is Postgres-compatible
-- apart from the trigger syntax, which is noted inline.
-- LangGraph owns its own checkpoint tables in a separate file.

CREATE TABLE IF NOT EXISTS scopes (
    scope_id          TEXT PRIMARY KEY,
    target_id         TEXT NOT NULL,
    target_endpoint   TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    signed_hash       TEXT NOT NULL,
    authorizer        TEXT NOT NULL,
    expiry_timestamp  TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

-- Write-once enforcement. repo.py exposes no UPDATE path; this is the
-- backstop if someone reaches for the DB directly.
CREATE TRIGGER IF NOT EXISTS scopes_immutable
BEFORE UPDATE ON scopes
BEGIN
    SELECT RAISE(ABORT, 'scopes are write-once');
END;

CREATE TRIGGER IF NOT EXISTS scopes_no_delete
BEFORE DELETE ON scopes
BEGIN
    SELECT RAISE(ABORT, 'scopes are write-once');
END;

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    scope_id     TEXT NOT NULL REFERENCES scopes(scope_id),
    status       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    budget_json  TEXT NOT NULL,
    abort_reason TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id       TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES runs(run_id),
    attack_category  TEXT NOT NULL,
    severity         REAL NOT NULL,
    confirmed        INTEGER NOT NULL,
    provenance       TEXT NOT NULL DEFAULT 'live',
    minimized_prompt TEXT,
    mitigation       TEXT,
    finding_json     TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trace_entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    node         TEXT NOT NULL,
    model        TEXT NOT NULL,
    ts           TEXT NOT NULL,
    latency_ms   INTEGER NOT NULL,
    tokens_in    INTEGER NOT NULL,
    tokens_out   INTEGER NOT NULL,
    usd          REAL NOT NULL,
    input_json   TEXT NOT NULL,
    output_json  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trace_run ON trace_entries(run_id, id);

CREATE TABLE IF NOT EXISTS interceptor_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    attack_id      TEXT,
    turn           INTEGER,
    tool_name      TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    executed       INTEGER NOT NULL,
    result_json    TEXT,
    flagged        INTEGER NOT NULL DEFAULT 0,
    flag_reason    TEXT,
    ts             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interceptor_run ON interceptor_log(run_id, id);

-- Cross-run learning. Read by the planner's retrieval step, written once per
-- run after the report gate approves.
CREATE TABLE IF NOT EXISTS attack_patterns (
    attack_pattern TEXT NOT NULL,
    target_type    TEXT NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 0,
    successes      INTEGER NOT NULL DEFAULT 0,
    success_rate   REAL NOT NULL DEFAULT 0.0,
    updated_at     TEXT,
    PRIMARY KEY (attack_pattern, target_type)
);
