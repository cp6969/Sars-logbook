-- SARS Vehicle Logbook -- schema.sql
-- Postgres 16 (postgres:16-alpine, same base image as the sibling PO Bridge app)
--
-- Greenfield repo, one canonical schema, no migration chain yet. The
-- moment there's a second real schema change after the first real deploy,
-- switch to numbered migration_NNN_*.sql files (+ a synced copy here),
-- matching the sibling PO Bridge app's own convention -- don't let more
-- than one undocumented change happen before adopting that discipline.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Single-row login -- this app only ever has one user, so there's no
-- users table, just one password hash to check against.
CREATE TABLE app_login (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    password_hash   TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Built as a proper table from day one even though only one vehicle is
-- used today. SARS explicitly requires a SEPARATE logbook per vehicle if
-- more than one is ever used for business travel in a tax year -- cheap,
-- sensible future-proofing given that explicit requirement.
CREATE TABLE vehicles (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registration                TEXT NOT NULL,
    make                        TEXT,
    model                       TEXT,
    engine_capacity_cc          INTEGER,
    tax_year_start_date         DATE NOT NULL DEFAULT '2026-03-01',
    tax_year_opening_odometer   NUMERIC(9,1) NOT NULL,
    is_active                   BOOLEAN NOT NULL DEFAULT true,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Singleton settings row.
CREATE TABLE settings (
    id                    INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    owner_display_name    TEXT NOT NULL DEFAULT '',
    active_vehicle_id     UUID REFERENCES vehicles(id),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO settings (id, owner_display_name) VALUES (1, '') ON CONFLICT (id) DO NOTHING;

CREATE TABLE trips (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id          UUID NOT NULL REFERENCES vehicles(id),
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    start_lat           DOUBLE PRECISION,
    start_lon           DOUBLE PRECISION,
    start_address       TEXT,
    end_lat             DOUBLE PRECISION,
    end_lon             DOUBLE PRECISION,
    end_address         TEXT,
    -- Array of {lat, lon, ts, accuracy} points captured during the trip.
    gps_track           JSONB NOT NULL DEFAULT '[]',
    -- GPS-derived, server-computed authoritative distance (never trust the
    -- client's own live running total -- it's a preview only).
    distance_km         NUMERIC(7,2),
    -- Optional REAL manual odometer readings for this specific trip --
    -- when present, these take precedence over the GPS-derived running
    -- ledger at export time (see app/export_sars.py's reconciliation
    -- logic).
    odometer_open       NUMERIC(9,1),
    odometer_close      NUMERIC(9,1),
    category            TEXT CHECK (category IN ('business', 'private')),
    -- Destination/client/site + reason -- SARS wants this specific enough
    -- to tie a trip back to a genuine business activity ("meeting" alone
    -- is not enough).
    purpose             TEXT,
    -- Idempotency key generated client-side (IndexedDB) so a retried sync
    -- (offline queue, or a killed/reopened tab mid-trip) can never create
    -- a duplicate trip server-side.
    client_trip_uuid    TEXT UNIQUE,
    -- 'open' = still in progress (ended_at IS NULL); 'pending_review' =
    -- ended but not yet classified; 'synced' = fully classified and done.
    sync_status         TEXT NOT NULL DEFAULT 'open'
                         CHECK (sync_status IN ('open', 'pending_review', 'synced')),
    -- Soft delete -- SARS wants 5-year logbook retention, so a manual
    -- delete hides the trip rather than actually destroying the record.
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trips_vehicle_started ON trips(vehicle_id, started_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_trips_open ON trips(vehicle_id) WHERE ended_at IS NULL AND deleted_at IS NULL;
CREATE INDEX idx_trips_pending_review ON trips(vehicle_id) WHERE sync_status = 'pending_review' AND deleted_at IS NULL;
-- Powers the "one-tap repeat trip" suggestion: most recent purpose/category
-- for a start/end point pair close to one already logged before.
CREATE INDEX idx_trips_addr_pair ON trips(vehicle_id, start_address, end_address)
    WHERE ended_at IS NOT NULL AND deleted_at IS NULL;
