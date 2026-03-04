"""
Congress trading data source.

Scrapes Capitol Trades (https://www.capitoltrades.com) for recent
stock purchases by U.S. Congress members (House + Senate).

Free, no API key required. Data comes from public STOCK Act filings.
"""

import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


def fetch_congress_trades(days_back=60):
    """Fetch recent congress member stock purchases.

    Returns list of dicts with keys:
        ticker, representative, transaction_date, amount_range,
        asset_description, owner, min_value
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching Congress trades from Capitol Trades...")

    purchases = []

    # Scrape first 3 pages of buy transactions
    for page in range(1, 4):
        page_trades = _scrape_page(page)
        if not page_trades:
            break
        purchases.extend(page_trades)

    # Filter by date
    cutoff = datetime.now() - timedelta(days=days_back)
    recent = []
    for trade in purchases:
        try:
            tx_date = datetime.strptime(trade['transaction_date'], '%Y-%m-%d')
            if tx_date >= cutoff:
                recent.append(trade)
        except (ValueError, TypeError):
            continue

    print(f"  OK {len(recent)} congress purchases in last {days_back} days")
    return recent


def _scrape_page(page):
    """Scrape a single page of buy transactions from Capitol Trades."""
    url = f"https://www.capitoltrades.com/trades?txType=buy&page={page}"
    try:
        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=20)

        if resp.status_code != 200:
            print(f"  ! Capitol Trades page {page} returned {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.content, 'html.parser')
        table = soup.find('table')
        if not table:
            return []

        rows = table.find_all('tr')[1:]  # skip header
        trades = []

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 9:
                continue

            try:
                # Parse politician name and party
                politician_text = cells[0].get_text(strip=True)

                # Parse ticker from "Traded Issuer" column (e.g. "Abbott LaboratoriesABT:US")
                issuer_text = cells[1].get_text(strip=True)
                ticker = _extract_ticker(issuer_text)
                if not ticker:
                    continue

                company_name = _extract_company(issuer_text)

                # Parse traded date (e.g. "29 Jan2026")
                traded_text = cells[3].get_text(strip=True)
                tx_date = _parse_date(traded_text)
                if not tx_date:
                    continue

                # Owner
                owner = cells[5].get_text(strip=True)

                # Size (e.g. "1K–15K", "250K–500K")
                size_text = cells[7].get_text(strip=True)
                min_value = _parse_size(size_text)

                # Price
                price_text = cells[8].get_text(strip=True)

                trades.append({
                    'ticker': ticker,
                    'representative': _clean_politician_name(politician_text),
                    'transaction_date': tx_date,
                    'amount_range': size_text,
                    'min_value': min_value,
                    'asset_description': company_name,
                    'owner': owner,
                    'price': price_text,
                })

            except Exception:
                continue

        return trades

    except Exception as e:
        print(f"  ERROR scraping Capitol Trades page {page}: {e}")
        return []


def _extract_ticker(issuer_text):
    """Extract ticker from issuer text like 'Abbott LaboratoriesABT:US'."""
    # Look for pattern like 'XXX:US' or 'XXXX:US'
    match = re.search(r'([A-Z]{1,5}):US', issuer_text)
    if match:
        return match.group(1)
    return None


def _extract_company(issuer_text):
    """Extract company name from issuer text."""
    match = re.search(r'([A-Z]{1,5}):US', issuer_text)
    if match:
        return issuer_text[:match.start()].strip()
    return issuer_text[:40]


def _clean_politician_name(text):
    """Extract politician name from text like 'Thomas Kean JrRepublicanHouseNJ'."""
    # Remove party/chamber/state suffixes
    for party in ['Republican', 'Democrat', 'Independent']:
        idx = text.find(party)
        if idx > 0:
            return text[:idx].strip()
    return text[:30].strip()


def _parse_date(date_text):
    """Parse date like '29 Jan2026' or '7 Jan2026' to 'YYYY-MM-DD'."""
    # Clean up: "29 Jan2026" -> "29 Jan 2026"
    cleaned = re.sub(r'(\w{3})(\d{4})', r'\1 \2', date_text)
    try:
        dt = datetime.strptime(cleaned.strip(), '%d %b %Y')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        return None


def _parse_size(size_text):
    """Parse size like '1K–15K' or '250K–500K' to minimum value in dollars."""
    # Replace various dash types and clean
    cleaned = size_text.replace('–', '-').replace('—', '-').replace('\u2013', '-')
    # Extract first number
    match = re.search(r'([\d.]+)\s*([KMB]?)', cleaned)
    if not match:
        return 0

    num = float(match.group(1))
    multiplier = match.group(2)
    if multiplier == 'K':
        return num * 1000
    elif multiplier == 'M':
        return num * 1000000
    elif multiplier == 'B':
        return num * 1000000000
    return num
