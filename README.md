# Bitcoin Chronos-2 Forecast

This project runs a multivariate zero-shot Bitcoin price forecast with Chronos-2.

In simple terms:

1. It downloads completed BTCUSDT candles from Binance.
2. It downloads BGeometrics Global M2 data.
3. It gives BTC close prices plus Global M2 Supply and M2 Growth YoY to Chronos-2.
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
Use `--no-m2-covariates` if you want a price-only baseline run.
Use `--m2-covariate-columns m2_global_supply_usd` or `--m2-covariate-columns m2_growth_yoy_pct`
to run a one-variable ablation.

## Outputs

Each run creates a folder under `outputs/` with:

- `history.csv`: downloaded historical candles
- `chronos_context.csv`: exact input passed into Chronos-2
- `forecast.csv`: predicted future prices and quantiles
- `macro_covariates_raw.csv`: decoded BGeometrics M2 series
- `macro_covariates_aligned.csv`: daily M2 covariates aligned to BTC candles
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
It also includes four covariate scenarios under `data/latest/scenarios`:

- price only
- M2 Supply only
- M2 Growth YoY only
- M2 Supply + M2 Growth YoY

## Macro Data Source

Global M2 covariates come from the public BGeometrics chart:

- `M2 Global Supply (USD)`
- `M2 Growth YoY (%)`

BGeometrics describes this as an aggregate from 21 central banks. Treat it as a macro liquidity proxy, not as a single official central-bank data release.

## Test

```bash
python3 -m unittest discover
```
