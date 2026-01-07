"""
FORWARD TESTING MONITOR - Multi-Strategy
=========================================

Sistema automático para validar estrategias de insider trading.

ESTRATEGIAS SIMULTÁNEAS:
1. Score ≥80 (multi-factor)
2. Score ≥85 (threshold alto)
3. Mega Whale >$10M
4. Ultra Whale >$50M
5. CEO Cluster 5+

OPTIMIZADO PARA:
- PythonAnywhere Beginner (100 seg CPU/día)
- Telegram notifications
- Paper trading

AUTOR: MM
FECHA: 2026-01-06
"""

import os
import sys
import sqlite3
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import time
import json

# ============================================
# CONFIGURACIÓN
# ============================================

# API Keys (desde environment variables)
MASSIVE_API_KEY = os.environ.get('MASSIVE_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Massive API
MASSIVE_BASE_URL = "https://api.massive.com/v1"

# Database
DB_PATH = "data/forward_testing.db"

# Paper Trading
INITIAL_CAPITAL = 10000.0
COMMISSION = 6.95
SLIPPAGE_PCT = 0.15

# Exit Rules
STOP_LOSS_PCT = -10.0
TAKE_PROFIT_PCT = 20.0
MAX_HOLDING_DAYS = 60

# Strategy configs
STRATEGIES = {
    'score_80': {
        'name': 'Score ≥80',
        'position_size_pct': 10,  # 10% del capital
        'max_positions': 10
    },
    'score_85': {
        'name': 'Score ≥85',
        'position_size_pct': 15,
        'max_positions': 7
    },
    'mega_whale': {
        'name': 'Mega Whale >$10M',
        'position_size_pct': 20,
        'max_positions': 5
    },
    'ultra_whale': {
        'name': 'Ultra Whale >$50M',
        'position_size_pct': 30,
        'max_positions': 3
    },
    'ceo_cluster_5': {
        'name': 'CEO Cluster 5+',
        'position_size_pct': 15,
        'max_positions': 7
    }
}

# ============================================
# TELEGRAM
# ============================================

def send_telegram(message):
    """Envía mensaje a Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM DISABLED] {message}")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

# ============================================
# DATABASE
# ============================================

def init_database():
    """Inicializa base de datos"""
    os.makedirs('data', exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabla de trades
    cursor.execute("""
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
            days_holding INTEGER,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy, ticker, trade_date, owner_name)
        )
    """)

    # Tabla de portfolios (paper trading)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT UNIQUE NOT NULL,
            cash REAL NOT NULL,
            invested REAL NOT NULL,
            total REAL NOT NULL,
            return_pct REAL,
            trades_count INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            updated_at DATE
        )
    """)

    # Inicializar portfolios
    for strategy_id in STRATEGIES.keys():
        cursor.execute("""
            INSERT OR IGNORE INTO portfolios (strategy, cash, invested, total, updated_at)
            VALUES (?, ?, 0, ?, ?)
        """, (strategy_id, INITIAL_CAPITAL, INITIAL_CAPITAL, datetime.now().strftime('%Y-%m-%d')))

    # Tabla de ejecuciones (paper trades)
    cursor.execute("""
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
    """Calcula score 0-100"""
    score = 0

    # Tipo
    if row['transaction_type'] != 'P':
        return 0
    score += 30

    # Posición
    title = str(row.get('Title', '')).upper()
    if 'CEO' in title or 'CFO' in title:
        score += 25
    elif 'PRESIDENT' in title:
        score += 22
    elif '10%' in title or 'OWNER' in title:
        score += 20
    elif 'COO' in title or 'CTO' in title:
        score += 18
    elif 'DIRECTOR' in title:
        score += 15
    else:
        score += 5

    # Valor
    try:
        value = abs(float(str(row.get('Value', '0')).replace('$', '').replace(',', '').replace('+', '')))
    except:
        value = 0

    if value >= 82_631_818:
        score += 20
    elif value >= 10_589_596:
        score += 17
    elif value >= 89_100:
        score += 12
    elif value >= 50_000:
        score += 7
    else:
        score += 2

    # Cluster
    if cluster_size >= 5:
        score += 20
    elif cluster_size >= 3:
        score += 15
    elif cluster_size >= 2:
        score += 10

    # Recencia
    try:
        trade_date = datetime.strptime(row['trade_date'], '%Y-%m-%d')
        days = (datetime.now() - trade_date).days
        if days <= 7:
            score += 5
        elif days <= 30:
            score += 3
        elif days <= 90:
            score += 1
    except:
        pass

    return score

# ============================================
# SCRAPING (OPTIMIZADO)
# ============================================

def scrape_openinsider_fast():
    """Scrape rápido de OpenInsider (últimos 7 días)"""
    url = "http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=7&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=500&page=1"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping OpenInsider...")

    try:
        response = requests.get(url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')

        table = soup.find('table', class_='tinytable')
        if not table:
            return []

        trades = []
        for tr in table.find_all('tr')[1:]:  # Skip header
            cols = tr.find_all('td')
            if len(cols) < 11:
                continue

            try:
                trades.append({
                    'trade_date': cols[1].text.strip(),
                    'ticker': cols[3].text.strip(),
                    'company_name': cols[4].text.strip(),
                    'owner_name': cols[5].text.strip(),
                    'Title': cols[6].text.strip(),
                    'transaction_type': cols[7].text.strip(),
                    'last_price': cols[8].text.strip(),
                    'Qty': cols[9].text.strip(),
                    'Value': cols[12].text.strip() if len(cols) > 12 else '0'
                })
            except:
                continue

        print(f"  ✓ {len(trades)} trades scraped")
        return trades

    except Exception as e:
        print(f"  ✗ Scraping failed: {e}")
        return []

# ============================================
# FILTERS
# ============================================

def apply_filters(trades_df):
    """Aplica 5 filtros y retorna trades por estrategia"""
    results = {strategy: [] for strategy in STRATEGIES.keys()}

    # Calcular clusters
    ticker_counts = {}
    for trade in trades_df:
        ticker = trade['ticker']
        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

    for trade in trades_df:
        # Solo compras
        if trade['transaction_type'] != 'P':
            continue

        # Calcular score
        cluster_size = ticker_counts.get(trade['ticker'], 1)
        score = calculate_score(trade, cluster_size)

        # Valor
        try:
            value = abs(float(str(trade['Value']).replace('$', '').replace(',', '').replace('+', '')))
        except:
            value = 0

        # Agregar data
        trade['score'] = score
        trade['cluster_size'] = cluster_size
        trade['value_numeric'] = value

        # Aplicar filtros
        if score >= 85:
            results['score_85'].append(trade.copy())

        if score >= 80:
            results['score_80'].append(trade.copy())

        if value >= 10_000_000:
            results['mega_whale'].append(trade.copy())

        if value >= 50_000_000:
            results['ultra_whale'].append(trade.copy())

        # CEO Cluster 5+
        title = str(trade['Title']).upper()
        if ('CEO' in title or 'CFO' in title) and cluster_size >= 5:
            results['ceo_cluster_5'].append(trade.copy())

    return results

# ============================================
# PRICE API (OPTIMIZADO)
# ============================================

def get_price_fast(ticker):
    """Obtiene precio actual (con rate limiting)"""
    url = f"{MASSIVE_BASE_URL}/stocks/{ticker}/quotes/latest"
    headers = {"Authorization": f"Bearer {MASSIVE_API_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get('close')
    except:
        pass

    return None

# ============================================
# PAPER TRADING
# ============================================

def execute_paper_buy(strategy, trade, portfolio):
    """Ejecuta compra simulada"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    ticker = trade['ticker']

    # Obtener precio
    price = get_price_fast(ticker)
    if price is None:
        conn.close()
        return False

    # Calcular shares
    position_size = portfolio['cash'] * (STRATEGIES[strategy]['position_size_pct'] / 100)
    shares = int((position_size - COMMISSION) / price)

    if shares < 1:
        conn.close()
        return False

    # Costo total
    cost = (shares * price) + COMMISSION

    if cost > portfolio['cash']:
        conn.close()
        return False

    # Insertar trade
    cursor.execute("""
        INSERT INTO trades
        (strategy, ticker, company_name, owner_name, title, trade_date, detection_date,
         score, value, cluster_size, entry_price, current_price, last_updated, status, days_holding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0)
    """, (
        strategy,
        ticker,
        trade.get('company_name'),
        trade.get('owner_name'),
        trade.get('Title'),
        trade['trade_date'],
        datetime.now().strftime('%Y-%m-%d'),
        trade.get('score', 0),
        trade.get('value_numeric', 0),
        trade.get('cluster_size', 1),
        price,
        price,
        datetime.now().strftime('%Y-%m-%d')
    ))

    trade_id = cursor.lastrowid

    # Registrar ejecución
    cursor.execute("""
        INSERT INTO executions (strategy, trade_id, action, ticker, shares, price, commission)
        VALUES (?, ?, 'BUY', ?, ?, ?, ?)
    """, (strategy, trade_id, ticker, shares, price, COMMISSION))

    # Actualizar portfolio
    new_cash = portfolio['cash'] - cost
    new_invested = portfolio['invested'] + (shares * price)
    new_total = new_cash + new_invested

    cursor.execute("""
        UPDATE portfolios
        SET cash = ?, invested = ?, total = ?, trades_count = trades_count + 1, updated_at = ?
        WHERE strategy = ?
    """, (new_cash, new_invested, new_total, datetime.now().strftime('%Y-%m-%d'), strategy))

    conn.commit()
    conn.close()

    # Telegram notification
    msg = f"""
💰 <b>PAPER TRADING - BUY</b>

Strategy: {STRATEGIES[strategy]['name']}
Ticker: ${ticker}
Shares: {shares} @ ${price:.2f}
Cost: ${cost:.2f}
Score: {trade.get('score', 0)}

Cash: ${new_cash:.2f}
"""
    send_telegram(msg)

    return True

def execute_paper_sell(strategy, trade_row, reason):
    """Ejecuta venta simulada"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    ticker = trade_row[2]  # ticker column
    trade_id = trade_row[0]
    entry_price = trade_row[11]

    # Obtener shares originales
    cursor.execute("SELECT shares FROM executions WHERE trade_id = ? AND action = 'BUY'", (trade_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return False

    shares = result[0]

    # Precio actual
    price = get_price_fast(ticker)
    if price is None:
        conn.close()
        return False

    # Revenue
    revenue = (shares * price) - COMMISSION
    return_pct = ((price - entry_price) / entry_price) * 100

    # Actualizar trade
    cursor.execute("""
        UPDATE trades
        SET status = 'CLOSED', exit_price = ?, exit_date = ?, exit_reason = ?, return_pct = ?, current_price = ?
        WHERE id = ?
    """, (price, datetime.now().strftime('%Y-%m-%d'), reason, return_pct, price, trade_id))

    # Registrar ejecución
    cursor.execute("""
        INSERT INTO executions (strategy, trade_id, action, ticker, shares, price, commission)
        VALUES (?, ?, 'SELL', ?, ?, ?, ?)
    """, (strategy, trade_id, ticker, shares, price, COMMISSION))

    # Actualizar portfolio
    cursor.execute("SELECT cash, invested FROM portfolios WHERE strategy = ?", (strategy,))
    portfolio = cursor.fetchone()

    new_cash = portfolio[0] + revenue
    new_invested = portfolio[1] - (shares * entry_price)
    new_total = new_cash + new_invested

    win = 1 if return_pct > 0 else 0

    cursor.execute("""
        UPDATE portfolios
        SET cash = ?, invested = ?, total = ?,
            wins = wins + ?, losses = losses + ?,
            return_pct = ((total - ?) / ?) * 100,
            updated_at = ?
        WHERE strategy = ?
    """, (new_cash, new_invested, new_total, win, 1-win, INITIAL_CAPITAL, INITIAL_CAPITAL,
          datetime.now().strftime('%Y-%m-%d'), strategy))

    conn.commit()
    conn.close()

    # Telegram notification
    emoji = "✅" if return_pct > 0 else "🛑"
    msg = f"""
{emoji} <b>PAPER TRADING - SELL</b>

Strategy: {STRATEGIES[strategy]['name']}
Ticker: ${ticker}
Return: {return_pct:+.2f}%
Reason: {reason}

Shares: {shares} @ ${price:.2f}
Revenue: ${revenue:.2f}
"""
    send_telegram(msg)

    return True

# ============================================
# MAIN LOGIC
# ============================================

def process_strategy(strategy, new_trades):
    """Procesa una estrategia: agrega nuevos y actualiza activos"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get portfolio
    cursor.execute("SELECT cash, invested, total FROM portfolios WHERE strategy = ?", (strategy,))
    portfolio_row = cursor.fetchone()
    portfolio = {'cash': portfolio_row[0], 'invested': portfolio_row[1], 'total': portfolio_row[2]}

    # Count active positions
    cursor.execute("SELECT COUNT(*) FROM trades WHERE strategy = ? AND status = 'ACTIVE'", (strategy,))
    active_count = cursor.fetchone()[0]

    # Add new trades (if space)
    max_positions = STRATEGIES[strategy]['max_positions']
    added = 0

    for trade in new_trades[:max_positions - active_count]:
        # Check if exists
        cursor.execute("""
            SELECT id FROM trades
            WHERE strategy = ? AND ticker = ? AND trade_date = ? AND owner_name = ?
        """, (strategy, trade['ticker'], trade['trade_date'], trade['owner_name']))

        if cursor.fetchone():
            continue

        # Execute buy
        if execute_paper_buy(strategy, trade, portfolio):
            added += 1
            time.sleep(12)  # Rate limit

    # Update active trades
    cursor.execute("""
        SELECT id, strategy, ticker, trade_date, entry_price, current_price, days_holding
        FROM trades
        WHERE strategy = ? AND status = 'ACTIVE'
    """, (strategy,))

    active_trades = cursor.fetchall()

    for trade_row in active_trades:
        trade_id = trade_row[0]
        ticker = trade_row[2]
        entry_price = trade_row[4]
        days = trade_row[6] + 1

        # Get current price
        current_price = get_price_fast(ticker)
        if current_price is None:
            continue

        return_pct = ((current_price - entry_price) / entry_price) * 100

        # Check exit conditions
        exit_reason = None
        if return_pct <= STOP_LOSS_PCT:
            exit_reason = 'STOP_LOSS'
        elif return_pct >= TAKE_PROFIT_PCT:
            exit_reason = 'TAKE_PROFIT'
        elif days >= MAX_HOLDING_DAYS:
            exit_reason = 'TIME_EXIT'

        if exit_reason:
            execute_paper_sell(strategy, trade_row, exit_reason)
        else:
            # Update price
            cursor.execute("""
                UPDATE trades
                SET current_price = ?, return_pct = ?, days_holding = ?, last_updated = ?
                WHERE id = ?
            """, (current_price, return_pct, days, datetime.now().strftime('%Y-%m-%d'), trade_id))

        time.sleep(12)  # Rate limit

    conn.commit()
    conn.close()

    return added

def generate_daily_summary():
    """Genera resumen diario por estrategia"""
    conn = sqlite3.connect(DB_PATH)

    summary = []
    for strategy, config in STRATEGIES.items():
        cursor = conn.cursor()

        cursor.execute("""
            SELECT trades_count, wins, losses, cash, total, return_pct
            FROM portfolios
            WHERE strategy = ?
        """, (strategy,))

        row = cursor.fetchone()
        if row:
            win_rate = (row[1] / row[0] * 100) if row[0] > 0 else 0
            summary.append({
                'strategy': config['name'],
                'trades': row[0],
                'wins': row[1],
                'losses': row[2],
                'win_rate': win_rate,
                'total': row[4],
                'return': row[5] or 0
            })

    conn.close()

    # Telegram message
    msg = f"""
📊 <b>DAILY SUMMARY</b>
{datetime.now().strftime('%Y-%m-%d')}

"""

    for s in summary:
        emoji = "📈" if s['return'] > 0 else "📉" if s['return'] < 0 else "➡️"
        msg += f"""
<b>{s['strategy']}</b>
Trades: {s['trades']} | WR: {s['win_rate']:.1f}%
Balance: ${s['total']:.2f} {emoji} {s['return']:+.2f}%
"""

    send_telegram(msg)

def main():
    """Flujo principal"""
    print("=" * 60)
    print("FORWARD TESTING MONITOR - Multi-Strategy")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Init DB
    init_database()

    # Scrape
    trades = scrape_openinsider_fast()
    if not trades:
        print("\nNo trades found")
        return

    # Apply filters
    filtered = apply_filters(trades)

    print("\nFiltered trades:")
    for strategy, trades_list in filtered.items():
        print(f"  {STRATEGIES[strategy]['name']}: {len(trades_list)} trades")

    # Process each strategy
    print("\nProcessing strategies...")
    for strategy, trades_list in filtered.items():
        if trades_list:
            added = process_strategy(strategy, trades_list)
            print(f"  {STRATEGIES[strategy]['name']}: {added} new positions")

    # Daily summary
    generate_daily_summary()

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

if __name__ == "__main__":
    main()
