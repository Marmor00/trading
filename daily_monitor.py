"""
TRADING SIMULATION LABORATORY v3.0
===================================

Multi-strategy paper trading platform.

Runs via GitHub Actions. Each strategy is a pluggable module in strategies/.
Adding a new strategy = create a file, implement BaseStrategy, done.

Backward compatible with v2.1 data -- migration is additive and idempotent.

Usage:
    RUN_SCHEDULE=weekdays python daily_monitor.py   # Stocks/ETFs (Mon-Fri)
    RUN_SCHEDULE=daily python daily_monitor.py      # Crypto (every day)
    RUN_SCHEDULE=all python daily_monitor.py        # Everything
"""

import os
import sys
from datetime import datetime

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.db_manager import DbManager
from engine.trading_engine import TradingEngine
from engine.price_service import get_price, clear_price_cache
from engine.telegram_service import send_telegram, send_telegram_long
from engine.models import AssetType
from strategies import registry
from data_sources.openinsider import scrape_openinsider, enrich_trades
from data_sources.congress import fetch_congress_trades
from data_sources.coingecko import fetch_crypto_data
from data_sources.market_scanner import scan_market, clear_scan_cache


DB_PATH = "data/forward_testing.db"


# ============================================
# DATA SOURCE FETCHING
# ============================================

def fetch_data(source):
    """Fetch data for a given source. Returns raw data or empty list."""
    if source == 'openinsider':
        trades = scrape_openinsider()
        return enrich_trades(trades)
    elif source == 'congress':
        return fetch_congress_trades(days_back=30)
    elif source == 'coingecko':
        return fetch_crypto_data()
    elif source == 'market_scanner':
        return scan_market()
    elif source == 'none':
        return None
    else:
        print(f"Unknown data source: {source}")
        return []


# ============================================
# REPORTING
# ============================================

def generate_daily_report(db, profiles):
    """Generate and send the daily Telegram report."""
    data = []
    for strategy, profile in profiles:
        state = db.get_portfolio_state(profile.profile_id)
        if not state:
            continue

        active_count = db.get_active_count(profile.profile_id)

        conn = db.connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades WHERE strategy=? AND status='CLOSED'", (profile.profile_id,))
        closed = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM trades WHERE strategy=? AND DATE(detection_date)=DATE('now')", (profile.profile_id,))
        today_new = c.fetchone()[0]
        conn.close()

        wr = 0
        if (state['wins'] + state['losses']) > 0:
            wr = state['wins'] / (state['wins'] + state['losses']) * 100

        data.append({
            'name': profile.display_name,
            'total': state['total'],
            'ret': state['return_pct'],
            'active': active_count,
            'closed': closed,
            'wr': wr,
            'today': today_new,
            'asset': profile.asset_type.value,
        })

    data.sort(key=lambda x: x['ret'], reverse=True)

    today_str = datetime.now().strftime('%Y-%m-%d')
    msg = f"<b>SIMULATION LAB v3.0</b>\n{today_str}\n\n"

    for s in data:
        arrow = "+" if s['ret'] > 0 else ""
        new_tag = f" [+{s['today']} new]" if s['today'] > 0 else ""
        asset_tag = f" [{s['asset']}]" if s['asset'] != 'stock' else ""

        msg += f"<b>{s['name']}</b>{asset_tag}{new_tag}\n"
        msg += f"${s['total']:.0f} ({arrow}{s['ret']:.1f}%)\n"
        msg += f"Active: {s['active']} | Closed: {s['closed']}"
        if s['closed'] > 0:
            msg += f" | WR: {s['wr']:.0f}%"
        msg += "\n\n"

    if data:
        best = data[0]
        worst = data[-1]
        msg += f"<b>BEST:</b> {best['name']} ({best['ret']:+.1f}%)\n"
        msg += f"<b>WORST:</b> {worst['name']} ({worst['ret']:+.1f}%)"

    send_telegram(msg)


def generate_positions_detail(db, profiles):
    """Send detailed positions message."""
    messages = []
    current_msg = "<b>POSITIONS DETAIL</b>\n"

    for strategy, profile in profiles:
        positions = db.get_active_positions(profile.profile_id)
        if not positions:
            continue

        state = db.get_portfolio_state(profile.profile_id)
        port_ret = state['return_pct'] if state else 0

        block = f"\n<b>{profile.display_name}</b> ({port_ret:+.1f}%)\n"
        for pos in sorted(positions, key=lambda x: x['return_pct'], reverse=True):
            ret = pos['return_pct']
            days = pos['days_holding']
            arrow = "+" if ret > 0 else ""
            block += f"  {pos['ticker']} {arrow}{ret:.1f}% | ${pos['entry_price']:.0f}->${pos['current_price']:.0f} | {days}d | {pos['shares']:.4g}sh\n"

        if len(current_msg) + len(block) > 3900:
            messages.append(current_msg)
            current_msg = "<b>POSITIONS (cont.)</b>\n"
        current_msg += block

    # Trades closed today
    conn = db.connect()
    c = conn.cursor()
    c.execute("""
        SELECT t.strategy, t.ticker, t.return_pct, t.exit_reason
        FROM trades t
        WHERE t.status = 'CLOSED' AND t.exit_date = ?
        ORDER BY t.return_pct DESC
    """, (datetime.now().strftime('%Y-%m-%d'),))
    closed_today = c.fetchall()
    conn.close()

    if closed_today:
        profile_names = {p.profile_id: p.display_name for _, p in profiles}
        block = "\n<b>CLOSED TODAY</b>\n"
        for row in closed_today:
            strat, ticker, ret, reason = row
            ret = ret or 0
            name = profile_names.get(strat, strat)
            tag = "WIN" if ret > 0 else "LOSS"
            block += f"  {ticker} ({name}) {ret:+.1f}% [{tag}] {reason}\n"

        if len(current_msg) + len(block) > 3900:
            messages.append(current_msg)
            current_msg = ""
        current_msg += block

    if current_msg.strip():
        messages.append(current_msg)

    for msg in messages:
        send_telegram(msg)


# ============================================
# MAIN
# ============================================

def main():
    schedule = os.environ.get('RUN_SCHEDULE', 'all')

    print("=" * 60)
    print("TRADING SIMULATION LABORATORY v3.0")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Schedule: {schedule}")
    print("=" * 60)

    # Initialize
    db = DbManager(DB_PATH)
    db.init_schema()
    db.migrate_to_v3()

    clear_price_cache()
    clear_scan_cache()

    # Load strategies
    profiles = registry.get_all_profiles(schedule_filter=schedule)
    print(f"\nLoaded {len(profiles)} profiles:")
    for strategy, profile in profiles:
        print(f"  - {profile.display_name} ({profile.profile_id}) [{profile.asset_type.value}]")

    # Register profiles in DB
    for strategy, profile in profiles:
        db.register_profile(profile)

    # Fetch data once per source
    sources_needed = registry.get_data_sources_needed(schedule_filter=schedule)
    data_cache = {}
    for source in sources_needed:
        print(f"\nFetching data from: {source}")
        data_cache[source] = fetch_data(source)

    # Generate signals and execute trades
    engine = TradingEngine(db)
    total_added = 0

    print("\nProcessing strategies...")
    for strategy, profile in profiles:
        market_data = data_cache.get(profile.data_source)
        active_positions = db.get_active_positions(profile.profile_id)
        portfolio_state = db.get_portfolio_state(profile.profile_id)

        if not portfolio_state:
            continue

        signals = strategy.generate_signals(profile, market_data, active_positions, portfolio_state)
        if signals:
            n = engine.process_signals(profile, signals)
            if n > 0:
                print(f"  {profile.display_name}: +{n} trades")
                total_added += n

    print(f"\nTotal new trades: {total_added}")

    # Update prices and check exits
    engine.update_all_positions([p for _, p in profiles])

    # Recalculate portfolio values
    engine.recalculate_portfolios([p for _, p in profiles])

    # Save daily snapshots (for dashboard charts)
    for _, profile in profiles:
        db.save_daily_snapshot(profile.profile_id)

    # Save SPY benchmark price
    spy_price = get_price('SPY', AssetType.ETF)
    if spy_price:
        db.save_benchmark_price('SPY', spy_price)

    # Send Telegram reports
    generate_daily_report(db, profiles)
    generate_positions_detail(db, profiles)

    # Run auto-optimizer on Fridays (last run of the week)
    if datetime.now().weekday() == 4:  # Friday
        try:
            from engine.auto_optimizer import AutoOptimizer
            optimizer = AutoOptimizer(db)
            actions = optimizer.run()
            if actions:
                optimizer.send_weekly_summary(actions)
        except Exception as e:
            print(f"Auto-optimizer error: {e}")

    print("\nDone.")


if __name__ == '__main__':
    main()
