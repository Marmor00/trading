"""
Telegram notification service.
"""

import os
import requests


TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


def send_telegram(message):
    """Send a message via Telegram bot. Returns True on success."""
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


def send_telegram_long(message):
    """Send a long message, splitting into chunks if needed (Telegram 4096 char limit)."""
    if len(message) <= 4000:
        return send_telegram(message)

    chunks = []
    current = ""
    for line in message.split('\n'):
        if len(current) + len(line) + 1 > 3900:
            chunks.append(current)
            current = line
        else:
            current += ('\n' if current else '') + line
    if current:
        chunks.append(current)

    success = True
    for chunk in chunks:
        if not send_telegram(chunk):
            success = False
    return success
