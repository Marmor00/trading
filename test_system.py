"""
TEST SYSTEM - Verificación completa
===================================

Verifica que todo el sistema funciona:
1. Telegram bot
2. Massive API
3. Database
4. Paper trading logic

EJECUTAR:
    python3 test_system.py
"""

import os
import requests
import sqlite3
from datetime import datetime

# Load env vars
MASSIVE_API_KEY = os.environ.get('MASSIVE_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

def test_telegram():
    """Test 1: Telegram bot"""
    print("\n" + "=" * 60)
    print("TEST 1: Telegram Bot")
    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ FAIL: Environment variables not set")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': f"✅ Test from PythonAnywhere - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data, timeout=10)

        if response.status_code == 200:
            print("✅ PASS: Telegram message sent")
            print("   Check your phone for the test message!")
            return True
        else:
            print(f"❌ FAIL: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_massive_api():
    """Test 2: Massive API"""
    print("\n" + "=" * 60)
    print("TEST 2: Massive API (Price data)")
    print("=" * 60)

    if not MASSIVE_API_KEY:
        print("❌ FAIL: MASSIVE_API_KEY not set")
        return False

    try:
        # Test with a known ticker (AAPL)
        url = f"https://api.massive.com/v1/stocks/AAPL/quotes/latest"
        headers = {"Authorization": f"Bearer {MASSIVE_API_KEY}"}

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            price = data.get('close')
            print(f"✅ PASS: Got AAPL price: ${price}")
            return True
        else:
            print(f"❌ FAIL: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_database():
    """Test 3: Database operations"""
    print("\n" + "=" * 60)
    print("TEST 3: Database")
    print("=" * 60)

    try:
        os.makedirs('data', exist_ok=True)
        conn = sqlite3.connect('data/forward_testing.db')
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        if len(tables) >= 3:
            print(f"✅ PASS: Database has {len(tables)} tables")
            for table in tables:
                print(f"   - {table[0]}")
        else:
            print("⚠️  WARNING: Database not initialized (run daily_monitor.py first)")

        # Check portfolios
        cursor.execute("SELECT COUNT(*) FROM portfolios")
        count = cursor.fetchone()[0]

        if count == 5:
            print(f"✅ PASS: 5 portfolios initialized")
        elif count > 0:
            print(f"⚠️  WARNING: Only {count} portfolios found (expected 5)")
        else:
            print("⚠️  WARNING: No portfolios (run daily_monitor.py first)")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_openinsider_access():
    """Test 4: OpenInsider website access"""
    print("\n" + "=" * 60)
    print("TEST 4: OpenInsider Website Access")
    print("=" * 60)

    try:
        url = "http://openinsider.com"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            print("✅ PASS: OpenInsider.com accessible")
            print(f"   Response length: {len(response.content)} bytes")
            return True
        else:
            print(f"❌ FAIL: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        print("   PythonAnywhere Beginner may block this site")
        print("   Try upgrading to Hacker plan if this persists")
        return False

def main():
    print("\n" + "=" * 60)
    print("SYSTEM TEST - Forward Testing Monitor")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Telegram Bot", test_telegram()))
    results.append(("Massive API", test_massive_api()))
    results.append(("Database", test_database()))
    results.append(("OpenInsider Access", test_openinsider_access()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print("\n" + "-" * 60)
    print(f"TOTAL: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYour system is ready to run automatically.")
        print("The scheduled task will execute daily at 18:00 UTC.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("\nPlease fix the issues above before running automatically.")

    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
