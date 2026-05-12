from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import zipfile
import zlib
from typing import Any

import pandas as pd


BGEOMETRICS_M2_URL = "https://charts.bgeometrics.com/graphics/m2_global.html"
BGEOMETRICS_SOURCE = "BGeometrics M2 Growth Global YoY chart"
BIS_CBTA_BULK_URL = "https://data.bis.org/static/bulk/WS_CBTA_csv_flat.zip"
FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
YAHOO_DXY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
ALTERNATIVE_FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
DEFILLAMA_USDT_SUPPLY_URL = "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=1"

M2_COVARIATE_COLUMNS = ["m2_global_supply_usd", "m2_growth_yoy_pct"]
ADDITIONAL_COVARIATE_COLUMNS = [
    "g4_global_liquidity_usd",
    "fed_net_liquidity_usd",
    "dxy_inverse",
    "fear_greed_index",
    "usdt_supply_net_change_usd",
    "usdt_supply_mint_proxy_usd",
    "usdt_supply_burn_proxy_usd",
]
POWER_LAW_COVARIATE_COLUMNS = ["btc_power_law_price_usd"]
EXTERNAL_MACRO_COVARIATE_COLUMNS = [*M2_COVARIATE_COLUMNS, *ADDITIONAL_COVARIATE_COLUMNS]
MACRO_COVARIATE_COLUMNS = [*EXTERNAL_MACRO_COVARIATE_COLUMNS, *POWER_LAW_COVARIATE_COLUMNS]
MACRO_SOURCE_URLS = {
    "m2_global_supply_usd": BGEOMETRICS_M2_URL,
    "m2_growth_yoy_pct": BGEOMETRICS_M2_URL,
    "g4_global_liquidity_usd": BIS_CBTA_BULK_URL,
    "fed_net_liquidity_usd": "https://fred.stlouisfed.org/",
    "dxy_inverse": "https://finance.yahoo.com/quote/DX-Y.NYB/history/",
    "fear_greed_index": "https://api.alternative.me/fng/",
    "usdt_supply_net_change_usd": DEFILLAMA_USDT_SUPPLY_URL,
    "usdt_supply_mint_proxy_usd": DEFILLAMA_USDT_SUPPLY_URL,
    "usdt_supply_burn_proxy_usd": DEFILLAMA_USDT_SUPPLY_URL,
}
G4_AREAS = {"US: United States", "XM: Euro area", "JP: Japan", "CN: China"}


def _download_text(url: str, timeout: int = 45, use_curl: bool = False) -> str:
    if use_curl:
        result = subprocess.run(
            ["curl", "-L", "--fail", "--max-time", str(timeout), "-s", url],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    import requests

    response = requests.get(url, timeout=timeout, headers={"User-Agent": "bitcoin-chronos/1.0"})
    response.raise_for_status()
    return response.text


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
    return normalize_bgeometrics_macro(extract_bgeometrics_macro_series(_download_text(url, timeout=30)))


def normalize_bis_g4_liquidity(frame: pd.DataFrame) -> pd.DataFrame:
    currency = frame["CURRENCY:Currency"] if "CURRENCY:Currency" in frame.columns else pd.Series("", index=frame.index)
    monthly_usd_assets = frame[
        (frame["FREQ:Frequency"] == "M: Monthly")
        & frame["REF_AREA:Reference area"].isin(G4_AREAS)
        & ((frame["UNIT_MEASURE:Unit of measure"] == "USD: US dollar") | (currency == "USD: US dollar"))
        & (frame["TRANSFORMATION:Transformation"] == "B: Adjusted for breaks")
    ].copy()
    monthly_usd_assets["timestamp"] = pd.to_datetime(
        monthly_usd_assets["TIME_PERIOD:Time period or range"],
        format="%Y-%m",
        utc=True,
    )
    monthly_usd_assets["value_usd"] = pd.to_numeric(
        monthly_usd_assets["OBS_VALUE:Observation Value"],
        errors="coerce",
    ) * 1_000_000_000
    monthly_usd_assets = monthly_usd_assets.dropna(subset=["timestamp", "value_usd"])
    pivot = (
        monthly_usd_assets.pivot_table(
            index="timestamp",
            columns="REF_AREA:Reference area",
            values="value_usd",
            aggfunc="last",
        )
        .sort_index()
        .ffill()
    )
    pivot = pivot.dropna(subset=sorted(G4_AREAS))
    out = pivot[sorted(G4_AREAS)].sum(axis=1).rename("g4_global_liquidity_usd").reset_index()
    return out.sort_values("timestamp").reset_index(drop=True)


def fetch_bis_g4_liquidity(url: str = BIS_CBTA_BULK_URL) -> pd.DataFrame:
    import requests

    response = requests.get(url, timeout=60, headers={"User-Agent": "bitcoin-chronos/1.0"})
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    name = archive.namelist()[0]
    columns = [
        "FREQ:Frequency",
        "REF_AREA:Reference area",
        "UNIT_MEASURE:Unit of measure",
        "CURRENCY:Currency",
        "TRANSFORMATION:Transformation",
        "TIME_PERIOD:Time period or range",
        "OBS_VALUE:Observation Value",
    ]
    return normalize_bis_g4_liquidity(pd.read_csv(archive.open(name), usecols=columns))


def fetch_fred_series(series_id: str) -> pd.DataFrame:
    csv_text = _download_text(FRED_GRAPH_URL.format(series_id=series_id), timeout=60, use_curl=True)
    frame = pd.read_csv(io.StringIO(csv_text))
    frame = frame.rename(columns={"observation_date": "timestamp", "DATE": "timestamp", series_id: series_id})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame[series_id] = pd.to_numeric(frame[series_id].replace(".", pd.NA), errors="coerce")
    return frame.dropna(subset=["timestamp", series_id]).sort_values("timestamp").reset_index(drop=True)


def normalize_fed_net_liquidity(series: dict[str, pd.DataFrame]) -> pd.DataFrame:
    walcl = series["WALCL"].copy()
    tga = series["WTREGEN"].copy()
    reverse_repo = series["RRPONTSYD"].copy()
    merged = pd.merge_asof(
        walcl.sort_values("timestamp"),
        tga.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )
    merged = pd.merge_asof(
        merged.sort_values("timestamp"),
        reverse_repo.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )
    merged["fed_net_liquidity_usd"] = (merged["WALCL"] - merged["WTREGEN"] - merged["RRPONTSYD"]) * 1_000_000
    return merged[["timestamp", "fed_net_liquidity_usd"]].dropna().sort_values("timestamp").reset_index(drop=True)


def fetch_fed_net_liquidity() -> pd.DataFrame:
    return normalize_fed_net_liquidity(
        {series_id: fetch_fred_series(series_id) for series_id in ("WALCL", "WTREGEN", "RRPONTSYD")}
    )


def normalize_dxy_inverse(payload: dict[str, Any]) -> pd.DataFrame:
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    frame = pd.DataFrame({"timestamp": timestamps, "dxy_close": closes})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
    frame["dxy_close"] = pd.to_numeric(frame["dxy_close"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "dxy_close"])
    frame["dxy_inverse"] = 100.0 / frame["dxy_close"]
    return frame[["timestamp", "dxy_inverse"]].sort_values("timestamp").reset_index(drop=True)


def fetch_dxy_inverse(url: str = YAHOO_DXY_URL) -> pd.DataFrame:
    full_url = f"{url}?period1=0&period2=2000000000&interval=1d&events=history&includeAdjustedClose=true"
    return normalize_dxy_inverse(json.loads(_download_text(full_url, timeout=45)))


def normalize_fear_greed(payload: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(payload["data"])
    frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame["timestamp"], errors="coerce"), unit="s", utc=True)
    frame["fear_greed_index"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame[["timestamp", "fear_greed_index"]].dropna().sort_values("timestamp").reset_index(drop=True)


def fetch_fear_greed(url: str = ALTERNATIVE_FNG_URL) -> pd.DataFrame:
    return normalize_fear_greed(json.loads(_download_text(url, timeout=30)))


def normalize_usdt_issuance_proxy(payload: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": pd.to_datetime(int(row["date"]), unit="s", utc=True),
            "usdt_supply_usd": float(row["totalCirculatingUSD"]["peggedUSD"]),
        }
        for row in payload
    ]
    frame = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    frame["usdt_supply_net_change_usd"] = frame["usdt_supply_usd"].diff().fillna(0.0)
    frame["usdt_supply_mint_proxy_usd"] = frame["usdt_supply_net_change_usd"].clip(lower=0.0)
    frame["usdt_supply_burn_proxy_usd"] = (-frame["usdt_supply_net_change_usd"]).clip(lower=0.0)
    return frame[
        [
            "timestamp",
            "usdt_supply_net_change_usd",
            "usdt_supply_mint_proxy_usd",
            "usdt_supply_burn_proxy_usd",
        ]
    ]


def fetch_usdt_issuance_proxy(url: str = DEFILLAMA_USDT_SUPPLY_URL) -> pd.DataFrame:
    return normalize_usdt_issuance_proxy(json.loads(_download_text(url, timeout=45)))


def combine_macro_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    merged = frames[0]
    for frame in frames[1:]:
        merged = pd.merge(merged, frame, on="timestamp", how="outer")
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    value_columns = [column for column in merged.columns if column != "timestamp"]
    merged[value_columns] = merged[value_columns].ffill()
    return merged


def fetch_macro_covariates() -> pd.DataFrame:
    frames = [
        fetch_bgeometrics_macro(),
        fetch_bis_g4_liquidity(),
        fetch_fed_net_liquidity(),
        fetch_dxy_inverse(),
        fetch_fear_greed(),
        fetch_usdt_issuance_proxy(),
    ]
    return combine_macro_frames(frames)
