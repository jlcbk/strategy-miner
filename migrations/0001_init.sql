CREATE TABLE IF NOT EXISTS instruments (
    id BIGSERIAL PRIMARY KEY,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    price_precision INTEGER,
    qty_precision INTEGER,
    contract_size NUMERIC,
    expiry_ts TIMESTAMPTZ,
    option_type TEXT,
    strike NUMERIC,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exchange, market_type, symbol)
);

CREATE TABLE IF NOT EXISTS data_source_heartbeats (
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    last_exchange_ts TIMESTAMPTZ,
    last_local_ts TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (exchange, market_type, symbol, event_type, source)
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS replay_jobs (
    id UUID PRIMARY KEY,
    strategy TEXT NOT NULL,
    version TEXT NOT NULL,
    data_window_start TIMESTAMPTZ NOT NULL,
    data_window_end TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY,
    strategy TEXT NOT NULL,
    version TEXT NOT NULL,
    grade TEXT NOT NULL,
    net_edge_usd NUMERIC NOT NULL,
    capacity_usd NUMERIC NOT NULL,
    confidence NUMERIC NOT NULL,
    risk_score NUMERIC NOT NULL,
    data_window_start TIMESTAMPTZ NOT NULL,
    data_window_end TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS opportunities_strategy_created_at_idx
    ON opportunities (strategy, created_at DESC);

CREATE TABLE IF NOT EXISTS research_reports (
    id UUID PRIMARY KEY,
    source_url TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    formulas JSONB NOT NULL DEFAULT '[]'::jsonb,
    cost_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    failure_modes JSONB NOT NULL DEFAULT '[]'::jsonb,
    candidate_artifacts JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
