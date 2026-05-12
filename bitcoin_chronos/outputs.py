from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import pandas as pd


def point_forecast_column(forecast: pd.DataFrame) -> object:
    for column in ("predictions", "mean", "0.5", 0.5):
        if column in forecast.columns:
            return column
    raise ValueError("Forecast has no point forecast column such as predictions, mean, or 0.5")


def _optional_float(row: pd.Series, column: str) -> float | None:
    if column not in row.index:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    return float(value)


def forecast_summary(forecast: pd.DataFrame) -> dict[str, Any]:
    if forecast.empty:
        raise ValueError("Forecast is empty")

    point_column = point_forecast_column(forecast)
    ordered = forecast.sort_values("timestamp").reset_index(drop=True)
    first = ordered.iloc[0]
    last = ordered.iloc[-1]

    return {
        "point_column": str(point_column),
        "horizon_steps": int(len(ordered)),
        "first_timestamp": pd.Timestamp(first["timestamp"]).isoformat(),
        "last_timestamp": pd.Timestamp(last["timestamp"]).isoformat(),
        "first_point": float(first[point_column]),
        "last_point": float(last[point_column]),
        "last_low": _optional_float(last, "0.1"),
        "last_high": _optional_float(last, "0.9"),
    }


def write_summary_json(summary: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report(summary: dict[str, Any], path: Path) -> None:
    low_high = ""
    if summary.get("last_low") is not None and summary.get("last_high") is not None:
        low_high = f"\n- Last 10-90% range: {summary['last_low']:,.2f} - {summary['last_high']:,.2f}"

    report = f"""# Bitcoin Chronos-2 Forecast

- Horizon steps: {summary['horizon_steps']}
- First forecast timestamp: {summary['first_timestamp']}
- Last forecast timestamp: {summary['last_timestamp']}
- First point forecast: {summary['first_point']:,.2f}
- Last point forecast: {summary['last_point']:,.2f}{low_high}

This is a model forecast, not financial advice. Bitcoin can move sharply for reasons that are not visible in the historical price curve.
"""
    path.write_text(report, encoding="utf-8")


def write_forecast_svg(history: pd.DataFrame, forecast: pd.DataFrame, path: Path) -> None:
    point_column = point_forecast_column(forecast)
    history_tail = history.tail(365).copy()
    history_tail["timestamp"] = pd.to_datetime(history_tail["timestamp"], utc=True).dt.tz_localize(None)
    history_tail["kind"] = "history"
    history_tail["value"] = history_tail["close"].astype(float)

    forecast_points = forecast[["timestamp", point_column]].copy()
    forecast_points["timestamp"] = pd.to_datetime(forecast_points["timestamp"], utc=True).dt.tz_localize(None)
    forecast_points["kind"] = "forecast"
    forecast_points["value"] = forecast_points[point_column].astype(float)

    combined = pd.concat(
        [
            history_tail[["timestamp", "kind", "value"]],
            forecast_points[["timestamp", "kind", "value"]],
        ],
        ignore_index=True,
    ).sort_values("timestamp")

    min_value = float(combined["value"].min())
    max_value = float(combined["value"].max())
    if min_value == max_value:
        min_value *= 0.95
        max_value *= 1.05

    timestamps = pd.to_datetime(combined["timestamp"])
    min_ts = timestamps.min()
    max_ts = timestamps.max()
    total_seconds = max((max_ts - min_ts).total_seconds(), 1.0)

    width = 1100
    height = 560
    left = 80
    right = 40
    top = 40
    bottom = 70
    plot_width = width - left - right
    plot_height = height - top - bottom

    def xy(ts: pd.Timestamp, value: float) -> tuple[float, float]:
        x = left + ((pd.Timestamp(ts) - min_ts).total_seconds() / total_seconds) * plot_width
        y = top + (1.0 - ((value - min_value) / (max_value - min_value))) * plot_height
        return x, y

    def path_for(kind: str) -> str:
        points = combined[combined["kind"] == kind]
        commands = []
        for idx, row in enumerate(points.itertuples(index=False)):
            x, y = xy(row.timestamp, row.value)
            commands.append(("M" if idx == 0 else "L") + f" {x:.1f} {y:.1f}")
        return " ".join(commands)

    y_ticks = []
    for i in range(5):
        value = min_value + (max_value - min_value) * i / 4
        _, y = xy(min_ts, value)
        y_ticks.append((value, y))

    title = "BTCUSDT Chronos-2 Forecast"
    last_history = float(history_tail.iloc[-1]["close"]) if not history_tail.empty else 0.0
    last_forecast = float(forecast_points.iloc[-1][point_column]) if not forecast_points.empty else 0.0

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="26" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">{escape(title)}</text>',
        f'<text x="{left}" y="50" font-family="Arial, sans-serif" font-size="13" fill="#4b5563">Last history close: {last_history:,.2f} | Last forecast: {last_forecast:,.2f}</text>',
    ]
    for value, y in y_ticks:
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        svg.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{value:,.0f}</text>')
    svg.extend(
        [
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#9ca3af" stroke-width="1"/>',
            f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#9ca3af" stroke-width="1"/>',
            f'<path d="{path_for("history")}" fill="none" stroke="#2563eb" stroke-width="2.2"/>',
            f'<path d="{path_for("forecast")}" fill="none" stroke="#dc2626" stroke-width="2.4" stroke-dasharray="8 5"/>',
            f'<circle cx="{left + 8}" cy="{height - 34}" r="5" fill="#2563eb"/><text x="{left + 20}" y="{height - 30}" font-family="Arial, sans-serif" font-size="13" fill="#374151">history</text>',
            f'<circle cx="{left + 98}" cy="{height - 34}" r="5" fill="#dc2626"/><text x="{left + 110}" y="{height - 30}" font-family="Arial, sans-serif" font-size="13" fill="#374151">forecast</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")
