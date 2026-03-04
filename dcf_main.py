#!/usr/bin/env python3
"""
Automated DCF Statement using SEC EDGAR API

Fetches financial data from SEC EDGAR (company facts) and runs a DCF valuation.
Usage:
  python dcf_main.py              # prompts for ticker (cin-style)
  python dcf_main.py AAPL
  python dcf_main.py MSFT --growth 0.12 --wacc 0.085
"""

import argparse
import json

from sec_edgar_client import get_financials_for_dcf, get_ticker_to_cik
from dcf_model import run_dcf


def format_currency(val: float) -> str:
    """Format large numbers as billions."""
    if abs(val) >= 1e12:
        return f"${val/1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"${val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.2f}"


def main():
    parser = argparse.ArgumentParser(
        description="Automated DCF valuation using SEC EDGAR data"
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="Stock ticker symbol (e.g., AAPL, MSFT) or CIK number (e.g., 320193 for Apple)",
    )
    parser.add_argument(
        "--growth",
        type=float,
        default=0.10,
        help="Revenue growth rate (default: 0.10 = 10%%)",
    )
    parser.add_argument(
        "--perpetuity",
        type=float,
        default=0.025,
        help="Terminal perpetuity growth (default: 0.025 = 2.5%%)",
    )
    parser.add_argument(
        "--wacc",
        type=float,
        default=0.09,
        help="WACC discount rate (default: 0.09 = 9%%)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Explicit projection years (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Use sample data (no SEC API call) to verify the pipeline",
    )
    args = parser.parse_args()

    if args.ticker is None:
        ticker = input("Enter ticker symbol: ").strip().upper()
        if not ticker:
            print("No ticker provided.")
            return 1
    else:
        ticker = args.ticker.upper()

    if args.test:
        # Sample Apple-like data to verify DCF works without network
        financials = {
            "company": "Apple Inc. (sample)",
            "revenue": [(2024, 383_285e6), (2023, 383_583e6), (2022, 394_328e6)],
            "net_income": [(2024, 97_000e6), (2023, 96_995e6), (2022, 99_803e6)],
            "operating_cf": [(2024, 110_543e6), (2023, 99_584e6), (2022, 122_151e6)],
            "capex": [(2024, -10_669e6), (2023, -10_159e6), (2022, -10_707e6)],
            "cash": [(2024, 61_555e6), (2023, 61_555e6)],
            "debt": [(2024, 92_628e6), (2023, 97_733e6)],
            "shares": [(2024, 15_456_889_000), (2023, 15_550_117_000)],
        }
        print("Using sample data (--test mode)...")
    else:
        # Resolve ticker to CIK (or use CIK directly if numeric)
        print(f"Fetching SEC data for {ticker}...")
        if ticker.isdigit():
            cik = ticker
            company_name = ticker
        else:
            try:
                tickers = get_ticker_to_cik()
            except Exception as e:
                print(f"Error fetching ticker list: {e}")
                return 1

            if ticker not in tickers:
                print(f"Ticker {ticker} not found in SEC registry.")
                return 1

            cik = tickers[ticker]["cik_str"]
            company_name = tickers[ticker].get("title", ticker)

        # Fetch financials
        try:
            financials = get_financials_for_dcf(cik)
        except Exception as e:
            print(f"Error fetching company facts: {e}")
            return 1

    if not financials.get("revenue"):
        print("No revenue data found. Company may use non-standard reporting.")
        return 1

    # Run DCF
    try:
        result = run_dcf(
            financials,
            revenue_growth=args.growth,
            perpetuity_growth=args.perpetuity,
            wacc=args.wacc,
            projection_years=args.years,
        )
    except Exception as e:
        print(f"DCF valuation error: {e}")
        return 1

    if args.json:
        # Convert for JSON serialization
        out = {**result}
        out["projected_fcf"] = [list(x) for x in result["projected_fcf"]]
        out["historical_fcf"] = [list(x) for x in result["historical_fcf"]]
        print(json.dumps(out, indent=2))
        return 0

    # Formatted report
    print()
    print("=" * 60)
    print(f"  DCF VALUATION: {result['company']} ({ticker})")
    print("=" * 60)
    print()
    print("  VALUATION SUMMARY")
    print("  " + "-" * 40)
    print(f"  Enterprise Value:    {format_currency(result['enterprise_value'])}")
    print(f"  Net Debt:           {format_currency(result['net_debt'])}")
    print(f"  Equity Value:       {format_currency(result['equity_value'])}")
    if result.get("per_share_value"):
        print(f"  Value per Share:     ${result['per_share_value']:.2f}")
    print()
    print("  ASSUMPTIONS")
    print("  " + "-" * 40)
    a = result["assumptions"]
    print(f"  Revenue Growth:      {a['revenue_growth']*100:.1f}%")
    print(f"  Perpetuity Growth:   {a['perpetuity_growth']*100:.1f}%")
    print(f"  WACC:                {a['wacc']*100:.1f}%")
    print(f"  Projection Years:    {a['projection_years']}")
    print()
    print("  PROJECTED FREE CASH FLOW")
    print("  " + "-" * 40)
    for yr, fcf in result["projected_fcf"]:
        print(f"  {yr}:  {format_currency(fcf)}")
    print(f"  Terminal Value (TV): {format_currency(result['terminal_value'])}")
    print()
    print("  HISTORICAL FCF (recent)")
    print("  " + "-" * 40)
    for yr, fcf in result["historical_fcf"]:
        print(f"  {yr}:  {format_currency(fcf)}")
    print()
    return 0


if __name__ == "__main__":
    exit(main())
