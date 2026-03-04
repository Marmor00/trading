"""
Migration from v2 to v3 schema.

This migration is idempotent -- safe to run multiple times.
It only adds new tables and columns, never removes anything.
"""

import sqlite3
import os


def migrate(db_path="data/forward_testing.db"):
    """Run the v2 -> v3 migration."""
    if not os.path.exists(db_path):
        print("No database found, skipping migration.")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Create new tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            profile_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            description TEXT,
            asset_type TEXT NOT NULL DEFAULT 'stock',
            data_source TEXT NOT NULL DEFAULT 'openinsider',
            initial_capital REAL NOT NULL DEFAULT 10000.0,
            position_size_pct REAL NOT NULL DEFAULT 10.0,
            max_positions INTEGER NOT NULL DEFAULT 10,
            stop_loss_pct REAL NOT NULL DEFAULT -10.0,
            take_profit_pct REAL NOT NULL DEFAULT 20.0,
            max_holding_days INTEGER NOT NULL DEFAULT 60,
            commission REAL NOT NULL DEFAULT 6.95,
            schedule TEXT NOT NULL DEFAULT 'weekdays',
            extra_params TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_prices (
            ticker TEXT NOT NULL,
            price_date DATE NOT NULL,
            close_price REAL NOT NULL,
            PRIMARY KEY (ticker, price_date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS signals_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            confidence REAL,
            reason TEXT,
            metadata TEXT,
            was_executed INTEGER DEFAULT 0,
            skip_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Add new columns to existing tables
    alter_statements = [
        "ALTER TABLE trades ADD COLUMN asset_type TEXT DEFAULT 'stock'",
        "ALTER TABLE trades ADD COLUMN profile_id TEXT",
    ]
    for stmt in alter_statements:
        try:
            c.execute(stmt)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # 3. Backfill profile_id from strategy column
    c.execute("UPDATE trades SET profile_id = strategy WHERE profile_id IS NULL")

    conn.commit()
    conn.close()
    print("Migration v2 -> v3 complete.")


if __name__ == '__main__':
    migrate()
