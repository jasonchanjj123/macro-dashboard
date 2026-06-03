# Macroeconomic Dashboard 全球總經儀表板

Automated macro dashboard that scrapes economic indicators from MacroMicro and sovereign CDS data from Investing.com, outputs a static HTML site deployable to Vercel / GitHub Pages.

## Data Sources

| Section | Source |
|---------|--------|
| KEY INDICATORS (US) | MacroMicro — top_charts |
| MARKET INDICATORS (Fed, Bonds, Stocks, Commodities) | MacroMicro — paged_instants |
| RECENT FOCUS DATA | MacroMicro — paged_focus_stats |
| WORLD STOCK INDICES (EU, JP, TW, CN, HK, BR, IN) | MacroMicro — macro country pages |
| THEMATIC INDICATORS (Recession, Spreads, Volatility, Sentiment) | MacroMicro — trader-insights |
| CDS (US, UK, France, Japan, China, Italy, Spain, Mexico, Brazil, Indonesia, Turkey) | Investing.com — individual CDS pages |

## Usage

```
pip install -r requirements.txt
python scrape_macromicro.py
```

### Output files:

- `index.html` — static dashboard
- `dashboard_data.json` — structured data
- `top_charts.csv` — chart metadata
- `series_last_rows.json` — raw series data

## Deploy

Static site — just point Vercel / GitHub Pages to the project root.
