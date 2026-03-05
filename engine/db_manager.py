"""
Database manager: connection, schema, migrations, and daily snapshots.
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

from engine.models import ProfileConfig


class DbManager:
    def __init__(self, db_path="data/forward_testing.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)

    def connect(self):
        return sqlite3.connect(self.db_path)

    # ------------------------------------------
    # Schema initialization (v2 compatible)
    # ------------------------------------------

    def init_schema(self):
        """Create base tables if they don't exist (v2 schema)."""
        conn = self.connect()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                owner_name TEXT,
                title TEXT,
                trade_date DATE NOT NULL,
                detection_date DATE NOT NULL,
                score INTEGER,
                value REAL,
                cluster_size INTEGER,
                entry_price REAL,
                current_price REAL,
                last_updated DATE,
                status TEXT DEFAULT 'ACTIVE',
                exit_price REAL,
                exit_date DATE,
                exit_reason TEXT,
                return_pct REAL,
                days_holding INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy, ticker, trade_date, owner_name)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                strategy TEXT PRIMARY KEY,
                cash REAL NOT NULL,
                invested_value REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL,
                return_pct REAL DEFAULT 0,
                trades_count INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                sharpe_ratio REAL,
                max_drawdown REAL,
                profit_factor REAL,
                sortino_ratio REAL,
                updated_at DATE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                trade_id INTEGER,
                action TEXT NOT NULL,
                ticker TEXT NOT NULL,
                shares INTEGER,
                price REAL,
                commission REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    # ------------------------------------------
    # v3 Migration (additive, idempotent)
    # ------------------------------------------

    def migrate_to_v3(self):
        """Add v3 tables and columns. Safe to run multiple times."""
        conn = self.connect()
        c = conn.cursor()

        # New table: profiles metadata
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

        # New table: daily portfolio snapshots (for charts)
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

        # New table: benchmark prices
        c.execute("""
            CREATE TABLE IF NOT EXISTS benchmark_prices (
                ticker TEXT NOT NULL,
                price_date DATE NOT NULL,
                close_price REAL NOT NULL,
                PRIMARY KEY (ticker, price_date)
            )
        """)

        # New table: signals log
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

        # New table: optimizer log
        c.execute("""
            CREATE TABLE IF NOT EXISTS optimizer_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                action TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                base_profile_id TEXT,
                reason TEXT NOT NULL,
                params_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add columns to existing trades table
        for alter in [
            "ALTER TABLE trades ADD COLUMN asset_type TEXT DEFAULT 'stock'",
            "ALTER TABLE trades ADD COLUMN profile_id TEXT",
        ]:
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Add columns to profiles table for optimizer
        for alter in [
            "ALTER TABLE profiles ADD COLUMN spawned_from TEXT",
            "ALTER TABLE profiles ADD COLUMN spawned_date TEXT",
            "ALTER TABLE profiles ADD COLUMN retired_date TEXT",
        ]:
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Add advanced metrics columns to portfolios table
        for alter in [
            "ALTER TABLE portfolios ADD COLUMN sharpe_ratio REAL",
            "ALTER TABLE portfolios ADD COLUMN max_drawdown REAL",
            "ALTER TABLE portfolios ADD COLUMN profit_factor REAL",
            "ALTER TABLE portfolios ADD COLUMN sortino_ratio REAL",
        ]:
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Backfill profile_id from strategy
        c.execute("UPDATE trades SET profile_id = strategy WHERE profile_id IS NULL")

        conn.commit()
        conn.close()

    # ------------------------------------------
    # Profile management
    # ------------------------------------------

    def register_profile(self, profile: ProfileConfig):
        """Register or update a profile in the DB."""
        conn = self.connect()
        c = conn.cursor()

        import json
        extra = json.dumps(profile.extra_params) if profile.extra_params else None

        c.execute("""
            INSERT OR REPLACE INTO profiles
            (profile_id, display_name, description, asset_type, data_source,
             initial_capital, position_size_pct, max_positions,
             stop_loss_pct, take_profit_pct, max_holding_days,
             commission, schedule, extra_params, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            profile.profile_id, profile.display_name, profile.description,
            profile.asset_type.value, profile.data_source,
            profile.initial_capital, profile.position_size_pct, profile.max_positions,
            profile.stop_loss_pct, profile.take_profit_pct, profile.max_holding_days,
            profile.commission, profile.schedule, extra
        ))

        # Ensure portfolio row exists
        c.execute("""
            INSERT OR IGNORE INTO portfolios (strategy, cash, invested_value, total, updated_at)
            VALUES (?, ?, 0, ?, ?)
        """, (profile.profile_id, profile.initial_capital, profile.initial_capital,
              datetime.now().strftime('%Y-%m-%d')))

        conn.commit()
        conn.close()

    # ------------------------------------------
    # Portfolio queries
    # ------------------------------------------

    def get_portfolio_state(self, profile_id):
        """Get current portfolio state for a profile."""
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT cash, invested_value, total, return_pct, trades_count, wins, losses,
                   sharpe_ratio, max_drawdown, profit_factor, sortino_ratio
            FROM portfolios WHERE strategy = ?
        """, (profile_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'cash': row[0], 'invested_value': row[1], 'total': row[2],
            'return_pct': row[3] or 0, 'trades_count': row[4] or 0,
            'wins': row[5] or 0, 'losses': row[6] or 0,
            'sharpe_ratio': row[7], 'max_drawdown': row[8],
            'profit_factor': row[9], 'sortino_ratio': row[10],
        }

    def get_active_positions(self, profile_id):
        """Get all active positions for a profile."""
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.ticker, t.entry_price, t.current_price, t.return_pct,
                   t.days_holding, t.company_name, t.owner_name, t.title,
                   e.shares, t.trade_date, t.score
            FROM trades t
            JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
            WHERE t.strategy = ? AND t.status = 'ACTIVE'
        """, (profile_id,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0], 'ticker': r[1], 'entry_price': r[2], 'current_price': r[3],
            'return_pct': r[4] or 0, 'days_holding': r[5] or 0,
            'company_name': r[6], 'owner_name': r[7], 'title': r[8],
            'shares': r[9], 'trade_date': r[10], 'score': r[11],
        } for r in rows]

    def get_active_count(self, profile_id):
        """Get count of active positions for a profile."""
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades WHERE strategy = ? AND status = 'ACTIVE'", (profile_id,))
        count = c.fetchone()[0]
        conn.close()
        return count

    # ------------------------------------------
    # Daily snapshots
    # ------------------------------------------

    def save_daily_snapshot(self, profile_id):
        """Save a daily snapshot of portfolio state for charts."""
        conn = self.connect()
        c = conn.cursor()

        c.execute("""
            SELECT cash, invested_value, total, return_pct, trades_count, wins, losses
            FROM portfolios WHERE strategy = ?
        """, (profile_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return

        c.execute("SELECT COUNT(*) FROM trades WHERE strategy = ? AND status = 'ACTIVE'", (profile_id,))
        active = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM trades WHERE strategy = ? AND status = 'CLOSED'", (profile_id,))
        closed = c.fetchone()[0]

        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("""
            INSERT OR REPLACE INTO portfolio_snapshots
            (profile_id, snapshot_date, cash, invested_value, total_value, return_pct,
             active_positions, closed_positions, wins, losses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile_id, today, row[0], row[1], row[2], row[3] or 0,
              active, closed, row[5] or 0, row[6] or 0))

        conn.commit()
        conn.close()

    def get_snapshots(self, profile_id: str, days: int = 30) -> List[Dict]:
        """Retrieve historical portfolio snapshots for equity curve display.
        
        Args:
            profile_id: The profile identifier
            days: Number of days of history to retrieve (default 30)
            
        Returns:
            List of snapshot dictionaries with date, total, cash, invested, return_pct
        """
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT snapshot_date, total_value, cash, invested_value, return_pct,
                   active_positions, closed_positions, wins, losses
            FROM portfolio_snapshots
            WHERE profile_id = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
        """, (profile_id, days))
        rows = c.fetchall()
        conn.close()
        
        # Return in chronological order (oldest first)
        return [{
            'date': r[0],
            'total': r[1],
            'cash': r[2],
            'invested': r[3],
            'return_pct': r[4],
            'active_positions': r[5],
            'closed_positions': r[6],
            'wins': r[7],
            'losses': r[8],
        } for r in reversed(rows)]

    def save_benchmark_price(self, ticker, price):
        """Save a daily benchmark price."""
        conn = self.connect()
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("""
            INSERT OR REPLACE INTO benchmark_prices (ticker, price_date, close_price)
            VALUES (?, ?, ?)
        """, (ticker, today, price))
        conn.commit()
        conn.close()
