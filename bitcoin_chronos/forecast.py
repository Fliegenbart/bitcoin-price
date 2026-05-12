from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from bitcoin_chronos.data import build_context_frame, merge_macro_covariates, parse_binance_klines
from bitcoin_chronos.macro import (
    BGEOMETRICS_M2_URL,
    BGEOMETRICS_SOURCE,
    MACRO_COVARIATE_COLUMNS,
    MACRO_SOURCE_URLS,
    fetch_macro_covariates,
)
from bitcoin_chronos.outputs import (
    forecast_summary,
    write_forecast_svg,
    write_report,
    write_summary_json,
)


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def utc_ms(value: str | None) -> int | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value, tz="UTC")
    return int(timestamp.timestamp() * 1000)


def download_binance_klines(
    symbol: str,
    interval: str,
    start: str,
    end: str | None = None,
    pause_seconds: float = 0.15,
) -> pd.DataFrame:
    start_ms = utc_ms(start)
    end_ms = utc_ms(end)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_rows: list[list[Any]] = []

    while True:
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": 1000,
            "startTime": start_ms,
        }
        if end_ms is not None:
            params["endTime"] = end_ms

        response = requests.get(BINANCE_KLINES_URL, params=params, timeout=30)
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break

        all_rows.extend(rows)
        next_start_ms = int(rows[-1][6]) + 1
        if len(rows) < 1000 or next_start_ms <= start_ms:
            break
        start_ms = next_start_ms
        time.sleep(pause_seconds)

    complete_rows = [row for row in all_rows if int(row[6]) < now_ms]
    return parse_binance_klines(complete_rows)


def parse_quantiles(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def selected_macro_covariates(raw: str, enabled: bool) -> list[str]:
    if not enabled or raw.strip().lower() == "none":
        return []
    if raw.strip().lower() == "all":
        return MACRO_COVARIATE_COLUMNS.copy()
    requested = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [column for column in requested if column not in MACRO_COVARIATE_COLUMNS]
    if unknown:
        raise ValueError(f"Unknown macro covariate columns: {', '.join(unknown)}")
    return requested


def selected_m2_covariates(raw: str, enabled: bool) -> list[str]:
    return selected_macro_covariates(raw, enabled)


def normalize_forecast_frame(predictions: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.reset_index() if not isinstance(predictions.index, pd.RangeIndex) else predictions.copy()
    if "item_id" in frame.columns and "id" not in frame.columns:
        frame = frame.rename(columns={"item_id": "id"})
    if "timestamp" not in frame.columns:
        raise ValueError(f"Forecast output has no timestamp column. Columns: {list(frame.columns)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame.sort_values("timestamp").reset_index(drop=True)


def run_forecast(args: argparse.Namespace) -> Path:
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

    from chronos import Chronos2Pipeline

    history = download_binance_klines(
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
    )
    if len(history) < args.min_history:
        raise ValueError(f"Only {len(history)} completed candles found; need at least {args.min_history}.")

    output_dir = args.output_dir or Path("outputs") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_covariates = args.m2_covariate_columns or args.macro_covariate_columns
    covariate_columns = selected_macro_covariates(raw_covariates, args.macro_covariates and args.m2_covariates)
    macro = pd.DataFrame()
    if covariate_columns:
        macro = fetch_macro_covariates()
        macro.to_csv(output_dir / "macro_covariates_raw.csv", index=False)
        history = merge_macro_covariates(
            history,
            macro,
            required=covariate_columns,
            drop_incomplete_start=True,
        )
        history[["timestamp", *[column for column in MACRO_COVARIATE_COLUMNS if column in history.columns]]].to_csv(
            output_dir / "macro_covariates_aligned.csv",
            index=False,
        )

    context = build_context_frame(
        history,
        item_id=args.symbol.upper(),
        covariate_columns=covariate_columns,
    )
    history.to_csv(output_dir / "history.csv", index=False)
    history.tail(365)[["timestamp", "close"]].to_csv(output_dir / "history_tail.csv", index=False)
    context.to_csv(output_dir / "chronos_context.csv", index=False)

    pipeline = Chronos2Pipeline.from_pretrained(args.model, device_map=args.device)
    predictions = pipeline.predict_df(
        context,
        prediction_length=args.prediction_length,
        quantile_levels=parse_quantiles(args.quantiles),
        id_column="id",
        timestamp_column="timestamp",
        target="close",
    )

    forecast = normalize_forecast_frame(predictions)
    forecast.to_csv(output_dir / "forecast.csv", index=False)

    summary = forecast_summary(forecast)
    summary.update(
        {
            "symbol": args.symbol.upper(),
            "interval": args.interval,
            "model": args.model,
            "device": args.device,
            "history_rows": int(len(history)),
            "history_start": pd.Timestamp(history.iloc[0]["timestamp"]).isoformat(),
            "history_end": pd.Timestamp(history.iloc[-1]["timestamp"]).isoformat(),
            "last_observed_close": float(history.iloc[-1]["close"]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "covariates": covariate_columns,
        }
    )
    if covariate_columns:
        latest_macro_values = {
            column: float(history.iloc[-1][column])
            for column in MACRO_COVARIATE_COLUMNS
            if column in history.columns and pd.notna(history.iloc[-1][column])
        }
        summary.update(
            {
                "macro_source": BGEOMETRICS_SOURCE,
                "macro_source_url": BGEOMETRICS_M2_URL,
                "macro_sources": MACRO_SOURCE_URLS,
                "macro_rows": int(len(macro)),
                "macro_last_timestamp": pd.Timestamp(macro.iloc[-1]["timestamp"]).isoformat(),
                "macro_aligned_start": pd.Timestamp(history.iloc[0]["timestamp"]).isoformat(),
                "macro_aligned_end": pd.Timestamp(history.iloc[-1]["timestamp"]).isoformat(),
                "macro_latest_values": latest_macro_values,
                **{f"{column}_last": value for column, value in latest_macro_values.items()},
            }
        )
    write_summary_json(summary, output_dir / "summary.json")
    write_report(summary, output_dir / "report.md")
    write_forecast_svg(history, forecast, output_dir / "forecast.svg")
    write_forecast_svg(history, forecast, output_dir / "forecast_log.svg", y_scale="log")

    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zero-shot Bitcoin forecasts with Chronos-2.")
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance symbol, e.g. BTCUSDT.")
    parser.add_argument("--interval", default="1d", help="Binance interval, e.g. 1d, 4h, 1h.")
    parser.add_argument("--start", default="2017-08-17", help="UTC start date for historical candles.")
    parser.add_argument("--end", default=None, help="Optional UTC end date.")
    parser.add_argument("--prediction-length", type=int, default=90, help="Forecast horizon in interval steps.")
    parser.add_argument("--quantiles", default="0.1,0.5,0.9", help="Comma-separated quantile levels.")
    parser.add_argument("--model", default="amazon/chronos-2", help="Hugging Face model id.")
    parser.add_argument("--device", default="cpu", help="Use cpu by default; use cuda only when GPU is free.")
    parser.add_argument("--min-history", type=int, default=128, help="Minimum completed candles required.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for CSV, JSON, report, and SVG.")
    parser.add_argument(
        "--no-m2-covariates",
        action="store_false",
        dest="m2_covariates",
        help="Backward-compatible alias to disable macro covariates.",
    )
    parser.add_argument(
        "--m2-covariate-columns",
        default=None,
        help="Backward-compatible comma-separated macro covariates to pass to Chronos-2, or 'none'.",
    )
    parser.add_argument(
        "--no-macro-covariates",
        action="store_false",
        dest="macro_covariates",
        help="Disable all macro covariates.",
    )
    parser.add_argument(
        "--macro-covariate-columns",
        default="all",
        help="Comma-separated macro covariates to pass to Chronos-2, 'all', or 'none'.",
    )
    parser.set_defaults(m2_covariates=True)
    parser.set_defaults(macro_covariates=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output_dir = run_forecast(args)
    except Exception as exc:
        print(f"Forecast failed: {exc}", file=sys.stderr)
        return 1
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
