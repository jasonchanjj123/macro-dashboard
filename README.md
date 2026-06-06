# Macroeconomic Dashboard 全球總經儀表板

<img width="941" height="482" alt="Screenshot 2026-06-06 113924" src="https://github.com/user-attachments/assets/b3f7b21c-4e43-4bdc-bf40-6c33a65a828e" />

<img width="938" height="393" alt="Screenshot 2026-06-06 113957" src="https://github.com/user-attachments/assets/c7ef39c4-dca6-498c-9a5c-997db8dfd99a" />


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
