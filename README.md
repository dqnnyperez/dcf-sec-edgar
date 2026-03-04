# Automated DCF from SEC EDGAR

Fetches financial data from the SEC EDGAR API and runs a Discounted Cash Flow (DCF) valuation. Uses the official [data.sec.gov](https://data.sec.gov) APIs — no API key required.

## Setup

```bash
cd dcf-sec-edgar
pip install -r requirements.txt
```

**Note:** The SEC requires a descriptive User-Agent. Update the `User-Agent` in `sec_edgar_client.py` with your email for production use.

## Usage

```bash
# Basic usage (Apple, default assumptions)
python dcf_main.py AAPL

# Custom assumptions
python dcf_main.py MSFT --growth 0.12 --wacc 0.085 --perpetuity 0.03

# 10-year explicit projection
python dcf_main.py GOOGL --years 10

# Raw JSON output
python dcf_main.py AAPL --json
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `ticker` | (required) | Stock ticker (e.g., AAPL, MSFT) |
| `--growth` | 0.10 | Revenue growth rate (10%) |
| `--perpetuity` | 0.025 | Terminal growth (2.5%) |
| `--wacc` | 0.09 | Discount rate (9%) |
| `--years` | 5 | Explicit projection years |
| `--json` | false | Output raw JSON |

## Data Sources

- **Company Facts API** (`/api/xbrl/companyfacts/CIK{id}.json`) — XBRL financial data from 10-K, 10-Q
- **Company Tickers** (`/files/company_tickers.json`) — Ticker to CIK mapping

## DCF Methodology 

1. **Free Cash Flow** = Cash company generates after reinvestment = Operating CF + CapEx
2. **PV / NPV** = CF / (1+r)^n ; DCF = discount future cash → today's value
3. **Terminal Value** = using WACC (Gordon growth): FCF × (1+g) / (WACC − g)
4. **Enterprise Value** = DCF + TV (discounted to today)
5. **Equity Value** = Enterprise Value − Net Debt
6. **Price** = Equity Value / Outstanding Shares

## Limitations

- Relies on reported XBRL concepts; some companies use different tags
- Bank/insurance companies may need different models
- Assumptions (growth, WACC) are inputs — adjust based on your analysis
- **Shares**: Uses most recent SEC filing (10-K, 10-Q) for split-adjusted counts. Growth stocks often trade above DCF value; try `--growth 0.15 --wacc 0.07` for higher intrinsic value.
