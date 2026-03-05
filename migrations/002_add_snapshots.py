"""
Migration 002: Add portfolio snapshots for equity curve tracking.

This migration ensures the portfolio_snapshots table exists and adds
an index for efficient date-range queries used by equity curves.

Idempotent -- safe to run multiple times.
"""

import sqlite3
import os


def migrate(db_path="data/forward_testing.db"):
    """Run migration 002 - add snapshots table and indices."""
    if not os.path.exists(db_path):
        print("No database found, skipping migration.")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Ensure portfolio_snapshots table exists (in case v3 migration wasn't run)
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            snapshot_date DATE NOT NULL,
            cash REAL NOT NULL,
            invested_value REAL NOT NULL,
            total_value REAL NOT NULL,
            return_pct REAL NOT NULL,
            active_positions INTEGER NOT NULL DEFAULT 0,
            closed_positions INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, snapshot_date)
        )
    """)

    # 2. Create index for efficient equity curve queries (by profile and date)
    try:
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_profile_date 
            ON portfolio_snapshots(profile_id, snapshot_date DESC)
        """)
    except sqlite3.OperationalError:
        pass  # Index already exists

    # 3. Create index for dashboard date-range queries
    try:
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_date 
            ON portfolio_snapshots(snapshot_date)
        """)
    except sqlite3.OperationalError:
        pass  # Index already exists

    conn.commit()
    conn.close()
    print("Migration 002 (portfolio snapshots) complete.")


if __name__ == '__main__':
    migrate()
