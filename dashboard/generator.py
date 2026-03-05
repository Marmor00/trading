"""
Dashboard generator: reads SQLite database and produces static HTML.

Outputs to dashboard/output/ for deployment to GitHub Pages.
"""

import os
import sys
import sqlite3
import json
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'forward_testing.db')
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')


# ============================================
# DATA QUERIES
# ============================================

def get_leaderboard(conn):
    """Get all profiles sorted by return %."""
    c = conn.cursor()

    c.execute("""
        SELECT p.strategy, p.cash, p.invested_value, p.total, p.return_pct,
               p.trades_count, p.wins, p.losses, p.updated_at,
               p.sharpe_ratio, p.max_drawdown, p.profit_factor, p.sortino_ratio
        FROM portfolios p
        ORDER BY p.return_pct DESC
    """)
    rows = c.fetchall()

    leaderboard = []
    for i, row in enumerate(rows):
        pid = row[0]
        wins, losses = row[6] or 0, row[7] or 0
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

        c.execute("SELECT COUNT(*) FROM trades WHERE strategy=? AND status='ACTIVE'", (pid,))
        active = c.fetchone()[0]

        # Get profile metadata
        c.execute("SELECT display_name, description, asset_type, data_source, created_at FROM profiles WHERE profile_id=?", (pid,))
        meta = c.fetchone()

        # Days active: from profile creation to now
        days_active = 0
        if meta and meta[4]:
            try:
                created = datetime.strptime(str(meta[4])[:10], '%Y-%m-%d')
                days_active = (datetime.now() - created).days
            except (ValueError, TypeError):
                pass

        # Last signal: most recent signal logged for this profile
        last_signal = '-'
        try:
            c.execute("""
                SELECT DATE(created_at) FROM signals_log
                WHERE profile_id=? AND was_executed=1
                ORDER BY created_at DESC LIMIT 1
            """, (pid,))
            sig_row = c.fetchone()
            if sig_row and sig_row[0]:
                last_signal = sig_row[0]
        except Exception:
            pass

        leaderboard.append({
            'rank': i + 1,
            'profile_id': pid,
            'display_name': meta[0] if meta else pid,
            'description': meta[1] if meta else '',
            'asset_type': meta[2] if meta else 'stock',
            'data_source': meta[3] if meta else 'unknown',
            'cash': row[1] or 0,
            'invested': row[2] or 0,
            'total': row[3] or 0,
            'return_pct': row[4] or 0,
            'trades_count': row[5] or 0,
            'wins': wins,
            'losses': losses,
            'win_rate': wr,
            'active': active,
            'updated_at': row[8] or '',
            'days_active': days_active,
            'last_signal': last_signal,
            'sharpe_ratio': row[9],
            'max_drawdown': row[10],
            'profit_factor': row[11],
            'sortino_ratio': row[12],
        })

    return leaderboard


def get_return_curves(conn):
    """Get time-series data for return curves chart."""
    c = conn.cursor()

    # Only show active profiles in return curves
    c.execute("""
        SELECT DISTINCT ps.profile_id FROM portfolio_snapshots ps
        JOIN profiles pr ON pr.profile_id = ps.profile_id
        WHERE pr.is_active = 1
        ORDER BY ps.profile_id
    """)
    profile_ids = [row[0] for row in c.fetchall()]

    c.execute("SELECT DISTINCT snapshot_date FROM portfolio_snapshots ORDER BY snapshot_date")
    dates = [row[0] for row in c.fetchall()]

    if not dates or not profile_ids:
        return {'labels': [], 'datasets': []}

    # Colors for each profile (30+ to support up to 35 profiles)
    colors = [
        '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
        '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b',
        '#2980b9', '#d35400', '#27ae60', '#8e44ad', '#f1c40f',
        '#e91e63', '#00bcd4', '#ff9800', '#4caf50', '#673ab7',
        '#009688', '#ff5722', '#607d8b', '#795548', '#cddc39',
        '#03a9f4', '#e040fb', '#76ff03', '#ff6e40', '#18ffff',
    ]

    datasets = []
    for i, pid in enumerate(profile_ids):
        c.execute("""
            SELECT snapshot_date, return_pct FROM portfolio_snapshots
            WHERE profile_id = ? ORDER BY snapshot_date
        """, (pid,))
        data = {row[0]: row[1] for row in c.fetchall()}

        # Get display name
        c.execute("SELECT display_name FROM profiles WHERE profile_id=?", (pid,))
        name_row = c.fetchone()
        name = name_row[0] if name_row else pid

        is_benchmark = pid == 'spy_benchmark'
        datasets.append({
            'label': name,
            'data': [data.get(d, None) for d in dates],
            'borderColor': '#888888' if is_benchmark else colors[i % len(colors)],
            'borderDash': [5, 5] if is_benchmark else [],
            'borderWidth': 2 if is_benchmark else 2.5,
            'fill': False,
            'tension': 0.3,
            'pointRadius': 0,
        })

    return {'labels': dates, 'datasets': datasets}


def get_profile_detail(conn, profile_id):
    """Get detailed data for a single profile."""
    c = conn.cursor()

    # Profile metadata
    c.execute("SELECT * FROM profiles WHERE profile_id=?", (profile_id,))
    meta_row = c.fetchone()
    if not meta_row:
        return None

    meta_cols = [desc[0] for desc in c.description]
    meta = dict(zip(meta_cols, meta_row))

    # Portfolio state
    c.execute("SELECT * FROM portfolios WHERE strategy=?", (profile_id,))
    port_row = c.fetchone()
    port_cols = [desc[0] for desc in c.description]
    portfolio = dict(zip(port_cols, port_row)) if port_row else {}

    # Active trades
    c.execute("""
        SELECT t.ticker, t.company_name, t.entry_price, t.current_price,
               t.return_pct, t.days_holding, t.owner_name, t.title,
               e.shares, t.trade_date, t.score
        FROM trades t
        JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
        WHERE t.strategy = ? AND t.status = 'ACTIVE'
        ORDER BY t.return_pct DESC
    """, (profile_id,))
    active_trades = []
    for row in c.fetchall():
        active_trades.append({
            'ticker': row[0], 'company': row[1], 'entry_price': row[2],
            'current_price': row[3], 'return_pct': row[4] or 0,
            'days': row[5] or 0, 'insider': row[6], 'title': row[7],
            'shares': row[8], 'trade_date': row[9], 'score': row[10] or 0,
        })

    # Closed trades
    c.execute("""
        SELECT t.ticker, t.company_name, t.entry_price, t.exit_price,
               t.return_pct, t.days_holding, t.exit_reason, t.exit_date,
               t.owner_name, t.score
        FROM trades t
        WHERE t.strategy = ? AND t.status = 'CLOSED'
        ORDER BY t.exit_date DESC
    """, (profile_id,))
    closed_trades = []
    for row in c.fetchall():
        closed_trades.append({
            'ticker': row[0], 'company': row[1], 'entry_price': row[2],
            'exit_price': row[3], 'return_pct': row[4] or 0,
            'days': row[5] or 0, 'exit_reason': row[6], 'exit_date': row[7],
            'insider': row[8], 'score': row[9] or 0,
        })

    # Portfolio snapshots for value chart
    c.execute("""
        SELECT snapshot_date, total_value, cash, invested_value, return_pct
        FROM portfolio_snapshots
        WHERE profile_id = ?
        ORDER BY snapshot_date
    """, (profile_id,))
    snapshots = []
    for row in c.fetchall():
        snapshots.append({
            'date': row[0], 'total': row[1], 'cash': row[2],
            'invested': row[3], 'return_pct': row[4],
        })

    # Metrics
    wins = portfolio.get('wins', 0) or 0
    losses = portfolio.get('losses', 0) or 0
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    avg_win = 0
    avg_loss = 0
    if closed_trades:
        winning = [t['return_pct'] for t in closed_trades if t['return_pct'] > 0]
        losing = [t['return_pct'] for t in closed_trades if t['return_pct'] <= 0]
        avg_win = sum(winning) / len(winning) if winning else 0
        avg_loss = sum(losing) / len(losing) if losing else 0

    best_trade = max((t['return_pct'] for t in closed_trades), default=0)
    worst_trade = min((t['return_pct'] for t in closed_trades), default=0)

    # Max drawdown from snapshots (fallback if not in portfolio)
    max_drawdown = portfolio.get('max_drawdown') or 0
    if max_drawdown == 0 and snapshots:
        peak = 0
        for snap in snapshots:
            val = snap['total']
            if val > peak:
                peak = val
            dd = ((val - peak) / peak * 100) if peak > 0 else 0
            if dd < max_drawdown:
                max_drawdown = dd

    return {
        'meta': meta,
        'portfolio': portfolio,
        'active_trades': active_trades,
        'closed_trades': closed_trades,
        'snapshots': snapshots,
        'metrics': {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'max_drawdown': max_drawdown,
            'total_closed': total_closed,
            'sharpe_ratio': portfolio.get('sharpe_ratio'),
            'profit_factor': portfolio.get('profit_factor'),
            'sortino_ratio': portfolio.get('sortino_ratio'),
        },
    }


def get_optimizer_log(conn, limit=20):
    """Get recent optimizer actions."""
    c = conn.cursor()
    try:
        c.execute("""
            SELECT log_date, action, profile_id, base_profile_id, reason
            FROM optimizer_log
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return [{'date': r[0], 'action': r[1], 'profile_id': r[2],
                 'base': r[3], 'reason': r[4]} for r in c.fetchall()]
    except Exception:
        return []


def get_retired_profiles(conn):
    """Get retired (inactive) profiles for the graveyard section."""
    c = conn.cursor()
    try:
        c.execute("""
            SELECT p.profile_id, p.display_name, p.retired_date, p.spawned_from,
                   pt.return_pct, pt.wins, pt.losses
            FROM profiles p
            LEFT JOIN portfolios pt ON pt.strategy = p.profile_id
            WHERE p.is_active = 0 AND p.retired_date IS NOT NULL
            ORDER BY p.retired_date DESC
        """)
        return [{'profile_id': r[0], 'display_name': r[1], 'retired_date': r[2],
                 'spawned_from': r[3], 'return_pct': r[4] or 0,
                 'wins': r[5] or 0, 'losses': r[6] or 0} for r in c.fetchall()]
    except Exception:
        return []


# ============================================
# HTML GENERATION
# ============================================

def generate_dashboard():
    """Generate all dashboard HTML files."""
    if not os.path.exists(DB_PATH):
        print("No database found, skipping dashboard generation.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Copy static files
    if os.path.exists(STATIC_DIR):
        import shutil
        static_out = os.path.join(OUTPUT_DIR, 'static')
        if os.path.exists(static_out):
            shutil.rmtree(static_out)
        shutil.copytree(STATIC_DIR, static_out)

    # Setup Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    env.filters['fmt_money'] = lambda v: f"${v:,.0f}" if v else "$0"
    env.filters['fmt_pct'] = lambda v: f"{v:+.1f}%" if v else "0.0%"
    env.filters['fmt_shares'] = lambda v: f"{v:.4g}" if v else "0"

    conn = sqlite3.connect(DB_PATH)

    # Generate index page
    leaderboard = get_leaderboard(conn)
    return_curves = get_return_curves(conn)
    optimizer_log = get_optimizer_log(conn)
    retired = get_retired_profiles(conn)
    now = datetime.now().strftime('%Y-%m-%d %H:%M UTC')

    try:
        index_template = env.get_template('index.html')
        index_html = index_template.render(
            leaderboard=leaderboard,
            return_curves_json=json.dumps(return_curves),
            optimizer_log=optimizer_log,
            retired_profiles=retired,
            updated_at=now,
            profile_count=len(leaderboard),
        )
        with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(index_html)
        print(f"Generated: index.html ({len(leaderboard)} profiles)")
    except Exception as e:
        print(f"Error generating index.html: {e}")

    # Generate profile detail pages
    for entry in leaderboard:
        pid = entry['profile_id']
        try:
            detail = get_profile_detail(conn, pid)
            if not detail:
                continue

            profile_template = env.get_template('profile.html')
            profile_html = profile_template.render(
                profile=detail,
                snapshots_json=json.dumps(detail['snapshots']),
                updated_at=now,
            )
            with open(os.path.join(OUTPUT_DIR, f'profile_{pid}.html'), 'w', encoding='utf-8') as f:
                f.write(profile_html)
            print(f"Generated: profile_{pid}.html")
        except Exception as e:
            print(f"Error generating profile_{pid}.html: {e}")

    conn.close()
    print(f"\nDashboard generated in {OUTPUT_DIR}/")


if __name__ == '__main__':
    generate_dashboard()
