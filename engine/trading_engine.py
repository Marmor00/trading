"""
Paper trading engine: executes buy/sell, updates positions, recalculates portfolios.
"""

import sqlite3
import time
import json
from datetime import datetime
from typing import List

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from engine.price_service import get_price
from engine.db_manager import DbManager
from engine.analytics import calculate_all_metrics


class TradingEngine:
    def __init__(self, db: DbManager):
        self.db = db

    # ------------------------------------------
    # Process signals from strategies
    # ------------------------------------------

    def process_signals(self, profile: ProfileConfig, signals: List[Signal]):
        """Process buy/sell signals for a profile. Returns count of executed trades."""
        if not signals:
            return 0

        portfolio = self.db.get_portfolio_state(profile.profile_id)
        if not portfolio:
            return 0

        cash = portfolio['cash']
        active_count = self.db.get_active_count(profile.profile_id)
        slots = profile.max_positions - active_count

        executed = 0
        for signal in signals:
            if signal.signal_type == SignalType.BUY:
                if slots <= 0:
                    self._log_signal(profile.profile_id, signal, False, "No available slots")
                    continue

                ok, cost = self._execute_buy(profile, signal, cash)
                if ok:
                    executed += 1
                    cash -= cost
                    slots -= 1
                    self._log_signal(profile.profile_id, signal, True)
                    time.sleep(2)
                else:
                    self._log_signal(profile.profile_id, signal, False, "Buy failed")

        return executed

    # ------------------------------------------
    # Buy execution
    # ------------------------------------------

    def _execute_buy(self, profile: ProfileConfig, signal: Signal, available_cash: float):
        """Execute a simulated buy. Returns (success, cost)."""
        ticker = signal.ticker
        price = get_price(ticker, profile.asset_type)
        if not price:
            return False, 0

        # Simulate slippage: pay slightly more on buys (realistic fill price)
        slippage = 0.002 if profile.asset_type == AssetType.CRYPTO else 0.001
        price = price * (1 + slippage)

        position_size = available_cash * (profile.position_size_pct / 100)
        commission = profile.commission

        if profile.asset_type == AssetType.CRYPTO:
            # Crypto: fractional shares allowed, percentage commission
            comm_pct = profile.extra_params.get('commission_pct', 0.1) / 100
            invest_amount = position_size - (position_size * comm_pct)
            shares_float = invest_amount / price
            if shares_float <= 0 or position_size > available_cash:
                return False, 0
            actual_commission = position_size * comm_pct
            cost = position_size
            shares = shares_float  # fractional for crypto
        else:
            # Stocks/ETFs: whole shares, flat commission
            shares = int((position_size - commission) / price)
            if shares < 1:
                return False, 0
            cost = (shares * price) + commission
            actual_commission = commission
            if cost > available_cash:
                return False, 0

        conn = self.db.connect()
        c = conn.cursor()
        try:
            # Extract metadata for DB columns
            meta = signal.metadata
            c.execute("""
                INSERT INTO trades
                (strategy, ticker, company_name, owner_name, title, trade_date, detection_date,
                 score, value, cluster_size, entry_price, current_price, last_updated,
                 status, days_holding, asset_type, profile_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0, ?, ?)
            """, (
                profile.profile_id, ticker,
                meta.get('company_name', ''), meta.get('owner_name', ''), meta.get('title', ''),
                meta.get('trade_date', datetime.now().strftime('%Y-%m-%d')),
                datetime.now().strftime('%Y-%m-%d'),
                meta.get('score', 0), meta.get('value', 0), meta.get('cluster_size', 0),
                price, price, datetime.now().strftime('%Y-%m-%d'),
                profile.asset_type.value, profile.profile_id
            ))
            trade_id = c.lastrowid

            c.execute("""
                INSERT INTO executions (strategy, trade_id, action, ticker, shares, price, commission)
                VALUES (?, ?, 'BUY', ?, ?, ?, ?)
            """, (profile.profile_id, trade_id, ticker, shares, price, actual_commission))

            c.execute("""
                UPDATE portfolios
                SET cash = cash - ?, trades_count = trades_count + 1, updated_at = ?
                WHERE strategy = ?
            """, (cost, datetime.now().strftime('%Y-%m-%d'), profile.profile_id))

            conn.commit()
            print(f"    + BUY {ticker} x{shares:.4g} @ ${price:.2f} [{profile.display_name}]")
            return True, cost

        except sqlite3.IntegrityError:
            return False, 0
        except Exception as e:
            print(f"    ! Error buying {ticker}: {e}")
            return False, 0
        finally:
            conn.close()

    # ------------------------------------------
    # Sell execution
    # ------------------------------------------

    def _execute_sell(self, profile: ProfileConfig, trade_id, ticker, entry_price, reason):
        """Execute a simulated sell."""
        conn = self.db.connect()
        c = conn.cursor()

        c.execute("SELECT shares FROM executions WHERE trade_id = ? AND action = 'BUY'", (trade_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False
        shares = row[0]

        price = get_price(ticker, profile.asset_type)
        if not price:
            conn.close()
            return False

        # Simulate slippage: receive slightly less on sells
        slippage = 0.002 if profile.asset_type == AssetType.CRYPTO else 0.001
        price = price * (1 - slippage)

        commission = profile.commission
        if profile.asset_type == AssetType.CRYPTO:
            comm_pct = profile.extra_params.get('commission_pct', 0.1) / 100
            revenue = (shares * price) * (1 - comm_pct)
            actual_commission = (shares * price) * comm_pct
        else:
            revenue = (shares * price) - commission
            actual_commission = commission

        ret_pct = ((price - entry_price) / entry_price) * 100
        win = 1 if ret_pct > 0 else 0

        c.execute("""
            UPDATE trades
            SET status='CLOSED', exit_price=?, exit_date=?, exit_reason=?, return_pct=?, current_price=?
            WHERE id=?
        """, (price, datetime.now().strftime('%Y-%m-%d'), reason, ret_pct, price, trade_id))

        c.execute("""
            INSERT INTO executions (strategy, trade_id, action, ticker, shares, price, commission)
            VALUES (?, ?, 'SELL', ?, ?, ?, ?)
        """, (profile.profile_id, trade_id, ticker, shares, price, actual_commission))

        c.execute("""
            UPDATE portfolios
            SET cash = cash + ?, wins = wins + ?, losses = losses + ?, updated_at = ?
            WHERE strategy = ?
        """, (revenue, win, 1 - win, datetime.now().strftime('%Y-%m-%d'), profile.profile_id))

        conn.commit()
        conn.close()

        tag = "WIN" if win else "LOSS"
        print(f"    - SELL {ticker} ({tag}) {ret_pct:+.1f}% | {reason} [{profile.display_name}]")
        return True

    # ------------------------------------------
    # Update all active positions
    # ------------------------------------------

    def update_all_positions(self, profiles: List[ProfileConfig]):
        """Update prices and check exit conditions for all active positions."""
        # Build a lookup of profile configs by id
        profile_map = {p.profile_id: p for p in profiles}

        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.strategy, t.ticker, t.entry_price, t.days_holding,
                   e.shares, t.asset_type
            FROM trades t
            JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
            WHERE t.status = 'ACTIVE'
        """)
        active = c.fetchall()
        conn.close()

        print(f"\nUpdating {len(active)} active trades...")

        for row in active:
            trade_id, strategy, ticker, entry_price, days_held, shares, asset_type_str = row
            days_held = (days_held or 0) + 1

            profile = profile_map.get(strategy)
            if not profile:
                continue

            price = get_price(ticker, profile.asset_type)
            if not price:
                continue

            ret_pct = ((price - entry_price) / entry_price) * 100

            # Check exit conditions
            exit_reason = None
            if ret_pct <= profile.stop_loss_pct:
                exit_reason = 'STOP_LOSS'
            elif ret_pct >= profile.take_profit_pct:
                exit_reason = 'TAKE_PROFIT'
            elif days_held >= profile.max_holding_days:
                exit_reason = 'TIME_EXIT'

            if exit_reason:
                self._execute_sell(profile, trade_id, ticker, entry_price, exit_reason)
            else:
                conn = self.db.connect()
                c = conn.cursor()
                c.execute("""
                    UPDATE trades
                    SET current_price=?, return_pct=?, days_holding=?, last_updated=?
                    WHERE id=?
                """, (price, ret_pct, days_held, datetime.now().strftime('%Y-%m-%d'), trade_id))
                conn.commit()
                conn.close()

            time.sleep(1)

    # ------------------------------------------
    # Recalculate portfolio values
    # ------------------------------------------

    def recalculate_portfolios(self, profiles: List[ProfileConfig]):
        """Recalculate real market value of each portfolio."""
        conn = self.db.connect()
        c = conn.cursor()

        for profile in profiles:
            pid = profile.profile_id

            c.execute("SELECT cash FROM portfolios WHERE strategy = ?", (pid,))
            row = c.fetchone()
            if not row:
                continue
            cash = row[0]

            c.execute("""
                SELECT COALESCE(SUM(e.shares * t.current_price), 0)
                FROM trades t
                JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
                WHERE t.strategy = ? AND t.status = 'ACTIVE'
            """, (pid,))
            market_value = c.fetchone()[0]

            total = cash + market_value
            ret_pct = ((total - profile.initial_capital) / profile.initial_capital) * 100

            # Get equity curve from portfolio snapshots
            c.execute("""
                SELECT total_value FROM portfolio_snapshots
                WHERE profile_id = ? ORDER BY snapshot_date
            """, (pid,))
            equity_curve = [r[0] for r in c.fetchall()]
            # Add current total to equity curve
            if total > 0:
                equity_curve.append(total)

            # Get closed trades for profit factor calculation
            c.execute("""
                SELECT return_pct FROM trades
                WHERE strategy = ? AND status = 'CLOSED'
            """, (pid,))
            closed_trades = [{'return_pct': r[0]} for r in c.fetchall()]

            # Calculate advanced metrics
            metrics = calculate_all_metrics(equity_curve, closed_trades)

            c.execute("""
                UPDATE portfolios
                SET invested_value = ?, total = ?, return_pct = ?,
                    sharpe_ratio = ?, max_drawdown = ?, profit_factor = ?, sortino_ratio = ?,
                    updated_at = ?
                WHERE strategy = ?
            """, (market_value, total, ret_pct,
                  metrics['sharpe_ratio'], metrics['max_drawdown'],
                  metrics['profit_factor'], metrics['sortino_ratio'],
                  datetime.now().strftime('%Y-%m-%d'), pid))

        conn.commit()
        conn.close()
        print("Portfolios recalculated.")

        # Save daily snapshots for equity curve tracking
        for profile in profiles:
            self.db.save_daily_snapshot(profile.profile_id)
        print("Portfolio snapshots saved.")

    # ------------------------------------------
    # Signal logging
    # ------------------------------------------

    def _log_signal(self, profile_id, signal: Signal, was_executed, skip_reason=None):
        """Log a signal for debugging."""
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            INSERT INTO signals_log
            (profile_id, ticker, signal_type, confidence, reason, metadata, was_executed, skip_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id, signal.ticker, signal.signal_type.value,
            signal.confidence, signal.reason,
            json.dumps(signal.metadata) if signal.metadata else None,
            1 if was_executed else 0, skip_reason
        ))
        conn.commit()
        conn.close()
