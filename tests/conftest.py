import os

import psycopg
import pytest

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


@pytest.fixture(scope="session", autouse=True)
def _apply_schema():
    from app.config import settings

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS trips, vehicles, settings, app_login CASCADE")
        with open(SCHEMA_PATH) as f:
            conn.execute(f.read())
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    from app.config import settings

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        # TRUNCATE ... CASCADE on vehicles also wipes `settings`, since
        # settings.active_vehicle_id FKs to it -- re-insert the singleton
        # row explicitly afterward rather than relying on an UPDATE that
        # would silently affect 0 rows once it's gone.
        conn.execute("TRUNCATE trips, vehicles, settings, app_login CASCADE")
        conn.execute("INSERT INTO settings (id, owner_display_name) VALUES (1, '')")


@pytest.fixture
def test_vehicle():
    from app import vehicles

    return vehicles.create_vehicle(
        registration="TEST 123 GP",
        make="Toyota",
        model="Corolla",
        engine_capacity_cc=1600,
        tax_year_opening_odometer=10000.0,
        tax_year_start_date="2026-03-01",
    )
