"""
Discounted Cash Flow (DCF) Model


- Free Cash Flow = Cash company generates after reinvestment (OCF + CapEx)
- PV = FV / (1+r)^n  |  NPV = Σ CF_n / (1+r)^n  |  DCF = discounting future cash → today's value
- Terminal Value using WACC (Gordon growth)
- Enterprise Value = DCF + TV
- Equity Value = Enterprise Value – Net Debt
- Price = Equity Value / Outstanding Shares
"""

from typing import Any

import numpy as np


def compute_free_cash_flow(
    operating_cf: list[tuple[int, float]],
    capex: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    """
    Free Cash Flow = Cash company generates after reinvestment.
    FCF = Operating Cash Flow + CapEx (CapEx is typically negative).
    Aligns by fiscal year.
    """
    op_dict = dict(operating_cf)
    capex_dict = dict(capex)
    years = sorted(set(op_dict.keys()) & set(capex_dict.keys()), reverse=True)
    if not years:
        # Use OCF only if no capex
        return operating_cf[:10]
    return [(y, op_dict[y] + capex_dict.get(y, 0)) for y in years]


def project_fcf(
    historical_fcf: list[tuple[int, float]],
    historical_revenue: list[tuple[int, float]],
    revenue_growth_rate: float,
    fcf_margin: float,
    projection_years: int = 5,
) -> list[tuple[int, float]]:
    """
    Project FCF using revenue growth and target FCF margin.
    Base year is last historical year; revenue grows at rate, FCF = revenue * margin.
    """
    if not historical_revenue or not historical_fcf:
        return []

    last_year = historical_revenue[0][0]
    last_revenue = historical_revenue[0][1]

    # Use historical FCF margin if not provided
    if fcf_margin is None or fcf_margin <= 0:
        fcf_dict = dict(historical_fcf)
        rev_dict = dict(historical_revenue)
        margins = [
            fcf_dict[y] / rev_dict[y]
            for y in fcf_dict
            if y in rev_dict and rev_dict[y] != 0
        ]
        fcf_margin = np.median(margins) if margins else 0.15

    projections = []
    rev = last_revenue
    for i in range(1, projection_years + 1):
        rev *= 1 + revenue_growth_rate
        yr = last_year + i
        fcf = rev * fcf_margin
        projections.append((yr, fcf))

    return projections


def terminal_value(
    last_fcf: float,
    perpetuity_growth: float,
    wacc: float,
) -> float:
    """Terminal Value using WACC. Gordon growth: TV = FCF_{n+1} / (WACC - g)."""
    if wacc <= perpetuity_growth:
        raise ValueError("WACC must be greater than perpetuity growth rate")
    fcf_next = last_fcf * (1 + perpetuity_growth)
    return fcf_next / (wacc - perpetuity_growth)


def npv(cash_flows: list[tuple[int, float]], wacc: float, base_year: int) -> float:
    """NPV = Σ CF_n / (1+r)^n. Discount future cash flows to today (base_year)."""
    return sum(
        cf / (1 + wacc) ** (yr - base_year)
        for yr, cf in cash_flows
    )


def run_dcf(
    financials: dict[str, Any],
    revenue_growth: float = 0.10,
    perpetuity_growth: float = 0.025,
    wacc: float = 0.09,
    fcf_margin: float | None = None,
    projection_years: int = 5,
) -> dict[str, Any]:
    """
    Run full DCF valuation.

    Args:
        financials: Output from get_financials_for_dcf()
        revenue_growth: Annual revenue growth rate (e.g. 0.10 = 10%)
        perpetuity_growth: Terminal perpetual growth rate (e.g. 0.025 = 2.5%)
        wacc: Weighted average cost of capital (e.g. 0.09 = 9%)
        fcf_margin: Target FCF/Revenue margin; if None, uses historical median
        projection_years: Years to project explicitly

    Returns:
        Dict with enterprise_value, equity_value, per_share_value, and details
    """
    # Historical FCF
    fcf_hist = compute_free_cash_flow(
        financials.get("operating_cf", []),
        financials.get("capex", []),
    )

    if not fcf_hist:
        fcf_hist = [(yr, ni) for yr, ni in financials.get("net_income", [])]
        # Rough approximation: FCF ~ Net Income * 1.1 (simplified)
        fcf_hist = [(y, v * 1.0) for y, v in fcf_hist]

    rev_hist = financials.get("revenue", [])
    if not rev_hist:
        raise ValueError("No revenue data available for DCF")

    # Project FCF
    fcf_proj = project_fcf(
        fcf_hist,
        rev_hist,
        revenue_growth,
        fcf_margin,
        projection_years,
    )

    if not fcf_proj:
        raise ValueError("Could not project FCF")

    base_year = rev_hist[0][0]
    last_proj_year, last_fcf = fcf_proj[-1]

    # Terminal Value using WACC
    tv = terminal_value(last_fcf, perpetuity_growth, wacc)
    tv_year = last_proj_year + 1

    # Add DCF + TV = Enterprise Value (future), discounted to today
    npv_explicit = npv(fcf_proj, wacc, base_year)
    npv_tv = tv / (1 + wacc) ** (tv_year - base_year)
    enterprise_value = npv_explicit + npv_tv

    # Equity Value = Enterprise Value – Net Debt
    cash = financials.get("cash", [])
    debt = financials.get("debt", [])
    cash_val = cash[0][1] if cash else 0
    debt_val = debt[0][1] if debt else 0
    net_debt = debt_val - cash_val
    equity_value = enterprise_value - net_debt

    # Price = Equity Value / Outstanding Shares
    shares = financials.get("shares", [])
    shares_out = shares[0][1] if shares else None
    per_share = equity_value / shares_out if shares_out and shares_out > 0 else None

    return {
        "company": financials.get("company", "Unknown"),
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "per_share_value": per_share,
        "net_debt": net_debt,
        "shares_outstanding": shares_out,
        "terminal_value": tv,
        "npv_explicit_period": npv_explicit,
        "npv_terminal": npv_tv,
        "assumptions": {
            "revenue_growth": revenue_growth,
            "perpetuity_growth": perpetuity_growth,
            "wacc": wacc,
            "projection_years": projection_years,
        },
        "projected_fcf": fcf_proj,
        "historical_fcf": fcf_hist[:5],
    }
