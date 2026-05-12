from __future__ import annotations

import json
import math
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


def _optional_column(frame: pd.DataFrame, *candidates: object) -> object | None:
    for column in candidates:
        if column in frame.columns:
            return column
    return None


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
    covariates = ""
    if summary.get("covariates"):
        covariates = "\n\n## Macro covariates\n\n"
        covariates += f"- Columns: {', '.join(summary['covariates'])}\n"
        if summary.get("macro_source"):
            covariates += f"- Source: {summary['macro_source']}\n"

    report = f"""# Bitcoin Chronos-2 Forecast

- Horizon steps: {summary['horizon_steps']}
- First forecast timestamp: {summary['first_timestamp']}
- Last forecast timestamp: {summary['last_timestamp']}
- First point forecast: {summary['first_point']:,.2f}
- Last point forecast: {summary['last_point']:,.2f}{low_high}
{covariates}

This is a model forecast, not financial advice. Bitcoin can move sharply for reasons that are not visible in the historical price curve.
"""
    path.write_text(report, encoding="utf-8")


def write_forecast_svg(history: pd.DataFrame, forecast: pd.DataFrame, path: Path, y_scale: str = "linear") -> None:
    if y_scale not in {"linear", "log"}:
        raise ValueError("y_scale must be 'linear' or 'log'")

    point_column = point_forecast_column(forecast)
    low_column = _optional_column(forecast, "0.1", 0.1)
    high_column = _optional_column(forecast, "0.9", 0.9)
    history_tail = history.tail(365).copy()
    history_tail["timestamp"] = pd.to_datetime(history_tail["timestamp"], utc=True).dt.tz_localize(None)
    history_tail["kind"] = "history"
    history_tail["value"] = history_tail["close"].astype(float)

    forecast_points = forecast[["timestamp", point_column]].copy()
    forecast_points["timestamp"] = pd.to_datetime(forecast_points["timestamp"], utc=True).dt.tz_localize(None)
    forecast_points["kind"] = "forecast"
    forecast_points["value"] = forecast_points[point_column].astype(float)

    corridor_points = pd.DataFrame()
    if low_column is not None and high_column is not None:
        corridor_points = forecast[["timestamp", low_column, high_column]].copy()
        corridor_points["timestamp"] = pd.to_datetime(corridor_points["timestamp"], utc=True).dt.tz_localize(None)
        corridor_points["low"] = corridor_points[low_column].astype(float)
        corridor_points["high"] = corridor_points[high_column].astype(float)

    value_frames = [
        history_tail[["timestamp", "kind", "value"]],
        forecast_points[["timestamp", "kind", "value"]],
    ]
    if not corridor_points.empty:
        value_frames.extend(
            [
                corridor_points[["timestamp", "low"]].rename(columns={"low": "value"}).assign(kind="corridor"),
                corridor_points[["timestamp", "high"]].rename(columns={"high": "value"}).assign(kind="corridor"),
            ]
        )
    combined = pd.concat(value_frames, ignore_index=True).sort_values("timestamp")

    min_value = float(combined["value"].min())
    max_value = float(combined["value"].max())
    if min_value == max_value:
        min_value *= 0.95
        max_value *= 1.05
    if y_scale == "log" and min_value <= 0:
        raise ValueError("Log scale requires all chart values to be positive")

    timestamps = pd.to_datetime(combined["timestamp"])
    min_ts = timestamps.min()
    max_ts = timestamps.max()
    total_seconds = max((max_ts - min_ts).total_seconds(), 1.0)

    width = 1100
    height = 620
    left = 80
    right = 40
    top = 72
    bottom = 115
    plot_width = width - left - right
    plot_height = height - top - bottom
    axis_y = height - bottom

    def scale_value(value: float) -> float:
        return math.log10(value) if y_scale == "log" else value

    min_scaled_value = scale_value(min_value)
    max_scaled_value = scale_value(max_value)

    def xy(ts: pd.Timestamp, value: float) -> tuple[float, float]:
        x = left + ((pd.Timestamp(ts) - min_ts).total_seconds() / total_seconds) * plot_width
        y = top + (1.0 - ((scale_value(value) - min_scaled_value) / (max_scaled_value - min_scaled_value))) * plot_height
        return x, y

    def path_for(kind: str) -> str:
        points = combined[combined["kind"] == kind]
        commands = []
        for idx, row in enumerate(points.itertuples(index=False)):
            x, y = xy(row.timestamp, row.value)
            commands.append(("M" if idx == 0 else "L") + f" {x:.1f} {y:.1f}")
        return " ".join(commands)

    def corridor_path() -> str:
        if corridor_points.empty:
            return ""
        ordered = corridor_points.sort_values("timestamp")
        upper = [xy(row.timestamp, row.high) for row in ordered.itertuples(index=False)]
        lower = [xy(row.timestamp, row.low) for row in reversed(list(ordered.itertuples(index=False)))]
        points = upper + lower
        commands = []
        for idx, (x, y) in enumerate(points):
            commands.append(("M" if idx == 0 else "L") + f" {x:.1f} {y:.1f}")
        return " ".join(commands) + " Z"

    y_ticks = []
    for i in range(5):
        if y_scale == "log":
            value = 10 ** (min_scaled_value + (max_scaled_value - min_scaled_value) * i / 4)
        else:
            value = min_value + (max_value - min_value) * i / 4
        _, y = xy(min_ts, value)
        y_ticks.append((value, y))

    x_ticks = []
    for i in range(6):
        fraction = i / 5
        tick_ts = min_ts + (max_ts - min_ts) * fraction
        x, _ = xy(tick_ts, min_value)
        x_ticks.append((tick_ts, x))

    forecast_start_ts = forecast_points["timestamp"].min()
    forecast_start_x, _ = xy(forecast_start_ts, min_value)

    title = "BTCUSDT Chronos-2 Forecast"
    subtitle_suffix = " | Y scale: log scale" if y_scale == "log" else ""
    last_history = float(history_tail.iloc[-1]["close"]) if not history_tail.empty else 0.0
    last_forecast = float(forecast_points.iloc[-1][point_column]) if not forecast_points.empty else 0.0

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" data-y-scale="{y_scale}" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="26" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">{escape(title)}</text>',
        f'<text x="{left}" y="50" font-family="Arial, sans-serif" font-size="13" fill="#4b5563">Last history close: {last_history:,.2f} | Last forecast: {last_forecast:,.2f}{subtitle_suffix}</text>',
    ]
    for value, y in y_ticks:
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        svg.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{value:,.0f}</text>')
    for tick_ts, x in x_ticks:
        svg.append(f'<line class="x-axis-grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{axis_y}" stroke="#f1f5f9" stroke-width="1"/>')
    svg.extend(
        [
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{axis_y}" stroke="#9ca3af" stroke-width="1"/>',
            f'<line x1="{left}" y1="{axis_y}" x2="{width - right}" y2="{axis_y}" stroke="#9ca3af" stroke-width="1"/>',
            *[
                f'<text class="x-axis-label" x="{x:.1f}" y="{axis_y + 25}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#6b7280">{pd.Timestamp(tick_ts).strftime("%Y-%m-%d")}</text>'
                for tick_ts, x in x_ticks
            ],
            f'<line id="forecast-start-line" x1="{forecast_start_x:.1f}" y1="{top}" x2="{forecast_start_x:.1f}" y2="{axis_y}" stroke="#111827" stroke-width="1.3" stroke-dasharray="5 6" opacity="0.42"/>',
            f'<text x="{forecast_start_x + 8:.1f}" y="{top + 15}" font-family="Arial, sans-serif" font-size="11" fill="#374151">forecast start</text>',
            f'<path id="probability-corridor" d="{corridor_path()}" fill="#dc2626" fill-opacity="0.13" stroke="none"/>'
            if not corridor_points.empty
            else "",
            f'<path d="{path_for("history")}" fill="none" stroke="#2563eb" stroke-width="2.2"/>',
            f'<path d="{path_for("forecast")}" fill="none" stroke="#dc2626" stroke-width="2.4" stroke-dasharray="8 5"/>',
            f'<circle cx="{left + 8}" cy="{height - 34}" r="5" fill="#2563eb"/><text x="{left + 20}" y="{height - 30}" font-family="Arial, sans-serif" font-size="13" fill="#374151">history</text>',
            f'<circle cx="{left + 98}" cy="{height - 34}" r="5" fill="#dc2626"/><text x="{left + 110}" y="{height - 30}" font-family="Arial, sans-serif" font-size="13" fill="#374151">forecast</text>',
            f'<rect x="{left + 185}" y="{height - 39}" width="22" height="10" rx="2" fill="#dc2626" fill-opacity="0.18"/><text x="{left + 216}" y="{height - 30}" font-family="Arial, sans-serif" font-size="13" fill="#374151">10-90% probability corridor</text>'
            if not corridor_points.empty
            else "",
            "</svg>",
        ]
    )
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")
