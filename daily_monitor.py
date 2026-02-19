"""
FORWARD TESTING MONITOR v2.1 - Multi-Strategy
==============================================

Sistema automatico de paper trading basado en insider trading.

ESTRATEGIAS:
1. Score >=60 (relajado)
2. Score >=70 (intermedio)
3. Score >=80 (estricto)
4. CEO/CFO Any (>$50k)
5. Value >$500k
6. Cluster 2+

Ejecuta via GitHub Actions (dias habiles, 6 PM UTC).
Persiste DB en el repo para acumular historial.

v2.1 - Fixes:
- DB ahora persiste entre ejecuciones (gitignore + git add -f)
- execute_paper_sell usaba indice incorrecto (crasheaba)
- Portfolio total ahora refleja valor de mercado real
- return_pct se recalcula diario (no solo al vender)
- Removido Congress Trading (requiere JS, no funciona)
"""

import os
import sqlite3
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import time

# ============================================
# CONFIGURACION
# ============================================

MASSIVE_API_KEY = os.environ.get('MASSIVE_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

MASSIVE_BASE_URL = "https://api.massive.com/v1"
DB_PATH = "data/forward_testing.db"

INITIAL_CAPITAL = 10000.0
COMMISSION = 6.95
SLIPPAGE_PCT = 0.15

STOP_LOSS_PCT = -10.0
TAKE_PROFIT_PCT = 20.0
MAX_HOLDING_DAYS = 60

STRATEGIES = {
    'score_60': {
        'name': 'Score >=60',
        'position_size_pct': 8,
        'max_positions': 12
    },
    'score_70': {
        'name': 'Score >=70',
        'position_size_pct': 10,
        'max_positions': 10
    },
    'score_80': {
        'name': 'Score >=80',
        'position_size_pct': 12,
        'max_positions': 8
    },
    'ceo_any': {
        'name': 'CEO/CFO',
        'position_size_pct': 10,
        'max_positions': 10
    },
    'value_500k': {
        'name': 'Value >$500k',
        'position_size_pct': 12,
        'max_positions': 8
    },
    'cluster_2': {
        'name': 'Cluster 2+',
        'position_size_pct': 10,
        'max_positions': 10
    },
}

# ============================================
# TELEGRAM
# ============================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM OFF] {message[:80]}...")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

# ============================================
# DATABASE
# ============================================

def init_database():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
            updated_at DATE
        )
    """)

    for sid in STRATEGIES:
        c.execute("""
            INSERT OR IGNORE INTO portfolios (strategy, cash, invested_value, total, updated_at)
            VALUES (?, ?, 0, ?, ?)
        """, (sid, INITIAL_CAPITAL, INITIAL_CAPITAL, datetime.now().strftime('%Y-%m-%d')))

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

# ============================================
# SCORING
# ============================================

def calculate_score(row, cluster_size=1):
    score = 0

    tx_type = str(row.get('transaction_type', '')).upper()
    if tx_type not in ['P', 'P - PURCHASE']:
        return 0
    score += 30

    title = str(row.get('Title', row.get('title', ''))).upper()
    if 'CEO' in title or 'CFO' in title:
        score += 25
    elif 'PRESIDENT' in title:
        score += 22
    elif '10%' in title or 'OWNER' in title:
        score += 20
    elif 'COO' in title or 'CTO' in title:
        score += 18
    elif 'VP' in title or 'VICE' in title:
        score += 16
    elif 'DIRECTOR' in title:
        score += 15
    elif 'OFFICER' in title:
        score += 12
    else:
        score += 5

    try:
        val_str = str(row.get('Value', row.get('value', '0')))
        value = abs(float(val_str.replace('$', '').replace(',', '').replace('+', '').strip()))
    except:
        value = 0

    if value >= 10_000_000:
        score += 20
    elif value >= 1_000_000:
        score += 17
    elif value >= 500_000:
        score += 14
    elif value >= 100_000:
        score += 10
    elif value >= 50_000:
        score += 7
    else:
        score += 2

    if cluster_size >= 5:
        score += 20
    elif cluster_size >= 3:
        score += 15
    elif cluster_size >= 2:
        score += 10

    try:
        td = row.get('trade_date', '')
        if td:
            trade_date = datetime.strptime(str(td)[:10], '%Y-%m-%d')
            days = (datetime.now() - trade_date).days
            if days <= 3:
                score += 5
            elif days <= 7:
                score += 4
            elif days <= 14:
                score += 3
            elif days <= 30:
                score += 2
    except:
        pass

    return score

# ============================================
# SCRAPING
# ============================================

def scrape_openinsider():
    url = "http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=14&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=500&page=1"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping OpenInsider...")

    try:
        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=45)
        soup = BeautifulSoup(resp.content, 'html.parser')

        table = soup.find('table', class_='tinytable')
        if not table:
            print("  ! No table found")
            return []

        trades = []
        for tr in table.find_all('tr')[1:]:
            cols = tr.find_all('td')
            if len(cols) < 13:
                continue
            try:
                raw_date = cols[1].text.strip()
                if '/' in raw_date:
                    p = raw_date.split('/')
                    trade_date = f"{p[2]}-{p[0].zfill(2)}-{p[1].zfill(2)}" if len(p) == 3 else raw_date
                else:
                    trade_date = raw_date

                if 'P' not in cols[7].text.strip().upper():
                    continue

                trades.append({
                    'trade_date': trade_date,
                    'ticker': cols[3].text.strip(),
                    'company_name': cols[4].text.strip()[:50],
                    'owner_name': cols[5].text.strip()[:50],
                    'Title': cols[6].text.strip(),
                    'transaction_type': 'P',
                    'Value': cols[12].text.strip() if len(cols) > 12 else '0',
                })
            except:
                continue

        print(f"  OK {len(trades)} purchases found")
        return trades
    except Exception as e:
        print(f"  ERROR: {e}")
        return []

# ============================================
# FILTERS
# ============================================

def apply_filters(trades_list):
    results = {s: [] for s in STRATEGIES}
    if not trades_list:
        return results

    ticker_counts = {}
    for t in trades_list:
        ticker_counts[t['ticker']] = ticker_counts.get(t['ticker'], 0) + 1

    for trade in trades_list:
        ticker = trade['ticker']
        cluster_size = ticker_counts.get(ticker, 1)
        score = calculate_score(trade, cluster_size)

        try:
            val_str = str(trade.get('Value', '0'))
            value = abs(float(val_str.replace('$', '').replace(',', '').replace('+', '').strip()))
        except:
            value = 0

        trade['score'] = score
        trade['cluster_size'] = cluster_size
        trade['value_numeric'] = value
        title = str(trade.get('Title', '')).upper()

        if score >= 60:
            results['score_60'].append(trade.copy())
        if score >= 70:
            results['score_70'].append(trade.copy())
        if score >= 80:
            results['score_80'].append(trade.copy())
        if ('CEO' in title or 'CFO' in title) and value >= 50000:
            results['ceo_any'].append(trade.copy())
        if value >= 500000:
            results['value_500k'].append(trade.copy())
        if cluster_size >= 2:
            results['cluster_2'].append(trade.copy())

    return results

# ============================================
# PRICE API
# ============================================

def get_price(ticker):
    # Massive API
    if MASSIVE_API_KEY:
        try:
            resp = requests.get(
                f"{MASSIVE_BASE_URL}/stocks/{ticker}/quotes/latest",
                headers={"Authorization": f"Bearer {MASSIVE_API_KEY}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                price = data.get('close') or data.get('price') or data.get('last')
                if price:
                    return float(price)
        except:
            pass

    # Yahoo Finance fallback
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d",
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if resp.status_code == 200:
            price = resp.json()['chart']['result'][0]['meta'].get('regularMarketPrice')
            if price:
                return float(price)
    except:
        pass

    return None

# ============================================
# PAPER TRADING
# ============================================

def execute_buy(strategy, trade, portfolio_cash):
    """Compra simulada. Retorna (True, cost) o (False, 0)."""
    ticker = trade['ticker']
    price = get_price(ticker)
    if not price:
        return False, 0

    position_size = portfolio_cash * (STRATEGIES[strategy]['position_size_pct'] / 100)
    shares = int((position_size - COMMISSION) / price)
    if shares < 1:
        return False, 0

    cost = (shares * price) + COMMISSION
    if cost > portfolio_cash:
        return False, 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO trades
            (strategy, ticker, company_name, owner_name, title, trade_date, detection_date,
             score, value, cluster_size, entry_price, current_price, last_updated, status, days_holding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0)
        """, (
            strategy, ticker,
            trade.get('company_name', ''), trade.get('owner_name', ''), trade.get('Title', ''),
            trade['trade_date'], datetime.now().strftime('%Y-%m-%d'),
            trade.get('score', 0), trade.get('value_numeric', 0), trade.get('cluster_size', 1),
            price, price, datetime.now().strftime('%Y-%m-%d')
        ))
        trade_id = c.lastrowid

        c.execute("""
            INSERT INTO executions (strategy, trade_id, action, ticker, shares, price, commission)
            VALUES (?, ?, 'BUY', ?, ?, ?, ?)
        """, (strategy, trade_id, ticker, shares, price, COMMISSION))

        c.execute("""
            UPDATE portfolios
            SET cash = cash - ?, trades_count = trades_count + 1, updated_at = ?
            WHERE strategy = ?
        """, (cost, datetime.now().strftime('%Y-%m-%d'), strategy))

        conn.commit()
        print(f"    + BUY {ticker} x{shares} @ ${price:.2f}")
        return True, cost
    except sqlite3.IntegrityError:
        return False, 0
    except Exception as e:
        print(f"    ! Error buying {ticker}: {e}")
        return False, 0
    finally:
        conn.close()


def execute_sell(trade_id, strategy, ticker, entry_price, reason):
    """Venta simulada."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT shares FROM executions WHERE trade_id = ? AND action = 'BUY'", (trade_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    shares = row[0]

    price = get_price(ticker)
    if not price:
        conn.close()
        return False

    revenue = (shares * price) - COMMISSION
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
    """, (strategy, trade_id, ticker, shares, price, COMMISSION))

    c.execute("""
        UPDATE portfolios
        SET cash = cash + ?, wins = wins + ?, losses = losses + ?, updated_at = ?
        WHERE strategy = ?
    """, (revenue, win, 1 - win, datetime.now().strftime('%Y-%m-%d'), strategy))

    conn.commit()
    conn.close()

    tag = "WIN" if win else "LOSS"
    print(f"    - SELL {ticker} ({tag}) {ret_pct:+.1f}% | {reason}")
    return True

# ============================================
# MAIN LOGIC
# ============================================

def process_new_trades(strategy, new_trades):
    """Agrega nuevos trades si hay espacio."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT cash FROM portfolios WHERE strategy = ?", (strategy,))
    cash = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM trades WHERE strategy = ? AND status = 'ACTIVE'", (strategy,))
    active = c.fetchone()[0]
    conn.close()

    slots = STRATEGIES[strategy]['max_positions'] - active
    if slots <= 0:
        return 0

    added = 0
    for trade in new_trades[:slots]:
        ok, cost = execute_buy(strategy, trade, cash)
        if ok:
            added += 1
            cash -= cost
            time.sleep(2)
    return added


def update_active_trades():
    """Actualiza precios, ejecuta exits, recalcula portfolios."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Fetch all active trades with their shares
    c.execute("""
        SELECT t.id, t.strategy, t.ticker, t.entry_price, t.days_holding,
               e.shares
        FROM trades t
        JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
        WHERE t.status = 'ACTIVE'
    """)
    active = c.fetchall()
    conn.close()

    print(f"\nUpdating {len(active)} active trades...")

    for row in active:
        trade_id, strategy, ticker, entry_price, days_held, shares = row
        days_held = (days_held or 0) + 1

        price = get_price(ticker)
        if not price:
            continue

        ret_pct = ((price - entry_price) / entry_price) * 100

        # Check exits
        exit_reason = None
        if ret_pct <= STOP_LOSS_PCT:
            exit_reason = 'STOP_LOSS'
        elif ret_pct >= TAKE_PROFIT_PCT:
            exit_reason = 'TAKE_PROFIT'
        elif days_held >= MAX_HOLDING_DAYS:
            exit_reason = 'TIME_EXIT'

        if exit_reason:
            execute_sell(trade_id, strategy, ticker, entry_price, exit_reason)
        else:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE trades
                SET current_price=?, return_pct=?, days_holding=?, last_updated=?
                WHERE id=?
            """, (price, ret_pct, days_held, datetime.now().strftime('%Y-%m-%d'), trade_id))
            conn.commit()
            conn.close()

        time.sleep(1)


def recalculate_portfolios():
    """Recalcula el valor real de cada portfolio basado en precios actuales."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for strategy in STRATEGIES:
        # Cash actual
        c.execute("SELECT cash FROM portfolios WHERE strategy = ?", (strategy,))
        cash = c.fetchone()[0]

        # Valor de mercado de posiciones activas = SUM(shares * current_price)
        c.execute("""
            SELECT COALESCE(SUM(e.shares * t.current_price), 0)
            FROM trades t
            JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
            WHERE t.strategy = ? AND t.status = 'ACTIVE'
        """, (strategy,))
        market_value = c.fetchone()[0]

        total = cash + market_value
        ret_pct = ((total - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100

        c.execute("""
            UPDATE portfolios
            SET invested_value = ?, total = ?, return_pct = ?, updated_at = ?
            WHERE strategy = ?
        """, (market_value, total, ret_pct, datetime.now().strftime('%Y-%m-%d'), strategy))

    conn.commit()
    conn.close()
    print("Portfolios recalculated.")


def generate_daily_summary():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    data = []
    for sid, cfg in STRATEGIES.items():
        c.execute("""
            SELECT trades_count, wins, losses, cash, total, return_pct
            FROM portfolios WHERE strategy = ?
        """, (sid,))
        p = c.fetchone()
        if not p:
            continue

        c.execute("SELECT COUNT(*) FROM trades WHERE strategy=? AND status='ACTIVE'", (sid,))
        active = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM trades WHERE strategy=? AND DATE(detection_date)=DATE('now')", (sid,))
        today_new = c.fetchone()[0]

        # Closed trades stats
        c.execute("""
            SELECT COUNT(*), AVG(return_pct)
            FROM trades WHERE strategy=? AND status='CLOSED'
        """, (sid,))
        closed_row = c.fetchone()
        closed = closed_row[0] if closed_row else 0

        wr = (p[1] / (p[1] + p[2]) * 100) if (p[1] + p[2]) > 0 else 0

        data.append({
            'name': cfg['name'],
            'total_trades': p[0],
            'wins': p[1],
            'losses': p[2],
            'wr': wr,
            'cash': p[3],
            'total': p[4],
            'ret': p[5] or 0,
            'active': active,
            'closed': closed,
            'today': today_new,
        })

    conn.close()

    data.sort(key=lambda x: x['ret'], reverse=True)

    today_str = datetime.now().strftime('%Y-%m-%d')
    msg = f"<b>DAILY REPORT</b>\n{today_str}\n\n"

    for s in data:
        arrow = "+" if s['ret'] > 0 else ""
        new_tag = f" [+{s['today']} new]" if s['today'] > 0 else ""

        msg += f"<b>{s['name']}</b>{new_tag}\n"
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


def generate_positions_detail():
    """Envia segundo mensaje con detalle de posiciones activas por estrategia."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Obtener estrategias ordenadas por return%
    c.execute("SELECT strategy, return_pct FROM portfolios ORDER BY return_pct DESC")
    strats = c.fetchall()

    messages = []
    current_msg = "<b>POSITIONS DETAIL</b>\n"

    for strategy, port_ret in strats:
        name = STRATEGIES.get(strategy, {}).get('name', strategy)

        c.execute("""
            SELECT t.ticker, t.entry_price, t.current_price, t.return_pct,
                   t.days_holding, t.owner_name, t.title, e.shares
            FROM trades t
            JOIN executions e ON e.trade_id = t.id AND e.action = 'BUY'
            WHERE t.strategy = ? AND t.status = 'ACTIVE'
            ORDER BY t.return_pct DESC
        """, (strategy,))
        positions = c.fetchall()

        if not positions:
            continue

        block = f"\n<b>{name}</b> ({port_ret:+.1f}%)\n"
        for pos in positions:
            ticker, entry, current, ret, days, owner, title, shares = pos
            ret = ret or 0
            days = days or 0
            arrow = "+" if ret > 0 else ""
            block += f"  {ticker} {arrow}{ret:.1f}% | ${entry:.0f}→${current:.0f} | {days}d | {shares}sh\n"

        # Telegram limit: 4096 chars. Si se pasa, enviar lo acumulado y empezar nuevo
        if len(current_msg) + len(block) > 3900:
            messages.append(current_msg)
            current_msg = "<b>POSITIONS (cont.)</b>\n"

        current_msg += block

    # Trades cerrados hoy
    c.execute("""
        SELECT t.strategy, t.ticker, t.return_pct, t.exit_reason
        FROM trades t
        WHERE t.status = 'CLOSED' AND t.exit_date = ?
        ORDER BY t.return_pct DESC
    """, (datetime.now().strftime('%Y-%m-%d'),))
    closed_today = c.fetchall()

    if closed_today:
        block = "\n<b>CLOSED TODAY</b>\n"
        for row in closed_today:
            strat, ticker, ret, reason = row
            ret = ret or 0
            name = STRATEGIES.get(strat, {}).get('name', strat)
            tag = "WIN" if ret > 0 else "LOSS"
            block += f"  {ticker} ({name}) {ret:+.1f}% [{tag}] {reason}\n"

        if len(current_msg) + len(block) > 3900:
            messages.append(current_msg)
            current_msg = ""
        current_msg += block

    conn.close()

    if current_msg.strip():
        messages.append(current_msg)

    for msg in messages:
        send_telegram(msg)


def main():
    print("=" * 60)
    print("FORWARD TESTING MONITOR v2.1")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    init_database()

    # 1. Scrape
    trades = scrape_openinsider()
    if not trades:
        print("\nNo trades found")
        recalculate_portfolios()
        generate_daily_summary()
        generate_positions_detail()
        return

    print(f"\n{len(trades)} purchases from OpenInsider")

    # 2. Filter
    filtered = apply_filters(trades)
    print("\nFiltered:")
    for s, tlist in filtered.items():
        print(f"  {STRATEGIES[s]['name']}: {len(tlist)}")

    # 3. Buy new positions
    print("\nBuying...")
    total_added = 0
    for s, tlist in filtered.items():
        if tlist:
            n = process_new_trades(s, tlist)
            if n > 0:
                print(f"  {STRATEGIES[s]['name']}: +{n}")
                total_added += n
    print(f"Total new: {total_added}")

    # 4. Update prices and check exits
    update_active_trades()

    # 5. Recalculate real portfolio values
    recalculate_portfolios()

    # 6. Send summary
    generate_daily_summary()

    # 7. Send positions detail
    generate_positions_detail()

    print("\n" + "=" * 60)
    print("DONE")


if __name__ == "__main__":
    main()
