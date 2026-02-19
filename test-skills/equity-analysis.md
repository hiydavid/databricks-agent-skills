# Equity Analysis Use Case

## Business Context

We are the equity research team at a mid-size wealth management firm. Our analysts cover ~200 public companies across multiple sectors. Today, producing a single equity research report takes an analyst 3-5 days — most of that time is spent gathering data, reading filings, and synthesizing information before the actual analysis begins.

We want to build an agentic system that, given a stock ticker (e.g., `AAPL`, `NVDA`, `JPM`), produces a comprehensive equity analysis report with a buy/hold/sell recommendation. The system should replicate what a senior analyst does, but compress the data gathering and initial analysis from days to minutes.

## Users

- **Equity research analysts**: Use the report as a starting point, then layer in their own judgment and client context before publishing
- **Portfolio managers**: Use the output for quick screening and position sizing decisions
- **Compliance team**: Reviews the report for accuracy and regulatory adherence before external distribution

## Data Sources

### Structured Data (Databricks — Unity Catalog)

All financial data lives in Databricks Unity Catalog with the following tables:

- `finance.fundamentals.income_statements` — Revenue, COGS, operating income, net income, EPS (quarterly + annual, last 10 years)
- `finance.fundamentals.balance_sheets` — Assets, liabilities, equity, debt levels, working capital (quarterly + annual)
- `finance.fundamentals.cashflow_statements` — Operating/investing/financing cash flows, free cash flow, capex

All tables are keyed by `ticker` and `year`.

There is a genie space create on top of these 3 tables

### Unstructured Data (Databricks — Vector Search)

SEC filings are ingested, chunked, and stored in a Databricks Vector Search index:

- `finance.documents.sec_filings_index` — 10-K (annual), earnings call transcripts
- Each chunk includes metadata: `ticker`, `filing_type`, `filing_date`, `section` (e.g., "Risk Factors", "MD&A", "Business Overview")
- Retrieval via Databricks Vector Search endpoint `vs_endpoint_sec_filings`

### External Data (Web Search)

- Latest news about the company (earnings announcements, management changes, product launches, lawsuits)
- Macroeconomic context (Fed policy, sector trends, regulatory changes)
- Competitor developments that impact the company's outlook
- Social sentiment and analyst commentary

## Input

- **Stock ticker** (required): e.g., `NVDA`
- **Analysis depth** (optional): "quick screen" (2-page summary) or "full coverage" (10+ page deep dive, default)
- **Focus areas** (optional): e.g., "focus on AI revenue growth" or "evaluate debt refinancing risk"

## Expected Output

A structured equity analysis report (`equity-report-{ticker}-{date}.md`) containing:

1. **Company Overview** — Business description, key products/segments, competitive position
2. **Financial Analysis**
   - Revenue trends and growth drivers (3-5 year view)
   - Profitability analysis (margins, operating leverage)
   - Balance sheet health (leverage, liquidity, debt maturity)
   - Cash flow analysis (FCF generation, capital allocation)
3. **Valuation**
   - Relative valuation (P/E, EV/EBITDA vs peers)
   - DCF or comparable analysis with key assumptions stated
   - Historical valuation range
4. **Risk Assessment**
   - Key risks from 10-K Risk Factors (extracted and summarized)
   - Macro/sector risks relevant to this company
   - Recent 8-K material events that change the risk profile
5. **Catalyst Analysis** — Upcoming events that could move the stock (earnings, product launches, regulatory decisions)
6. **News & Sentiment Synthesis** — Summary of recent news, analyst commentary, and market sentiment
7. **Recommendation** — Buy/Hold/Sell with price target, time horizon, and confidence level
8. **Supporting Data Tables** — Key financial metrics, peer comparison table, historical price chart data

## Constraints

- **Latency**: Full report in under 5 minutes. Quick screen in under 1 minute.
- **Accuracy is critical**: Financial numbers must come directly from the database — never hallucinated. Every claim should be traceable to a data source (filing section, table query, or news article).
- **Compliance**: The report must clearly label what is data-derived vs. AI-generated analysis. All SEC filing citations must include filing date and section.

## Existing Infrastructure

- Databricks workspace with Unity Catalog, SQL warehouses, genie space and Vector Search endpoints already provisioned
- Python SDK (`databricks-sdk`) available for programmatic access
- Web search available via API (Tavily, Brave Search, or similar)
