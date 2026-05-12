from __future__ import annotations

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


def merge_macro_covariates(history: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
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
    required = ["m2_global_supply_usd", "m2_growth_yoy_pct"]
    if merged[required].isna().any().any():
        raise ValueError("Macro covariates do not cover the full Bitcoin history.")
    return merged.reset_index(drop=True)


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
