#!/usr/bin/env python3
"""Sets or resets the single app login password.

Usage (run inside the running web container, or locally against
DATABASE_URL from the repo root):
    python -m scripts.set_password
"""
import getpass
import sys

from app.database import execute
from app.security import hash_password


def main():
    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match.")
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    password_hash = hash_password(password)
    execute(
        """
        INSERT INTO app_login (id, password_hash, updated_at)
        VALUES (1, %s, now())
        ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, updated_at = now()
        """,
        (password_hash,),
    )
    print("Password set.")


if __name__ == "__main__":
    main()
