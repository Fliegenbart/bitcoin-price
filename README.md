# Bitcoin Chronos-2 Forecast

This project runs a multivariate zero-shot Bitcoin price forecast with Chronos-2.

In simple terms:

1. It downloads completed BTCUSDT candles from Binance.
2. It downloads liquidity, dollar, sentiment, and stablecoin covariates.
3. It gives BTC close prices plus the selected covariates to Chronos-2.
4. Chronos-2 returns a future price path with uncertainty bands.
5. The run writes CSV files, a JSON summary, a Markdown report, and an SVG chart.

This is not financial advice. It is a model experiment, and Bitcoin can move for reasons that are not visible in price history alone.

## Run On The Server

```bash
cd /root/bitcoin-chronos
TRANSFORMERS_NO_TF=1 USE_TF=0 python3 -m bitcoin_chronos.forecast \
  --symbol BTCUSDT \
  --interval 1d \
  --prediction-length 90 \
  --device cpu
```

Use `--device cuda` only when the GPU is free.
Use `--no-macro-covariates` if you want a price-only baseline run.
Use `--macro-covariate-columns column_a,column_b` to run a specific ablation.
The old `--no-m2-covariates` and `--m2-covariate-columns` flags still work as aliases.

## Outputs

Each run creates a folder under `outputs/` with:

- `history.csv`: downloaded historical candles
- `chronos_context.csv`: exact input passed into Chronos-2
- `forecast.csv`: predicted future prices and quantiles
- `macro_covariates_raw.csv`: combined macro source data
- `macro_covariates_aligned.csv`: daily macro covariates aligned to BTC candles
- `summary.json`: machine-readable result summary
- `report.md`: short human-readable report
- `forecast.svg`: simple chart of recent history plus forecast

## Web Dashboard

The repository also contains a static Vercel dashboard:

- `index.html`
- `styles.css`
- `app.js`
- `data/latest/*`

It shows the latest generated forecast from `data/latest`.
It also includes covariate scenarios under `data/latest/scenarios`:

- price only
- core macro only
- core macro + M2 Supply
- core macro + M2 Growth YoY
- core macro + both M2 inputs

## Macro Data Source

The dashboard currently uses these public macro proxies:

- `M2 Global Supply (USD)` and `M2 Growth YoY (%)` from BGeometrics.
- `G4 Global Liquidity` from BIS central-bank total-assets data for the US, euro area, Japan, and China.
- `Fed Net Liquidity` from FRED as Fed balance sheet minus Treasury General Account minus reverse repos.
- `DXY inverse` from Yahoo Finance's DXY history, transformed as `100 / DXY`.
- `Fear & Greed Index` from Alternative.me.
- `USDT mint/burn proxy` from DeFiLlama Tether circulating supply changes.

BGeometrics describes Global M2 as an aggregate from 21 central banks. The USDT values are supply-change proxies, not an official historical Tether Treasury event ledger. Treat all covariates as model inputs, not as proof that one driver causes Bitcoin's next move.

## Test

```bash
python3 -m unittest discover
```
