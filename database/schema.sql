PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analysis (
    analysis_id TEXT PRIMARY KEY,
    demo_sha256 TEXT NOT NULL UNIQUE,
    demo_path TEXT NOT NULL,
    demo_size_bytes INTEGER NOT NULL,
    map_name TEXT,
    demo_version TEXT,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('created', 'parsed', 'analyzed', 'failed')
    ),
    error_message TEXT,
    total_rounds INTEGER,
    tick_rate REAL,
    playback_ticks INTEGER,
    has_match_end INTEGER NOT NULL DEFAULT 0
        CHECK (has_match_end IN (0, 1)),
    regulation_complete INTEGER NOT NULL DEFAULT 0
        CHECK (regulation_complete IN (0, 1)),
    imported_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS player (
    analysis_id TEXT NOT NULL,
    steamid TEXT NOT NULL,
    current_name TEXT NOT NULL,
    starting_side TEXT,
    is_recorder INTEGER NOT NULL DEFAULT 0 CHECK (is_recorder IN (0, 1)),
    PRIMARY KEY (analysis_id, steamid),
    FOREIGN KEY (analysis_id) REFERENCES analysis(analysis_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS round (
    analysis_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    start_tick INTEGER NOT NULL,
    freeze_end_tick INTEGER,
    end_tick INTEGER NOT NULL,
    winner_side TEXT NOT NULL,
    reason_code INTEGER,
    reason_name TEXT,
    is_knife_round INTEGER NOT NULL DEFAULT 0
        CHECK (is_knife_round IN (0, 1)),
    PRIMARY KEY (analysis_id, round_num),
    FOREIGN KEY (analysis_id) REFERENCES analysis(analysis_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tick_sample (
    analysis_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    steamid TEXT NOT NULL,
    side TEXT,
    x REAL,
    y REAL,
    z REAL,
    pitch REAL,
    yaw REAL,
    health INTEGER,
    armor INTEGER,
    money INTEGER,
    equipment_value INTEGER,
    active_weapon TEXT,
    place_name TEXT,
    has_bomb INTEGER,
    is_crouched INTEGER,
    is_walking INTEGER,
    is_jumping INTEGER,
    is_scoped INTEGER,
    is_blinded INTEGER,
    PRIMARY KEY (analysis_id, round_num, tick, steamid),
    FOREIGN KEY (analysis_id, round_num)
        REFERENCES round(analysis_id, round_num) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id, steamid)
        REFERENCES player(analysis_id, steamid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS round_team_economy (
    analysis_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    side TEXT NOT NULL,
    equipment_value INTEGER NOT NULL,
    buy_type TEXT,
    n_players INTEGER NOT NULL,
    PRIMARY KEY (analysis_id, round_num, side),
    FOREIGN KEY (analysis_id, round_num)
        REFERENCES round(analysis_id, round_num) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS game_event (
    evidence_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_steamid TEXT,
    target_steamid TEXT,
    assister_steamid TEXT,
    weapon TEXT,
    x REAL,
    y REAL,
    z REAL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (analysis_id, round_num)
        REFERENCES round(analysis_id, round_num) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS round_player_metric (
    analysis_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    steamid TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    value_number REAL,
    value_text TEXT,
    unit TEXT,
    sample_size INTEGER NOT NULL DEFAULT 1,
    confidence REAL,
    rule_version TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (
        analysis_id, round_num, steamid, metric_key, rule_version
    ),
    FOREIGN KEY (analysis_id, round_num)
        REFERENCES round(analysis_id, round_num) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id, steamid)
        REFERENCES player(analysis_id, steamid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_player_metric (
    analysis_id TEXT NOT NULL,
    steamid TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    value_number REAL,
    value_text TEXT,
    unit TEXT,
    sample_size INTEGER NOT NULL DEFAULT 1,
    confidence REAL,
    rule_version TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (analysis_id, steamid, metric_key, rule_version),
    FOREIGN KEY (analysis_id, steamid)
        REFERENCES player(analysis_id, steamid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS key_round (
    analysis_id TEXT NOT NULL,
    steamid TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN (
            'excellent', 'problem', 'high_impact', 'representative'
        )
    ),
    rank_score REAL NOT NULL,
    rationale TEXT NOT NULL,
    score_components_json TEXT NOT NULL DEFAULT '{}',
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    rule_version TEXT NOT NULL,
    PRIMARY KEY (analysis_id, steamid, round_num, category, rule_version),
    FOREIGN KEY (analysis_id, round_num)
        REFERENCES round(analysis_id, round_num) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id, steamid)
        REFERENCES player(analysis_id, steamid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report (
    report_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    steamid TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_model TEXT,
    prompt_version TEXT,
    fact_bundle_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'generated', 'validation_failed', 'failed')
    ),
    report_markdown TEXT,
    report_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (analysis_id, steamid)
        REFERENCES player(analysis_id, steamid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_game_event_round_tick
    ON game_event(analysis_id, round_num, tick);

CREATE INDEX IF NOT EXISTS idx_game_event_actor
    ON game_event(analysis_id, actor_steamid, round_num);

CREATE INDEX IF NOT EXISTS idx_tick_sample_player_tick
    ON tick_sample(analysis_id, steamid, tick);

CREATE INDEX IF NOT EXISTS idx_round_metric_player
    ON round_player_metric(analysis_id, steamid, metric_key);

CREATE INDEX IF NOT EXISTS idx_match_metric_player
    ON match_player_metric(analysis_id, steamid);

CREATE INDEX IF NOT EXISTS idx_key_round_player
    ON key_round(analysis_id, steamid, category, rank_score DESC);

CREATE INDEX IF NOT EXISTS idx_report_player
    ON report(analysis_id, steamid, created_at);

