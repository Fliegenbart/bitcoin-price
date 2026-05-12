from __future__ import annotations

import math
from typing import Iterable, Sequence

import pandas as pd


BINANCE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]


def parse_binance_klines(rows: Iterable[Sequence[object]]) -> pd.DataFrame:
    """Convert raw Binance kline rows to a clean OHLCV dataframe."""
    frame = pd.DataFrame(list(rows), columns=BINANCE_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(frame["open_time"], unit="ms", utc=True),
            "open": pd.to_numeric(frame["open"], errors="coerce"),
            "high": pd.to_numeric(frame["high"], errors="coerce"),
            "low": pd.to_numeric(frame["low"], errors="coerce"),
            "close": pd.to_numeric(frame["close"], errors="coerce"),
            "volume": pd.to_numeric(frame["volume"], errors="coerce"),
        }
    )
    out = out.dropna(subset=["timestamp", "close"]).drop_duplicates(subset=["timestamp"])
    return out.sort_values("timestamp").reset_index(drop=True)


def build_context_frame(
    history: pd.DataFrame,
    item_id: str,
    covariate_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Build the pandas format expected by Chronos2Pipeline.predict_df."""
    covariate_columns = covariate_columns or []
    columns = ["timestamp", "close", *covariate_columns]
    context = history[columns].copy()
    context["timestamp"] = pd.to_datetime(context["timestamp"], utc=True).dt.tz_localize(None)
    context.insert(0, "id", item_id)
    return context[["id", "timestamp", "close", *covariate_columns]]


def merge_macro_covariates(
    history: pd.DataFrame,
    macro: pd.DataFrame,
    required: list[str] | None = None,
    drop_incomplete_start: bool = False,
) -> pd.DataFrame:
    """Attach latest known macro covariates to each historical BTC candle."""
    history_sorted = history.copy()
    history_sorted["timestamp"] = pd.to_datetime(history_sorted["timestamp"], utc=True)
    history_sorted = history_sorted.sort_values("timestamp")

    macro_sorted = macro.copy()
    macro_sorted["timestamp"] = pd.to_datetime(macro_sorted["timestamp"], utc=True)
    macro_sorted = macro_sorted.sort_values("timestamp")

    merged = pd.merge_asof(
        history_sorted,
        macro_sorted,
        on="timestamp",
        direction="backward",
    )
    required = required or [column for column in macro_sorted.columns if column != "timestamp"]
    if merged[required].isna().any().any():
        if not drop_incomplete_start:
            raise ValueError("Macro covariates do not cover the full Bitcoin history.")
        merged = merged.dropna(subset=required)
        if merged.empty:
            raise ValueError("Macro covariates do not overlap with Bitcoin history.")
    return merged.reset_index(drop=True)


def attach_power_law_covariate(
    history: pd.DataFrame,
    origin: pd.Timestamp | str = "2009-01-03",
    column: str = "btc_power_law_price_usd",
) -> pd.DataFrame:
    """Fit log(price) against log(days since origin) and attach the fitted trend."""
    frame = history.copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    closes = pd.to_numeric(frame["close"], errors="coerce")

    origin_ts = pd.Timestamp(origin)
    origin_ts = origin_ts.tz_localize("UTC") if origin_ts.tzinfo is None else origin_ts.tz_convert("UTC")
    days = (timestamps - origin_ts).dt.total_seconds() / 86_400
    valid = (days > 0) & (closes > 0)
    if int(valid.sum()) < 2:
        raise ValueError("Power-law covariate needs at least two positive price points after the origin.")

    x_values = [math.log(float(value)) for value in days[valid]]
    y_values = [math.log(float(value)) for value in closes[valid]]
    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(y_values) / len(y_values)
    denominator = sum((value - mean_x) ** 2 for value in x_values)
    if denominator == 0:
        raise ValueError("Power-law covariate needs at least two distinct timestamps.")

    slope = sum((x_value - mean_x) * (y_value - mean_y) for x_value, y_value in zip(x_values, y_values)) / denominator
    intercept = mean_y - slope * mean_x
    frame[column] = [math.exp(intercept + slope * math.log(float(day))) if day > 0 else pd.NA for day in days]
    return frame


def interval_to_pandas_freq(interval: str) -> str:
    if interval.endswith("m"):
        return f"{int(interval[:-1])}min"
    if interval.endswith("h"):
        hours = int(interval[:-1])
        return "h" if hours == 1 else f"{hours}h"
    if interval.endswith("d"):
        days = int(interval[:-1])
        return "D" if days == 1 else f"{days}D"
    if interval.endswith("w"):
        weeks = int(interval[:-1])
        return "W" if weeks == 1 else f"{weeks}W"
    raise ValueError(f"Unsupported interval: {interval}")


def interval_to_milliseconds(interval: str) -> int:
    if interval.endswith("m"):
        return int(interval[:-1]) * 60_000
    if interval.endswith("h"):
        return int(interval[:-1]) * 60 * 60_000
    if interval.endswith("d"):
        return int(interval[:-1]) * 24 * 60 * 60_000
    if interval.endswith("w"):
        return int(interval[:-1]) * 7 * 24 * 60 * 60_000
    raise ValueError(f"Unsupported interval: {interval}")
