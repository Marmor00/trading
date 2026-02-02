"""
FORWARD TESTING MONITOR v2.0 - Multi-Strategy
==============================================

Sistema automatico para validar estrategias de insider trading + congress trading.

ESTRATEGIAS (ordenadas de mas a menos estrictas):
1. Score >=60 (relajado - mas trades)
2. Score >=70 (intermedio)
3. Score >=80 (estricto - original)
4. CEO Any (CEO/CFO comprando >$50k)
5. Value 500k (compras >$500k)
6. Cluster 2+ (2+ insiders mismo ticker)
7. Congress (politicos de EE.UU.)

OPTIMIZADO PARA:
- PythonAnywhere Beginner (100 seg CPU/dia)
- Telegram notifications
- Paper trading

AUTOR: MM
FECHA: 2026-02-01
VERSION: 2.0
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
# CONFIGURACION
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

# Strategy configs - NUEVAS ESTRATEGIAS MAS REALISTAS
STRATEGIES = {
    # Estrategias basadas en Score (de relajado a estricto)
    'score_60': {
        'name': 'Score >=60 (Relajado)',
        'description': 'Filtro amplio para capturar mas oportunidades',
        'position_size_pct': 8,
        'max_positions': 12
    },
    'score_70': {
        'name': 'Score >=70 (Medio)',
        'description': 'Balance entre volumen y calidad',
        'position_size_pct': 10,
        'max_positions': 10
    },
    'score_80': {
        'name': 'Score >=80 (Estricto)',
        'description': 'Solo los mejores trades',
        'position_size_pct': 12,
        'max_positions': 8
    },
    # Estrategias por tipo de insider
    'ceo_any': {
        'name': 'CEO/CFO Any',
        'description': 'Cualquier compra de CEO/CFO >$50k',
        'position_size_pct': 10,
        'max_positions': 10
    },
    # Estrategias por valor
    'value_500k': {
        'name': 'Value >$500k',
        'description': 'Compras grandes sin importar quien',
        'position_size_pct': 12,
        'max_positions': 8
    },
    # Estrategias por cluster
    'cluster_2': {
        'name': 'Cluster 2+',
        'description': '2+ insiders comprando mismo ticker',
        'position_size_pct': 10,
        'max_positions': 10
    },
    # Congress Trading
    'congress': {
        'name': 'Congress Trading',
        'description': 'Siguiendo a politicos de EE.UU.',
        'position_size_pct': 10,
        'max_positions': 10
    }
}

# ============================================
# TELEGRAM
# ============================================

def send_telegram(message):
    """Envia mensaje a Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM DISABLED] {message[:100]}...")
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
            source TEXT DEFAULT 'openinsider',

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

    # Tipo (30 pts)
    tx_type = str(row.get('transaction_type', '')).upper()
    if tx_type not in ['P', 'P - PURCHASE']:
        return 0
    score += 30

    # Posicion (25 pts max)
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

    # Valor (20 pts max)
    try:
        value_str = str(row.get('Value', row.get('value', '0')))
        value = abs(float(value_str.replace('$', '').replace(',', '').replace('+', '').strip()))
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

    # Cluster (20 pts max)
    if cluster_size >= 5:
        score += 20
    elif cluster_size >= 3:
        score += 15
    elif cluster_size >= 2:
        score += 10

    # Recencia (5 pts max)
    try:
        trade_date_str = row.get('trade_date', row.get('Trade Date', ''))
        if trade_date_str:
            trade_date = datetime.strptime(str(trade_date_str)[:10], '%Y-%m-%d')
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
# SCRAPING - OPENINSIDER
# ============================================

def scrape_openinsider():
    """Scrape de OpenInsider (ultimos 14 dias para mas datos)"""
    # Aumentamos a 14 dias para capturar mas trades
    url = "http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=14&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=500&page=1"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping OpenInsider (14 dias)...")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=45)
        soup = BeautifulSoup(response.content, 'html.parser')

        table = soup.find('table', class_='tinytable')
        if not table:
            print("  ! No se encontro tabla")
            return []

        trades = []
        rows = table.find_all('tr')[1:]  # Skip header

        for tr in rows:
            cols = tr.find_all('td')
            if len(cols) < 13:
                continue

            try:
                # Parsear fecha correctamente
                trade_date_raw = cols[1].text.strip()
                # Convertir de MM/DD/YYYY a YYYY-MM-DD si es necesario
                try:
                    if '/' in trade_date_raw:
                        parts = trade_date_raw.split('/')
                        if len(parts) == 3:
                            trade_date = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                        else:
                            trade_date = trade_date_raw
                    else:
                        trade_date = trade_date_raw
                except:
                    trade_date = trade_date_raw

                # Parsear tipo de transaccion
                tx_type = cols[7].text.strip().upper()
                if 'P' not in tx_type:
                    continue  # Solo compras

                trades.append({
                    'trade_date': trade_date,
                    'ticker': cols[3].text.strip(),
                    'company_name': cols[4].text.strip()[:50],
                    'owner_name': cols[5].text.strip()[:50],
                    'Title': cols[6].text.strip(),
                    'transaction_type': 'P',
                    'last_price': cols[8].text.strip(),
                    'Qty': cols[9].text.strip(),
                    'Value': cols[12].text.strip() if len(cols) > 12 else '0',
                    'source': 'openinsider'
                })
            except Exception as e:
                continue

        print(f"  OK {len(trades)} compras encontradas")
        return trades

    except Exception as e:
        print(f"  ERROR Scraping failed: {e}")
        return []

# ============================================
# SCRAPING - CONGRESS TRADING
# ============================================

def scrape_congress_trading():
    """Scrape de Quiver Quantitative (Congress Trading)"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping Congress Trading...")

    # Quiver Quant tiene una pagina publica con trades recientes
    url = "https://www.quiverquant.com/congresstrading/"

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"  ! Congress scraping returned {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')

        # Buscar la tabla de trades
        trades = []

        # Quiver usa una tabla con clase especifica
        table = soup.find('table')
        if not table:
            # Intentar buscar datos en scripts JSON
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'trades' in script.string.lower():
                    # Intentar parsear JSON embebido
                    try:
                        import re
                        json_match = re.search(r'\[.*\]', script.string)
                        if json_match:
                            data = json.loads(json_match.group())
                            for item in data[:20]:  # Limitar a 20
                                if item.get('Transaction', '').upper() == 'PURCHASE':
                                    trades.append({
                                        'trade_date': item.get('TransactionDate', '')[:10],
                                        'ticker': item.get('Ticker', ''),
                                        'company_name': item.get('Company', '')[:50],
                                        'owner_name': item.get('Representative', '')[:50],
                                        'Title': 'Congress Member',
                                        'transaction_type': 'P',
                                        'Value': str(item.get('Amount', '0')),
                                        'source': 'congress'
                                    })
                    except:
                        continue

            print(f"  OK {len(trades)} trades de Congress encontrados")
            return trades

        # Si hay tabla, parsearla
        rows = table.find_all('tr')[1:]
        for tr in rows[:20]:  # Limitar
            cols = tr.find_all('td')
            if len(cols) >= 4:
                try:
                    tx_type = cols[3].text.strip().upper() if len(cols) > 3 else ''
                    if 'PURCHASE' in tx_type or 'BUY' in tx_type:
                        trades.append({
                            'trade_date': cols[0].text.strip()[:10],
                            'ticker': cols[1].text.strip(),
                            'company_name': cols[2].text.strip()[:50] if len(cols) > 2 else '',
                            'owner_name': cols[4].text.strip()[:50] if len(cols) > 4 else 'Congress Member',
                            'Title': 'Congress Member',
                            'transaction_type': 'P',
                            'Value': cols[5].text.strip() if len(cols) > 5 else '0',
                            'source': 'congress'
                        })
                except:
                    continue

        print(f"  OK {len(trades)} trades de Congress encontrados")
        return trades

    except Exception as e:
        print(f"  ! Congress scraping error: {e}")
        return []

# ============================================
# FILTERS - APLICAR ESTRATEGIAS
# ============================================

def apply_filters(trades_list):
    """Aplica filtros y retorna trades por estrategia"""
    results = {strategy: [] for strategy in STRATEGIES.keys()}

    if not trades_list:
        return results

    # Separar por fuente
    openinsider_trades = [t for t in trades_list if t.get('source') == 'openinsider']
    congress_trades = [t for t in trades_list if t.get('source') == 'congress']

    # Calcular clusters para OpenInsider
    ticker_counts = {}
    for trade in openinsider_trades:
        ticker = trade['ticker']
        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

    # Procesar OpenInsider trades
    for trade in openinsider_trades:
        ticker = trade['ticker']
        cluster_size = ticker_counts.get(ticker, 1)
        score = calculate_score(trade, cluster_size)

        # Parsear valor
        try:
            value_str = str(trade.get('Value', '0'))
            value = abs(float(value_str.replace('$', '').replace(',', '').replace('+', '').strip()))
        except:
            value = 0

        # Agregar metadata
        trade['score'] = score
        trade['cluster_size'] = cluster_size
        trade['value_numeric'] = value

        title = str(trade.get('Title', '')).upper()

        # === APLICAR FILTROS ===

        # Score >=60
        if score >= 60:
            results['score_60'].append(trade.copy())

        # Score >=70
        if score >= 70:
            results['score_70'].append(trade.copy())

        # Score >=80
        if score >= 80:
            results['score_80'].append(trade.copy())

        # CEO/CFO Any (>$50k)
        if ('CEO' in title or 'CFO' in title) and value >= 50000:
            results['ceo_any'].append(trade.copy())

        # Value >$500k
        if value >= 500000:
            results['value_500k'].append(trade.copy())

        # Cluster 2+
        if cluster_size >= 2:
            results['cluster_2'].append(trade.copy())

    # Procesar Congress trades
    for trade in congress_trades:
        trade['score'] = 75  # Score fijo para congress
        trade['cluster_size'] = 1
        try:
            value_str = str(trade.get('Value', '0'))
            # Congress reporta rangos como "$1,001 - $15,000"
            if '-' in value_str:
                # Tomar el valor maximo del rango
                parts = value_str.split('-')
                value_str = parts[-1]
            trade['value_numeric'] = abs(float(value_str.replace('$', '').replace(',', '').strip()))
        except:
            trade['value_numeric'] = 50000  # Default

        results['congress'].append(trade.copy())

    return results

# ============================================
# PRICE API
# ============================================

def get_price_fast(ticker):
    """Obtiene precio actual usando yfinance como fallback"""

    # Intentar Massive API primero
    if MASSIVE_API_KEY:
        url = f"{MASSIVE_BASE_URL}/stocks/{ticker}/quotes/latest"
        headers = {"Authorization": f"Bearer {MASSIVE_API_KEY}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                price = data.get('close') or data.get('price') or data.get('last')
                if price:
                    return float(price)
        except:
            pass

    # Fallback: usar Yahoo Finance API directa
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price = data['chart']['result'][0]['meta'].get('regularMarketPrice')
            if price:
                return float(price)
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
        print(f"    ! No price for {ticker}")
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
    try:
        cursor.execute("""
            INSERT INTO trades
            (strategy, ticker, company_name, owner_name, title, trade_date, detection_date,
             score, value, cluster_size, source, entry_price, current_price, last_updated, status, days_holding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0)
        """, (
            strategy,
            ticker,
            trade.get('company_name', ''),
            trade.get('owner_name', ''),
            trade.get('Title', ''),
            trade['trade_date'],
            datetime.now().strftime('%Y-%m-%d'),
            trade.get('score', 0),
            trade.get('value_numeric', 0),
            trade.get('cluster_size', 1),
            trade.get('source', 'openinsider'),
            price,
            price,
            datetime.now().strftime('%Y-%m-%d')
        ))

        trade_id = cursor.lastrowid

        # Registrar ejecucion
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

        print(f"    + BUY {ticker} x{shares} @ ${price:.2f} = ${cost:.2f}")
        return True

    except sqlite3.IntegrityError:
        # Trade ya existe
        conn.close()
        return False
    except Exception as e:
        print(f"    ! Error buying {ticker}: {e}")
        conn.close()
        return False

def execute_paper_sell(strategy, trade_row, reason):
    """Ejecuta venta simulada"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    trade_id = trade_row[0]
    ticker = trade_row[2]
    entry_price = trade_row[12]  # entry_price column

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

    # Registrar ejecucion
    cursor.execute("""
        INSERT INTO executions (strategy, trade_id, action, ticker, shares, price, commission)
        VALUES (?, ?, 'SELL', ?, ?, ?, ?)
    """, (strategy, trade_id, ticker, shares, price, COMMISSION))

    # Actualizar portfolio
    cursor.execute("SELECT cash, invested FROM portfolios WHERE strategy = ?", (strategy,))
    portfolio = cursor.fetchone()

    new_cash = portfolio[0] + revenue
    new_invested = max(0, portfolio[1] - (shares * entry_price))
    new_total = new_cash + new_invested

    win = 1 if return_pct > 0 else 0

    cursor.execute("""
        UPDATE portfolios
        SET cash = ?, invested = ?, total = ?,
            wins = wins + ?, losses = losses + ?,
            return_pct = ((? - ?) / ?) * 100,
            updated_at = ?
        WHERE strategy = ?
    """, (new_cash, new_invested, new_total, win, 1-win, new_total, INITIAL_CAPITAL, INITIAL_CAPITAL,
          datetime.now().strftime('%Y-%m-%d'), strategy))

    conn.commit()
    conn.close()

    emoji = "WIN" if return_pct > 0 else "LOSS"
    print(f"    - SELL {ticker} ({emoji}) {return_pct:+.1f}% | Reason: {reason}")

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
    if not portfolio_row:
        conn.close()
        return 0

    portfolio = {'cash': portfolio_row[0], 'invested': portfolio_row[1], 'total': portfolio_row[2]}

    # Count active positions
    cursor.execute("SELECT COUNT(*) FROM trades WHERE strategy = ? AND status = 'ACTIVE'", (strategy,))
    active_count = cursor.fetchone()[0]

    conn.close()

    # Add new trades (if space)
    max_positions = STRATEGIES[strategy]['max_positions']
    added = 0

    available_slots = max_positions - active_count
    if available_slots <= 0:
        return 0

    for trade in new_trades[:available_slots]:
        if execute_paper_buy(strategy, trade, portfolio):
            added += 1
            # Actualizar portfolio en memoria
            portfolio['cash'] -= (portfolio['cash'] * STRATEGIES[strategy]['position_size_pct'] / 100)
            time.sleep(2)  # Rate limit mas agresivo

    return added

def update_active_trades():
    """Actualiza precios y verifica exits para todos los trades activos"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, strategy, ticker, trade_date, entry_price, current_price, days_holding
        FROM trades
        WHERE status = 'ACTIVE'
    """)

    active_trades = cursor.fetchall()
    conn.close()

    print(f"\nActualizando {len(active_trades)} trades activos...")

    for trade_row in active_trades:
        trade_id = trade_row[0]
        strategy = trade_row[1]
        ticker = trade_row[2]
        entry_price = trade_row[4]
        days = (trade_row[6] or 0) + 1

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
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trades
                SET current_price = ?, return_pct = ?, days_holding = ?, last_updated = ?
                WHERE id = ?
            """, (current_price, return_pct, days, datetime.now().strftime('%Y-%m-%d'), trade_id))
            conn.commit()
            conn.close()

        time.sleep(1)  # Rate limit

def generate_daily_summary():
    """Genera resumen diario mejorado"""
    conn = sqlite3.connect(DB_PATH)

    # Obtener stats por estrategia
    summary_data = []
    for strategy_id, config in STRATEGIES.items():
        cursor = conn.cursor()

        # Portfolio stats
        cursor.execute("""
            SELECT trades_count, wins, losses, cash, total, return_pct
            FROM portfolios
            WHERE strategy = ?
        """, (strategy_id,))
        portfolio = cursor.fetchone()

        # Active trades
        cursor.execute("""
            SELECT COUNT(*), AVG(return_pct)
            FROM trades
            WHERE strategy = ? AND status = 'ACTIVE'
        """, (strategy_id,))
        active = cursor.fetchone()

        # Trades de hoy
        cursor.execute("""
            SELECT COUNT(*)
            FROM trades
            WHERE strategy = ? AND DATE(detection_date) = DATE('now')
        """, (strategy_id,))
        today = cursor.fetchone()

        if portfolio:
            win_rate = (portfolio[1] / portfolio[0] * 100) if portfolio[0] > 0 else 0
            summary_data.append({
                'id': strategy_id,
                'name': config['name'],
                'trades': portfolio[0],
                'wins': portfolio[1],
                'losses': portfolio[2],
                'win_rate': win_rate,
                'total': portfolio[4],
                'return_pct': portfolio[5] or 0,
                'active': active[0] if active else 0,
                'active_avg_return': active[1] if active and active[1] else 0,
                'today': today[0] if today else 0
            })

    conn.close()

    # Construir mensaje
    today_str = datetime.now().strftime('%Y-%m-%d')

    msg = f"""
<b>DAILY REPORT</b>
{today_str}

"""

    # Ordenar por return
    summary_data.sort(key=lambda x: x['return_pct'], reverse=True)

    for s in summary_data:
        if s['return_pct'] > 0:
            emoji = "+"
        elif s['return_pct'] < 0:
            emoji = ""
        else:
            emoji = " "

        # Indicador de actividad
        activity = ""
        if s['today'] > 0:
            activity = f" [+{s['today']} hoy]"

        msg += f"""<b>{s['name']}</b>{activity}
${s['total']:.0f} ({emoji}{s['return_pct']:.1f}%)
Trades: {s['trades']} | WR: {s['win_rate']:.0f}% | Activos: {s['active']}

"""

    # Agregar mejor y peor estrategia
    if summary_data:
        best = summary_data[0]
        worst = summary_data[-1]

        msg += f"""
<b>RESUMEN</b>
Mejor: {best['name']} ({best['return_pct']:+.1f}%)
Peor: {worst['name']} ({worst['return_pct']:+.1f}%)
"""

    send_telegram(msg)

def main():
    """Flujo principal"""
    print("=" * 60)
    print("FORWARD TESTING MONITOR v2.0")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Init DB
    init_database()

    # Scrape ambas fuentes
    openinsider_trades = scrape_openinsider()
    congress_trades = scrape_congress_trading()

    all_trades = openinsider_trades + congress_trades

    if not all_trades:
        print("\nNo trades found from any source")
        generate_daily_summary()
        return

    print(f"\nTotal: {len(all_trades)} trades ({len(openinsider_trades)} OpenInsider, {len(congress_trades)} Congress)")

    # Apply filters
    filtered = apply_filters(all_trades)

    print("\nTrades por estrategia:")
    for strategy, trades_list in filtered.items():
        print(f"  {STRATEGIES[strategy]['name']}: {len(trades_list)}")

    # Process each strategy
    print("\nProcesando estrategias...")
    total_added = 0
    for strategy, trades_list in filtered.items():
        if trades_list:
            added = process_strategy(strategy, trades_list)
            if added > 0:
                print(f"  {STRATEGIES[strategy]['name']}: +{added} nuevas posiciones")
                total_added += added

    print(f"\nTotal nuevas posiciones: {total_added}")

    # Update active trades
    update_active_trades()

    # Daily summary
    generate_daily_summary()

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

if __name__ == "__main__":
    main()
