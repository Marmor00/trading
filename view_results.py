"""
VIEW RESULTS - Dashboard
========================

Muestra resultados del forward testing por estrategia.

EJECUTAR:
    python3 view_results.py
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/forward_testing.db"

STRATEGIES = {
    'score_80': 'Score ≥80',
    'score_85': 'Score ≥85',
    'mega_whale': 'Mega Whale >$10M',
    'ultra_whale': 'Ultra Whale >$50M',
    'ceo_cluster_5': 'CEO Cluster 5+'
}

def print_header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def view_portfolios():
    """Ver estado de portfolios"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print_header("PORTFOLIOS - PAPER TRADING")

    cursor.execute("""
        SELECT strategy, cash, invested, total, return_pct, trades_count, wins, losses, updated_at
        FROM portfolios
        ORDER BY return_pct DESC
    """)

    rows = cursor.fetchall()

    print(f"\n{'Strategy':<20} {'Cash':<12} {'Invested':<12} {'Total':<12} {'Return':<10} {'Trades':<8} {'WR':<8}")
    print("-" * 95)

    for row in rows:
        strategy_name = STRATEGIES.get(row[0], row[0])
        win_rate = (row[6] / row[5] * 100) if row[5] > 0 else 0
        emoji = "📈" if row[4] and row[4] > 0 else "📉" if row[4] and row[4] < 0 else "➡️"

        print(f"{strategy_name:<20} ${row[1]:<11.2f} ${row[2]:<11.2f} ${row[3]:<11.2f} {emoji} {row[4] or 0:>6.2f}% {row[5]:<8} {win_rate:>5.1f}%")

    conn.close()

def view_active_trades():
    """Ver trades activos"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print_header("ACTIVE TRADES")

    cursor.execute("""
        SELECT strategy, ticker, entry_price, current_price, return_pct, days_holding, score
        FROM trades
        WHERE status = 'ACTIVE'
        ORDER BY strategy, return_pct DESC
    """)

    rows = cursor.fetchall()

    if not rows:
        print("\n  No active trades")
        conn.close()
        return

    print(f"\n{'Strategy':<20} {'Ticker':<8} {'Entry':<10} {'Current':<10} {'Return':<10} {'Days':<6} {'Score'}")
    print("-" * 80)

    for row in rows:
        strategy_name = STRATEGIES.get(row[0], row[0])
        emoji = "📈" if row[4] and row[4] > 0 else "📉"

        print(f"{strategy_name:<20} {row[1]:<8} ${row[2]:<9.2f} ${row[3]:<9.2f} {emoji} {row[4] or 0:>6.2f}% {row[5]:<6} {row[6]}")

    conn.close()

def view_closed_trades():
    """Ver trades cerrados (últimos 20)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print_header("CLOSED TRADES (Last 20)")

    cursor.execute("""
        SELECT strategy, ticker, entry_price, exit_price, return_pct, exit_reason, exit_date
        FROM trades
        WHERE status = 'CLOSED'
        ORDER BY exit_date DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    if not rows:
        print("\n  No closed trades yet")
        conn.close()
        return

    print(f"\n{'Strategy':<20} {'Ticker':<8} {'Entry':<10} {'Exit':<10} {'Return':<10} {'Reason':<15} {'Date'}")
    print("-" * 95)

    for row in rows:
        strategy_name = STRATEGIES.get(row[0], row[0])
        emoji = "✅" if row[4] and row[4] > 0 else "🛑"

        print(f"{strategy_name:<20} {row[1]:<8} ${row[2]:<9.2f} ${row[3]:<9.2f} {emoji} {row[4] or 0:>6.2f}% {row[5]:<15} {row[6]}")

    conn.close()

def main():
    print("\n" + "=" * 80)
    print("  FORWARD TESTING DASHBOARD")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    view_portfolios()
    view_active_trades()
    view_closed_trades()

    print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    main()
