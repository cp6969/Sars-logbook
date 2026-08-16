from app.database import execute, fetchall, fetchone


def get_active_vehicle():
    return fetchone(
        """
        SELECT v.* FROM vehicles v
        JOIN settings s ON s.active_vehicle_id = v.id
        WHERE v.is_active = true
        """
    )


def list_vehicles():
    return fetchall("SELECT * FROM vehicles WHERE is_active = true ORDER BY created_at")


def create_vehicle(registration, make, model, engine_capacity_cc, tax_year_opening_odometer, tax_year_start_date):
    rows = execute(
        """
        INSERT INTO vehicles (registration, make, model, engine_capacity_cc,
                               tax_year_opening_odometer, tax_year_start_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (registration, make, model, engine_capacity_cc, tax_year_opening_odometer, tax_year_start_date),
    )
    vehicle = rows[0]
    execute(
        "UPDATE settings SET active_vehicle_id = %s, updated_at = now() WHERE id = 1",
        (vehicle["id"],),
    )
    return vehicle


def update_vehicle(vehicle_id, **fields):
    """`fields` must only ever be known, hardcoded column names passed as
    kwargs by callers in this codebase -- never build this dict from raw
    user-supplied keys, since the SET clause is built via string
    interpolation of the keys themselves (values are still parameterized)."""
    if not fields:
        return
    set_clause = ", ".join(f"{key} = %s" for key in fields)
    params = list(fields.values()) + [vehicle_id]
    execute(f"UPDATE vehicles SET {set_clause}, updated_at = now() WHERE id = %s", params)


def get_settings():
    return fetchone("SELECT * FROM settings WHERE id = 1")


def update_owner_name(name):
    execute("UPDATE settings SET owner_display_name = %s, updated_at = now() WHERE id = 1", (name,))
