# Bitcoin Chronos-2 Forecast

This project runs a zero-shot Bitcoin price forecast with Chronos-2.

In simple terms:

1. It downloads completed BTCUSDT candles from Binance.
2. It gives the historical close prices to Chronos-2.
3. Chronos-2 returns a future price path with uncertainty bands.
4. The run writes CSV files, a JSON summary, a Markdown report, and an SVG chart.

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

## Outputs

Each run creates a folder under `outputs/` with:

- `history.csv`: downloaded historical candles
- `chronos_context.csv`: exact input passed into Chronos-2
- `forecast.csv`: predicted future prices and quantiles
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

## Test

```bash
python3 -m unittest discover
```
