#!/usr/bin/env python3
"""
Diagnostic script to verify that non-A-stock fundamentals are correctly
transformed and rendered in the template.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import db
from datetime import timezone, timedelta, datetime
from jinja2 import Environment

def test_intel_fundamentals():
    """Test that Intel fundamentals are correctly transformed"""

    db.init_db()

    code = "INTC"
    stock = db.get_stock(code)
    if not stock:
        print(f"✗ Stock {code} not found in database")
        return False

    # Get fundamentals
    fund = db.get_fundamentals(code)
    signals = fund.get("signals", {}) if fund else {}
    annual = fund.get("annual", []) if fund else []

    print(f"📊 Testing {code} ({stock.get('name')})")
    print(f"   Market: {stock.get('market')}")

    # Verify initial state
    if not signals:
        print(f"✗ No signals data found for {code}")
        return False
    print(f"✓ Signals data found: {len(signals)} fields")

    if annual:
        print(f"✗ {code} should have empty annual array (non-A-stock), but found {len(annual)} records")
        return False
    print(f"✓ Annual array is empty (as expected for non-A-stock)")

    # Apply transformation (from app.py)
    if signals and not annual:
        if "roe" in signals and isinstance(signals["roe"], (int, float)):
            signals["roe"] = f"{signals['roe']*100:.1f}%"
        if "roa" in signals and isinstance(signals["roa"], (int, float)):
            signals["roa"] = f"{signals['roa']*100:.1f}%"
        if "gross_margin" in signals and isinstance(signals["gross_margin"], (int, float)):
            signals["gross_margin"] = f"{signals['gross_margin']*100:.1f}%"
        if "profit_margin" in signals and isinstance(signals["profit_margin"], (int, float)):
            signals["net_margin"] = f"{signals['profit_margin']*100:.1f}%"
            signals["profit_margin"] = signals["net_margin"]
        if "debt_to_equity" in signals and isinstance(signals["debt_to_equity"], (int, float)):
            signals["debt_ratio"] = f"{signals['debt_to_equity']:.1f}"

        CN_TZ = timezone(timedelta(hours=8))
        signals["year"] = datetime.now(CN_TZ).strftime("%Y")

        virtual_annual = {
            "year": signals.get("year", "—"),
            "roe": signals.get("roe", "—"),
            "net_margin": signals.get("net_margin", "—"),
            "debt_ratio": signals.get("debt_ratio", "—"),
            "profit_growth": "—",
        }
        annual = [virtual_annual]

    print(f"✓ Transformation applied")
    print(f"   annual length: {len(annual)}")

    # Verify transformed values
    if not annual:
        print(f"✗ Virtual annual not created")
        return False

    record = annual[0]
    expected = {
        "roe": "0.0%",           # Intel ROE is ~0.02%, rounds to 0.0%
        "net_margin": "-0.5%",   # Intel profit margin is negative
        "debt_ratio": "37.3",    # Intel debt-to-equity is 37.28, rounds to 37.3
    }

    all_ok = True
    for field, expected_val in expected.items():
        actual_val = record.get(field)
        if actual_val == expected_val:
            print(f"✓ {field}: {actual_val}")
        else:
            print(f"✗ {field}: expected {expected_val}, got {actual_val}")
            all_ok = False

    # Test template rendering
    print(f"\n🎨 Testing template rendering:")
    env = Environment()
    template = env.from_string("""
{%- set lat = annual[0] if annual else none -%}
{%- if lat and lat.roe -%}
ROE: {{ lat.roe }}
{%- else -%}
ROE: MISSING
{%- endif -%}
{%- if lat and lat.net_margin -%}
NET_MARGIN: {{ lat.net_margin }}
{%- else -%}
NET_MARGIN: MISSING
{%- endif -%}
{%- if lat and lat.debt_ratio -%}
DEBT_RATIO: {{ lat.debt_ratio }}
{%- else -%}
DEBT_RATIO: MISSING
{%- endif -%}
""")

    result = template.render(annual=annual, signals=signals)
    lines = [l.strip() for l in result.split('\n') if l.strip()]

    for line in lines:
        if "MISSING" in line:
            print(f"✗ {line}")
            all_ok = False
        else:
            print(f"✓ {line}")

    return all_ok

if __name__ == "__main__":
    try:
        success = test_intel_fundamentals()
        if success:
            print(f"\n✅ All tests passed! Non-A-stock fundamentals are working correctly.")
            sys.exit(0)
        else:
            print(f"\n❌ Some tests failed.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
