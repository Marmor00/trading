"""
OpenInsider.com scraper - extracts insider trading purchases.
"""

import requests
from datetime import datetime
from bs4 import BeautifulSoup


def scrape_openinsider():
    """Scrape recent insider purchases from OpenInsider.

    Returns list of dicts with keys:
        trade_date, ticker, company_name, owner_name, Title,
        transaction_type, Value
    """
    url = (
        "http://openinsider.com/screener?"
        "s=&o=&pl=&ph=&ll=&lh=&fd=14&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago="
        "&xp=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0"
        "&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h="
        "&sortcol=0&cnt=500&page=1"
    )

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
            except Exception:
                continue

        print(f"  OK {len(trades)} purchases found")
        return trades
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def calculate_score(row, cluster_size=1):
    """Calculate insider trading score (0-100) for a trade."""
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
    except Exception:
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
    except Exception:
        pass

    return score


def enrich_trades(trades_list):
    """Add score, cluster_size, and value_numeric to each trade."""
    if not trades_list:
        return trades_list

    # Count tickers for cluster detection
    ticker_counts = {}
    for t in trades_list:
        ticker_counts[t['ticker']] = ticker_counts.get(t['ticker'], 0) + 1

    for trade in trades_list:
        cluster_size = ticker_counts.get(trade['ticker'], 1)
        score = calculate_score(trade, cluster_size)

        try:
            val_str = str(trade.get('Value', '0'))
            value = abs(float(val_str.replace('$', '').replace(',', '').replace('+', '').strip()))
        except Exception:
            value = 0

        trade['score'] = score
        trade['cluster_size'] = cluster_size
        trade['value_numeric'] = value

    return trades_list
