from __future__ import annotations

import base64
import json
import re
import zlib
from typing import Any

import pandas as pd


BGEOMETRICS_M2_URL = "https://charts.bgeometrics.com/graphics/m2_global.html"
BGEOMETRICS_SOURCE = "BGeometrics M2 Growth Global YoY chart"
MACRO_COVARIATE_COLUMNS = ["m2_global_supply_usd", "m2_growth_yoy_pct"]


def decode_bgeometrics_series(encoded: str) -> list[list[float]]:
    raw = base64.b64decode(encoded)
    return json.loads(zlib.decompress(raw).decode("utf-8"))


def _extract_decoder_payloads(html: str) -> dict[str, str]:
    return dict(re.findall(r'const\s+(\w+)\s*=\s*decoder\("([^"]+)"\)', html))


def _extract_series_variable(html: str, series_name: str) -> str:
    pattern = rf"id:\s*'{re.escape(series_name)}'[\s\S]*?data:\s*(\w+)"
    match = re.search(pattern, html)
    if not match:
        raise ValueError(f"Could not find BGeometrics series variable for {series_name!r}.")
    return match.group(1)


def extract_bgeometrics_macro_series(html: str) -> dict[str, list[list[float]]]:
    payloads = _extract_decoder_payloads(html)
    series: dict[str, list[list[float]]] = {}
    for label in ("M2 Global Supply (USD)", "M2 Growth YoY (%)"):
        variable = _extract_series_variable(html, label)
        if variable not in payloads:
            raise ValueError(f"Found series {label!r}, but decoder payload {variable!r} is missing.")
        series[label] = decode_bgeometrics_series(payloads[variable])
    return series


def _series_frame(points: list[list[Any]], column: str) -> pd.DataFrame:
    frame = pd.DataFrame(points, columns=["timestamp", column])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["timestamp", column]).sort_values("timestamp")


def normalize_bgeometrics_macro(series: dict[str, list[list[float]]]) -> pd.DataFrame:
    supply = _series_frame(series["M2 Global Supply (USD)"], "m2_global_supply_usd")
    growth = _series_frame(series["M2 Growth YoY (%)"], "m2_growth_yoy_pct")
    merged = pd.merge(supply, growth, on="timestamp", how="inner")
    return merged.sort_values("timestamp").reset_index(drop=True)


def fetch_bgeometrics_macro(url: str = BGEOMETRICS_M2_URL) -> pd.DataFrame:
    import requests

    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "bitcoin-chronos/1.0"},
    )
    response.raise_for_status()
    return normalize_bgeometrics_macro(extract_bgeometrics_macro_series(response.text))
