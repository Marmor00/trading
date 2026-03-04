"""
Auto-Optimizer: autonomous profile optimization that runs every Friday.

Actions:
1. SPAWN: Create variations of top-performing profiles
2. RETIRE: Deactivate underperforming spawned profiles (never original 25)
3. LOG: Record every decision with clear, educational explanations

All decisions are logged to optimizer_log table and reported via Telegram.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from engine.db_manager import DbManager
from engine.models import ProfileConfig, AssetType
from engine.telegram_service import send_telegram


# Maximum total profiles (original + spawned)
MAX_TOTAL_PROFILES = 35

# Spawn criteria
MIN_RETURN_TO_SPAWN = 3.0       # Profile must have > 3% return
MIN_WIN_RATE_TO_SPAWN = 35.0    # And > 35% win rate
MIN_CLOSED_TRADES = 5           # With at least 5 closed trades

# Retire criteria (only for spawned profiles)
MAX_LOSS_TO_RETIRE = -8.0       # Retire if return < -8%
MIN_DAYS_BEFORE_RETIRE = 30     # Only after 30+ days of data


class AutoOptimizer:
    def __init__(self, db: DbManager):
        self.db = db

    def run(self) -> List[Dict]:
        """Run the weekly optimization. Returns list of actions taken."""
        print("\n" + "=" * 60)
        print("AUTO-OPTIMIZER (Weekly)")
        print("=" * 60)

        actions = []

        profiles = self._get_all_profile_stats()
        if not profiles:
            print("  No profiles found.")
            return actions

        total_active = sum(1 for p in profiles if p['is_active'])
        print(f"  {len(profiles)} profiles ({total_active} active)")

        # Step 1: Retire underperforming spawned profiles
        retire_actions = self._retire_losers(profiles)
        actions.extend(retire_actions)

        # Recalculate active count after retires
        total_active -= len(retire_actions)

        # Step 2: Spawn variations of winners
        spawn_actions = self._spawn_winners(profiles, total_active)
        actions.extend(spawn_actions)

        # Step 3: Log all decisions
        for action in actions:
            self._log_action(action)

        if not actions:
            self._log_action({
                'action': 'SKIP',
                'profile_id': 'all',
                'reason': f'No optimizations needed this week. {total_active} profiles active.',
            })
            print("  No optimizations needed this week.")

        print(f"  {len(actions)} actions taken.")
        return actions

    # ------------------------------------------
    # Retire underperforming spawned profiles
    # ------------------------------------------

    def _retire_losers(self, profiles: List[Dict]) -> List[Dict]:
        """Retire spawned profiles that are losing badly."""
        actions = []

        for p in profiles:
            # Never retire original profiles (spawned_from is NULL)
            if not p.get('spawned_from'):
                continue
            if not p['is_active']:
                continue

            days_active = p.get('days_since_spawn', 0)
            if days_active < MIN_DAYS_BEFORE_RETIRE:
                continue

            ret = p.get('return_pct', 0)
            if ret < MAX_LOSS_TO_RETIRE:
                # Retire this profile
                self._deactivate_profile(p['profile_id'])
                actions.append({
                    'action': 'RETIRE',
                    'profile_id': p['profile_id'],
                    'base_profile_id': p['spawned_from'],
                    'reason': (
                        f"Retired {p['display_name']} after {days_active} days. "
                        f"Return: {ret:+.1f}% (threshold: {MAX_LOSS_TO_RETIRE}%). "
                        f"This variation of {p['spawned_from']} did not perform well enough."
                    ),
                    'params': p.get('extra_params', {}),
                })

        return actions

    def _deactivate_profile(self, profile_id: str):
        """Mark profile as inactive and close its open trades."""
        conn = self.db.connect()
        c = conn.cursor()

        # Mark inactive
        c.execute("""
            UPDATE profiles SET is_active = 0, retired_date = ?
            WHERE profile_id = ?
        """, (datetime.now().strftime('%Y-%m-%d'), profile_id))

        # Close all active trades at current price
        c.execute("""
            SELECT id, ticker, entry_price, current_price
            FROM trades WHERE strategy = ? AND status = 'ACTIVE'
        """, (profile_id,))

        for trade_id, ticker, entry_price, current_price in c.fetchall():
            if current_price and entry_price:
                ret_pct = ((current_price - entry_price) / entry_price) * 100
                win = 1 if ret_pct > 0 else 0
            else:
                ret_pct = 0
                win = 0

            c.execute("""
                UPDATE trades SET status='CLOSED', exit_price=?, exit_date=?,
                exit_reason='OPTIMIZER_RETIRE', return_pct=?
                WHERE id=?
            """, (current_price, datetime.now().strftime('%Y-%m-%d'), ret_pct, trade_id))

            c.execute("""
                UPDATE portfolios SET wins = wins + ?, losses = losses + ?
                WHERE strategy = ?
            """, (win, 1 - win, profile_id))

        conn.commit()
        conn.close()
        print(f"    Retired: {profile_id}")

    # ------------------------------------------
    # Spawn variations of winners
    # ------------------------------------------

    def _spawn_winners(self, profiles: List[Dict], current_active: int) -> List[Dict]:
        """Create variations of top-performing profiles."""
        actions = []
        slots_available = MAX_TOTAL_PROFILES - current_active

        if slots_available <= 0:
            return actions

        # Find eligible profiles (active, good performance, enough data)
        candidates = []
        for p in profiles:
            if not p['is_active']:
                continue
            if p.get('return_pct', 0) <= MIN_RETURN_TO_SPAWN:
                continue
            if p.get('win_rate', 0) <= MIN_WIN_RATE_TO_SPAWN:
                continue
            if p.get('total_closed', 0) < MIN_CLOSED_TRADES:
                continue
            # Walk-forward guard: verify performance is consistent, not just recent luck
            if not self._passes_consistency_check(p['profile_id']):
                self._log_action({
                    'action': 'SKIP',
                    'profile_id': p['profile_id'],
                    'reason': (
                        f"Skipped {p['display_name']} for spawn: failed consistency check. "
                        f"First-half and second-half trade results are inconsistent, "
                        f"suggesting the performance may not be sustainable."
                    ),
                })
                continue
            candidates.append(p)

        if not candidates:
            return actions

        # Sort by return (best first)
        candidates.sort(key=lambda x: x.get('return_pct', 0), reverse=True)

        # Try to spawn 1-2 variations per candidate (up to available slots)
        existing_ids = {p['profile_id'] for p in profiles}

        for parent in candidates[:2]:  # Max 2 parent profiles per week
            if slots_available <= 0:
                break

            variations = self._generate_variations(parent, existing_ids)
            for var in variations[:2]:  # Max 2 variations per parent
                if slots_available <= 0:
                    break

                success = self._create_spawned_profile(var, parent['profile_id'])
                if success:
                    existing_ids.add(var['profile_id'])
                    slots_available -= 1
                    actions.append({
                        'action': 'SPAWN',
                        'profile_id': var['profile_id'],
                        'base_profile_id': parent['profile_id'],
                        'reason': (
                            f"Created {var['display_name']} based on {parent['display_name']} "
                            f"(return: {parent['return_pct']:+.1f}%, WR: {parent['win_rate']:.0f}%). "
                            f"Change: {var['change_description']}"
                        ),
                        'params': var.get('extra_params', {}),
                    })

        return actions

    def _generate_variations(self, parent: Dict, existing_ids: set) -> List[Dict]:
        """Generate parameter variations of a successful profile."""
        variations = []
        extra = parent.get('extra_params', {})
        pid = parent['profile_id']

        # Variation type depends on the strategy
        if 'score_threshold' in extra:
            # OpenInsider score profiles: vary threshold
            score = extra['score_threshold']
            for delta in [-3, +3]:
                new_score = score + delta
                new_id = f"score_{new_score}"
                if new_id not in existing_ids and 40 <= new_score <= 95:
                    new_extra = dict(extra)
                    new_extra['score_threshold'] = new_score
                    variations.append({
                        'profile_id': new_id,
                        'display_name': f'Score >={new_score} (auto)',
                        'description': f'Auto-spawned from {pid}: testing score threshold {new_score}',
                        'asset_type': parent['asset_type'],
                        'data_source': parent['data_source'],
                        'position_size_pct': parent.get('position_size_pct', 10),
                        'max_positions': parent.get('max_positions', 10),
                        'stop_loss_pct': parent.get('stop_loss_pct', -10),
                        'take_profit_pct': parent.get('take_profit_pct', 20),
                        'max_holding_days': parent.get('max_holding_days', 60),
                        'commission': parent.get('commission', 6.95),
                        'schedule': parent.get('schedule', 'weekdays'),
                        'extra_params': new_extra,
                        'change_description': f'score threshold {score} -> {new_score}',
                    })

        elif 'min_value' in extra and parent.get('data_source') == 'congress':
            # Congress profiles: vary min value
            min_val = extra['min_value']
            for factor in [0.7, 1.5]:
                new_val = int(min_val * factor)
                new_id = f"congress_{new_val // 1000}k_auto"
                if new_id not in existing_ids:
                    new_extra = dict(extra)
                    new_extra['min_value'] = new_val
                    variations.append({
                        'profile_id': new_id,
                        'display_name': f'Congress >${new_val // 1000}k (auto)',
                        'description': f'Auto-spawned from {pid}: testing min value ${new_val:,}',
                        'asset_type': parent['asset_type'],
                        'data_source': parent['data_source'],
                        'position_size_pct': parent.get('position_size_pct', 10),
                        'max_positions': parent.get('max_positions', 10),
                        'stop_loss_pct': parent.get('stop_loss_pct', -10),
                        'take_profit_pct': parent.get('take_profit_pct', 20),
                        'max_holding_days': parent.get('max_holding_days', 60),
                        'commission': parent.get('commission', 6.95),
                        'schedule': parent.get('schedule', 'weekdays'),
                        'extra_params': new_extra,
                        'change_description': f'min value ${min_val:,} -> ${new_val:,}',
                    })

        elif parent.get('data_source') == 'market_scanner':
            # Scanner profiles: vary indicator thresholds and risk params
            indicator = extra.get('indicator', '')

            if indicator == 'rsi' and 'buy_threshold' in extra:
                thresh = extra['buy_threshold']
                for delta in [-5, +5]:
                    new_thresh = thresh + delta
                    if 15 <= new_thresh <= 45:
                        new_id = f"{pid}_rsi{new_thresh}"
                        if new_id not in existing_ids:
                            new_extra = dict(extra)
                            new_extra['buy_threshold'] = new_thresh
                            new_extra['id'] = new_id
                            variations.append({
                                'profile_id': new_id,
                                'display_name': f"{extra.get('display_name', pid)} RSI<{new_thresh} (auto)",
                                'description': f'Auto-spawned from {pid}: testing RSI threshold {new_thresh}',
                                'asset_type': parent['asset_type'],
                                'data_source': 'market_scanner',
                                'position_size_pct': parent.get('position_size_pct', 10),
                                'max_positions': parent.get('max_positions', 8),
                                'stop_loss_pct': parent.get('stop_loss_pct', -8),
                                'take_profit_pct': parent.get('take_profit_pct', 15),
                                'max_holding_days': parent.get('max_holding_days', 30),
                                'commission': 0.0,
                                'schedule': 'weekdays',
                                'extra_params': new_extra,
                                'change_description': f'RSI buy threshold {thresh} -> {new_thresh}',
                            })

            # For any scanner profile: try tighter stop loss
            sl = parent.get('stop_loss_pct', -10)
            new_sl = round(sl * 0.7, 1)  # Tighter stop
            new_id = f"{pid}_tightstop"
            if new_id not in existing_ids and new_sl > -20:
                new_extra = dict(extra)
                new_extra['id'] = new_id
                variations.append({
                    'profile_id': new_id,
                    'display_name': f"{extra.get('display_name', pid)} TightSL (auto)",
                    'description': f'Auto-spawned from {pid}: testing tighter stop loss {new_sl}%',
                    'asset_type': parent['asset_type'],
                    'data_source': 'market_scanner',
                    'position_size_pct': parent.get('position_size_pct', 10),
                    'max_positions': parent.get('max_positions', 8),
                    'stop_loss_pct': new_sl,
                    'take_profit_pct': parent.get('take_profit_pct', 15),
                    'max_holding_days': parent.get('max_holding_days', 30),
                    'commission': 0.0,
                    'schedule': 'weekdays',
                    'extra_params': new_extra,
                    'change_description': f'stop loss {sl}% -> {new_sl}%',
                })

        else:
            # Generic: vary stop loss and take profit
            sl = parent.get('stop_loss_pct', -10)
            tp = parent.get('take_profit_pct', 20)

            for sl_mult, tp_mult, label in [(0.7, 1.0, 'tightstop'), (1.0, 1.3, 'widetp')]:
                new_sl = round(sl * sl_mult, 1)
                new_tp = round(tp * tp_mult, 1)
                new_id = f"{pid}_{label}"
                if new_id not in existing_ids:
                    variations.append({
                        'profile_id': new_id,
                        'display_name': f"{parent['display_name']} {label} (auto)",
                        'description': f'Auto-spawned from {pid}: SL={new_sl}%, TP={new_tp}%',
                        'asset_type': parent['asset_type'],
                        'data_source': parent['data_source'],
                        'position_size_pct': parent.get('position_size_pct', 10),
                        'max_positions': parent.get('max_positions', 10),
                        'stop_loss_pct': new_sl,
                        'take_profit_pct': new_tp,
                        'max_holding_days': parent.get('max_holding_days', 60),
                        'commission': parent.get('commission', 6.95),
                        'schedule': parent.get('schedule', 'weekdays'),
                        'extra_params': extra,
                        'change_description': f'SL {sl}% -> {new_sl}%, TP {tp}% -> {new_tp}%',
                    })

        return variations

    def _create_spawned_profile(self, var: Dict, parent_id: str) -> bool:
        """Create a new profile in the DB from a variation config."""
        conn = self.db.connect()
        c = conn.cursor()
        try:
            extra_json = json.dumps(var.get('extra_params', {}))
            now = datetime.now().strftime('%Y-%m-%d')

            c.execute("""
                INSERT INTO profiles
                (profile_id, display_name, description, asset_type, data_source,
                 initial_capital, position_size_pct, max_positions,
                 stop_loss_pct, take_profit_pct, max_holding_days,
                 commission, schedule, extra_params, is_active,
                 spawned_from, spawned_date)
                VALUES (?, ?, ?, ?, ?, 10000.0, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                var['profile_id'], var['display_name'], var['description'],
                var['asset_type'], var['data_source'],
                var['position_size_pct'], var['max_positions'],
                var['stop_loss_pct'], var['take_profit_pct'], var['max_holding_days'],
                var.get('commission', 0.0), var['schedule'], extra_json,
                parent_id, now,
            ))

            # Create portfolio row
            c.execute("""
                INSERT OR IGNORE INTO portfolios (strategy, cash, invested_value, total, updated_at)
                VALUES (?, 10000.0, 0, 10000.0, ?)
            """, (var['profile_id'], now))

            conn.commit()
            print(f"    Spawned: {var['profile_id']} (from {parent_id})")
            return True

        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"    ! Error spawning {var['profile_id']}: {e}")
            return False
        finally:
            conn.close()

    # ------------------------------------------
    # Walk-forward consistency check
    # ------------------------------------------

    def _passes_consistency_check(self, profile_id: str) -> bool:
        """Check that a profile's performance is consistent across time.

        Splits closed trades into first and second half chronologically.
        Both halves must have a positive average return. This prevents
        spawning variations of profiles whose good numbers come from
        one lucky early trade followed by mediocre results.
        """
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            SELECT return_pct FROM trades
            WHERE strategy = ? AND status = 'CLOSED' AND return_pct IS NOT NULL
            ORDER BY exit_date ASC
        """, (profile_id,))
        returns = [r[0] for r in c.fetchall()]
        conn.close()

        if len(returns) < 4:
            # Not enough trades to split meaningfully — allow spawn
            return True

        mid = len(returns) // 2
        first_half_avg = sum(returns[:mid]) / mid
        second_half_avg = sum(returns[mid:]) / (len(returns) - mid)

        # Both halves must be net positive
        return first_half_avg > 0 and second_half_avg > 0

    # ------------------------------------------
    # Data queries
    # ------------------------------------------

    def _get_all_profile_stats(self) -> List[Dict]:
        """Get performance stats for all profiles."""
        conn = self.db.connect()
        c = conn.cursor()

        c.execute("""
            SELECT p.profile_id, p.display_name, p.asset_type, p.data_source,
                   p.position_size_pct, p.max_positions, p.stop_loss_pct,
                   p.take_profit_pct, p.max_holding_days, p.extra_params,
                   p.is_active, p.spawned_from, p.spawned_date, p.commission,
                   p.schedule,
                   pt.return_pct, pt.wins, pt.losses
            FROM profiles p
            LEFT JOIN portfolios pt ON pt.strategy = p.profile_id
        """)
        rows = c.fetchall()
        conn.close()

        profiles = []
        for row in rows:
            wins = row[16] or 0
            losses = row[17] or 0
            total_closed = wins + losses
            win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

            spawned_date = row[12]
            days_since_spawn = 0
            if spawned_date:
                try:
                    sd = datetime.strptime(spawned_date, '%Y-%m-%d')
                    days_since_spawn = (datetime.now() - sd).days
                except ValueError:
                    pass

            extra = {}
            if row[9]:
                try:
                    extra = json.loads(row[9])
                except (json.JSONDecodeError, TypeError):
                    pass

            profiles.append({
                'profile_id': row[0],
                'display_name': row[1],
                'asset_type': row[2],
                'data_source': row[3],
                'position_size_pct': row[4],
                'max_positions': row[5],
                'stop_loss_pct': row[6],
                'take_profit_pct': row[7],
                'max_holding_days': row[8],
                'extra_params': extra,
                'is_active': bool(row[10]),
                'spawned_from': row[11],
                'spawned_date': spawned_date,
                'commission': row[13],
                'schedule': row[14],
                'return_pct': row[15] or 0,
                'wins': wins,
                'losses': losses,
                'total_closed': total_closed,
                'win_rate': win_rate,
                'days_since_spawn': days_since_spawn,
            })

        return profiles

    # ------------------------------------------
    # Logging
    # ------------------------------------------

    def _log_action(self, action: Dict):
        """Log optimizer action to DB."""
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            INSERT INTO optimizer_log
            (log_date, action, profile_id, base_profile_id, reason, params_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime('%Y-%m-%d'),
            action.get('action', 'UNKNOWN'),
            action.get('profile_id', ''),
            action.get('base_profile_id'),
            action.get('reason', ''),
            json.dumps(action.get('params', {})),
        ))
        conn.commit()
        conn.close()

    # ------------------------------------------
    # Weekly Telegram summary
    # ------------------------------------------

    def send_weekly_summary(self, actions: List[Dict]):
        """Send weekly optimizer summary via Telegram."""
        msg = "<b>WEEKLY OPTIMIZER REPORT</b>\n"
        msg += f"{datetime.now().strftime('%Y-%m-%d')}\n\n"

        spawns = [a for a in actions if a['action'] == 'SPAWN']
        retires = [a for a in actions if a['action'] == 'RETIRE']

        if spawns:
            msg += f"<b>NEW PROFILES ({len(spawns)}):</b>\n"
            for s in spawns:
                msg += f"  + {s['profile_id']}\n"
                msg += f"    {s['reason']}\n\n"

        if retires:
            msg += f"<b>RETIRED ({len(retires)}):</b>\n"
            for r in retires:
                msg += f"  - {r['profile_id']}\n"
                msg += f"    {r['reason']}\n\n"

        if not spawns and not retires:
            msg += "No changes this week. All profiles within expected ranges.\n"

        send_telegram(msg)
