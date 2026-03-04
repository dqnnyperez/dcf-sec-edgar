"""
SEC EDGAR API Client for fetching financial data.
Uses official data.sec.gov APIs - no API key required.
SEC requires a descriptive User-Agent header.
"""

import json
import time
from typing import Any

import requests

SEC_BASE = "https://data.sec.gov"
HEADERS = {
    "User-Agent": "DCF Analysis Tool (contact@example.com)",
    "Accept": "application/json",
}


def get_ticker_to_cik() -> dict[str, dict]:
    """Fetch ticker to CIK mapping from SEC."""
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Keys are string indices, values have ticker, cik_str, title
    return {v["ticker"]: v for _, v in data.items()}


def pad_cik(cik: int | str) -> str:
    """Pad CIK to 10 digits as required by SEC API."""
    return str(cik).zfill(10)


def get_company_facts(cik: int | str) -> dict[str, Any]:
    """Fetch company facts (all XBRL data) for a given CIK."""
    cik_padded = pad_cik(cik)
    url = f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def extract_annual_values(
    facts: dict,
    concept: str,
    taxonomy: str = "us-gaap",
    unit_type: str = "USD",
) -> list[tuple[int, float]]:
    """
    Extract annual values for a concept. Returns list of (fiscal_year, value).
    Prefers instant (balance sheet) or duration (income/cash flow) as appropriate.
    """
    try:
        inner = facts.get("facts", facts)
        if taxonomy == "dei":
            data = inner.get("dei", {}).get(concept, {})
        else:
            data = inner.get(taxonomy, {}).get(concept, {})
    except (AttributeError, TypeError):
        return []

    if not data:
        return []

    unit_key = "shares" if unit_type == "shares" else unit_type
    units = data.get("units", {}).get(unit_key)
    if not units:
        # Try other unit types if primary not found
        for uk, uv in data.get("units", {}).items():
            if isinstance(uv, list) and uv:
                units = uv
                break
    if not units:
        return []

    results = []
    seen = set()
    # Prefer 10-K annual filings
    for item in sorted(units, key=lambda x: (x.get("fy") or 0, x.get("form") or ""), reverse=True):
        fy = item.get("fy")
        fp = item.get("fp", "")
        form = item.get("form", "")
        if fy and (fp or "").upper() == "FY" and form in ("10-K", "10-K/A", "20-F", "40-F"):
            key = fy
            if key in seen:
                continue
            seen.add(key)
            val = item.get("val")
            if val is not None:
                results.append((fy, float(val)))

    return sorted(results, key=lambda x: x[0], reverse=True)


def get_financials_for_dcf(cik: int | str) -> dict[str, Any]:
    """
    Extract DCF-relevant financials from company facts.
    Returns dict with revenue, net_income, operating_cf, capex, cash, debt, shares.
    """
    facts = get_company_facts(cik)
    time.sleep(0.2)  # Be respectful of SEC rate limits

    result: dict[str, Any] = {
        "company": facts.get("entityName", "Unknown"),
        "cik": facts.get("cik"),
        "revenue": [],
        "net_income": [],
        "operating_cf": [],
        "capex": [],
        "cash": [],
        "debt": [],
        "shares": [],
    }

    # Revenue - try common concepts
    for concept in (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "NetSalesRevenues",
        "SalesRevenueGoodsNet",
        "SalesRevenueNet",
    ):
        vals = extract_annual_values(facts, concept)
        if vals:
            result["revenue"] = vals[:10]  # Last 10 years
            break

    # Net Income
    for concept in ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"):
        vals = extract_annual_values(facts, concept)
        if vals:
            result["net_income"] = vals[:10]
            break

    # Operating Cash Flow
    for concept in (
        "NetCashProvidedByUsedInOperatingActivities",
        "CashProvidedByUsedInOperatingActivities",
    ):
        vals = extract_annual_values(facts, concept)
        if vals:
            result["operating_cf"] = vals[:10]
            break

    # CapEx (typically negative - spending)
    for concept in (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ):
        vals = extract_annual_values(facts, concept)
        if vals:
            # Payments are usually reported as positive; we subtract for FCF
            result["capex"] = [(y, -abs(v)) for y, v in vals[:10]]
            break

    # If capex not found, try Payments (reported as positive outflow)
    if not result["capex"]:
        for concept in ("PaymentsToAcquirePropertyPlantAndEquipment",):
            vals = extract_annual_values(facts, concept)
            if vals:
                result["capex"] = [(y, -abs(v)) for y, v in vals[:10]]
                break

    # Cash
    for concept in (
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
        "CashAndCashEquivalentsFairValueDisclosure",
    ):
        vals = extract_annual_values(facts, concept)
        if vals:
            result["cash"] = vals[:10]
            break

    # Debt (long-term)
    for concept in (
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "DebtCurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ):
        vals = extract_annual_values(facts, concept)
        if vals:
            result["debt"] = vals[:10]
            break

    # Shares outstanding: use most recent data including 10-Q for split-adjusted recency
    # Try dei:EntityCommonStockSharesOutstanding first, then us-gaap:CommonStockSharesOutstanding
    inner = facts.get("facts", facts)
    shares_data: list[tuple[str, int, float]] = []  # (end_date, fy, val)

    for taxonomy, concept in (
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ):
        if taxonomy == "dei":
            data = inner.get("dei", {}).get(concept, {})
        else:
            data = inner.get("us-gaap", {}).get(concept, {})
        units = data.get("units", {}).get("shares", []) if data else []
        for u in units:
            if u.get("val") is None:
                continue
            form = (u.get("form") or "").upper()
            fy = u.get("fy")
            end = u.get("end") or ""
            # Accept 10-K, 20-F, 40-F (annual) and 10-Q (quarterly, more recent post-splits)
            if form not in ("10-K", "10-K/A", "20-F", "40-F", "10-Q"):
                continue
            val = float(u["val"])
            # XBRL decimals: -6 = millions, -3 = thousands; scale up if present
            dec = u.get("decimals")
            if dec is not None:
                try:
                    d = int(dec)
                    if d < 0:
                        val *= 10 ** (-d)
                except (TypeError, ValueError):
                    pass
            # Prefer later end date (most recent = post-split)
            end_key = end or (str(fy) if fy else "0000")
            shares_data.append((end_key, fy or 0, val))
        if shares_data:
            break

    if shares_data:
        # Sort by end date descending, then fy; take most recent per fiscal year
        shares_data.sort(key=lambda x: (x[0], x[1]), reverse=True)
        by_year: dict[int, float] = {}
        for _, fy, v in shares_data:
            if fy and fy not in by_year:
                by_year[fy] = v
        result["shares"] = sorted(by_year.items(), key=lambda x: x[0], reverse=True)[:10]

    return result
