-- RESOURCES tool database (SQLite)
-- reference = general game data, replaced on refresh
-- state     = player's current state, replaced on refresh
-- history   = time series, appended

PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------- reference
CREATE TABLE IF NOT EXISTS items (            -- q=1001
    item_id   INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    icon_url  TEXT
);

CREATE TABLE IF NOT EXISTS recipes (          -- q=1002, one row per product
    item_id           INTEGER PRIMARY KEY,
    factory_id        INTEGER NOT NULL,
    factory_name      TEXT,
    base_out_h        REAL,                   -- output/h = base_out_h * factory level
    out_per_cycle     REAL,
    credits_per_cycle REAL
);
CREATE TABLE IF NOT EXISTS recipe_inputs (
    item_id        INTEGER,
    input_id       INTEGER,
    qty_per_cycle  REAL,
    PRIMARY KEY (item_id, input_id)
);

CREATE TABLE IF NOT EXISTS recycling (        -- q=1003
    item_id    INTEGER PRIMARY KEY,
    name       TEXT,
    input_qty  REAL
);
CREATE TABLE IF NOT EXISTS recycling_outputs (
    item_id  INTEGER,
    out_id   INTEGER,
    qty      REAL,
    PRIMARY KEY (item_id, out_id)
);

CREATE TABLE IF NOT EXISTS factory_upgrades ( -- q=1004
    factory_id  INTEGER PRIMARY KEY,
    name        TEXT,
    product_id  INTEGER,
    base_cost   REAL,
    min_lvl     INTEGER
);
CREATE TABLE IF NOT EXISTS factory_upgrade_items (
    factory_id INTEGER, item_id INTEGER, qty REAL,
    PRIMARY KEY (factory_id, item_id)
);

CREATE TABLE IF NOT EXISTS specb_upgrades (   -- q=1005, cost = base * target_lvl^2
    specb_id   INTEGER PRIMARY KEY,
    name       TEXT,
    base_cost  REAL,
    min_lvl    INTEGER
);
CREATE TABLE IF NOT EXISTS specb_upgrade_items (
    specb_id INTEGER, item_id INTEGER, qty REAL,
    PRIMARY KEY (specb_id, item_id)
);

CREATE TABLE IF NOT EXISTS troops (           -- q=1007
    item_id        INTEGER PRIMARY KEY,
    name           TEXT,
    cost_per_unit  REAL
);
CREATE TABLE IF NOT EXISTS troop_items (
    troop_id INTEGER, item_id INTEGER, qty REAL,
    PRIMARY KEY (troop_id, item_id)
);

-- ---------------------------------------------------------------- state
CREATE TABLE IF NOT EXISTS factories (        -- q=1
    factory_id  INTEGER PRIMARY KEY,
    name        TEXT,
    lvl         INTEGER,
    strike      TEXT,
    updated_ts  INTEGER
);

CREATE TABLE IF NOT EXISTS specbuildings (    -- q=3
    specb_id    INTEGER PRIMARY KEY,
    name        TEXT,
    lvl         INTEGER,
    updated_ts  INTEGER
);

CREATE TABLE IF NOT EXISTS hq (               -- q=4
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    lvl         INTEGER,
    lat         REAL,
    lon         REAL,
    target      REAL,
    raw_json    TEXT,
    updated_ts  INTEGER
);

CREATE TABLE IF NOT EXISTS mines (            -- q=5
    mine_key         TEXT PRIMARY KEY,        -- "lat,lon": the API has no unique mine ID
    type_id          INTEGER,                 -- API "mineID" = mine type (4 = Clay Pit)
    name             TEXT,
    resource_id      INTEGER,
    resource_name    TEXT,
    lat              REAL,
    lon              REAL,
    builddate        INTEGER,
    hq_boost         REAL,
    fullrate         REAL,
    rawrate          REAL,
    techfactor       REAL,
    quality          REAL,
    quality_tu       REAL,
    condition        REAL,
    lastmaintenance  INTEGER,
    lastenemyaction  INTEGER,
    def1 INTEGER, def2 INTEGER, def3 INTEGER,
    attackpenalty    REAL,
    attackcount      INTEGER,
    attacklost       INTEGER,
    active           INTEGER DEFAULT 1,      -- 0 = not in the last answer (demolished)
    updated_ts       INTEGER
);

CREATE TABLE IF NOT EXISTS achievements (     -- q=12
    achievement_id  INTEGER PRIMARY KEY,
    title           TEXT,
    descr           TEXT,
    reward_item_id  INTEGER,
    reward_amt      REAL,
    req_amt         REAL,
    completed       INTEGER,
    reward_earned   INTEGER,
    completed_ts    INTEGER,
    updated_ts      INTEGER
);

-- ---------------------------------------------------------------- history
CREATE TABLE IF NOT EXISTS warehouse_hist (   -- q=2
    ts INTEGER, item_id INTEGER, level INTEGER, amount REAL,
    PRIMARY KEY (ts, item_id)
);
CREATE TABLE IF NOT EXISTS market_hist (      -- q=1006
    ts INTEGER, item_id INTEGER, ki_price REAL, price REAL,
    PRIMARY KEY (ts, item_id)
);
CREATE TABLE IF NOT EXISTS player_hist (      -- q=7
    ts INTEGER PRIMARY KEY, username TEXT, lvl INTEGER, points INTEGER, rank INTEGER
);
CREATE TABLE IF NOT EXISTS missions_hist (    -- q=10
    ts INTEGER, quest_id INTEGER, title TEXT, descr TEXT, status TEXT,
    progress REAL, goal REAL, dur_h REAL, reward_item INTEGER, reward_amt REAL,
    penalty REAL, cooldown REAL, starttime REAL, endtime REAL, interval_days REAL,
    PRIMARY KEY (ts, quest_id)
);
CREATE TABLE IF NOT EXISTS mines_hist (       -- q=5, compact per-mine history
    ts INTEGER, mine_key TEXT, condition REAL, lastmaintenance INTEGER,
    fullrate REAL, attackcount INTEGER,
    PRIMARY KEY (ts, mine_key)
);
CREATE TABLE IF NOT EXISTS factories_hist (   -- q=1
    ts INTEGER, factory_id INTEGER, lvl INTEGER,
    PRIMARY KEY (ts, factory_id)
);
CREATE TABLE IF NOT EXISTS specb_hist (       -- q=3
    ts INTEGER, specb_id INTEGER, lvl INTEGER,
    PRIMARY KEY (ts, specb_id)
);
CREATE TABLE IF NOT EXISTS money_daily (      -- q=8, revenues/expenditures per category per day
    date INTEGER, item_id INTEGER, name TEXT, revenues REAL, expenditures REAL,
    PRIMARY KEY (date, item_id)
);
CREATE TABLE IF NOT EXISTS trades (           -- q=6
    ts INTEGER, event TEXT, username TEXT, ulvl INTEGER, item_id INTEGER,
    amount REAL, ppstk REAL, transcost REAL,
    UNIQUE (ts, event, username, item_id, amount, ppstk)
);

-- ---------------------------------------------------------------- system
CREATE TABLE IF NOT EXISTS fetch_log (
    ts INTEGER, q INTEGER, ok INTEGER, rows INTEGER, credits INTEGER, note TEXT
);
CREATE INDEX IF NOT EXISTS ix_fetch ON fetch_log (q, ts);

CREATE TABLE IF NOT EXISTS raw (              -- every answer, zlib-compressed JSON
    ts INTEGER, q INTEGER, data BLOB,
    PRIMARY KEY (ts, q)
);

CREATE TABLE IF NOT EXISTS meta   (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS alerts (key TEXT PRIMARY KEY, ts INTEGER);

CREATE INDEX IF NOT EXISTS ix_wh_item  ON warehouse_hist (item_id, ts);
CREATE INDEX IF NOT EXISTS ix_mk_item  ON market_hist (item_id, ts);
CREATE INDEX IF NOT EXISTS ix_ms_quest ON missions_hist (quest_id, ts);
CREATE INDEX IF NOT EXISTS ix_tr_item  ON trades (item_id, ts);
