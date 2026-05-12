import unittest

import pandas as pd

from bitcoin_chronos.macro import (
    MACRO_COVARIATE_COLUMNS,
    combine_macro_frames,
    decode_bgeometrics_series,
    normalize_bgeometrics_macro,
    normalize_bis_g4_liquidity,
    normalize_dxy_inverse,
    normalize_fear_greed,
    normalize_fed_net_liquidity,
    normalize_usdt_issuance_proxy,
)


class MacroDataTests(unittest.TestCase):
    def test_decode_bgeometrics_series_reads_compressed_chart_payload(self):
        encoded = "eJyLjjY0N0AAHQVDIwNkoGcQGwsAiRwHZg=="

        decoded = decode_bgeometrics_series(encoded)

        self.assertEqual(decoded, [[1_700_000_000_000, 120_000_000_000_000.0]])

    def test_normalize_bgeometrics_macro_combines_supply_and_growth(self):
        raw = {
            "M2 Global Supply (USD)": [[1_700_000_000_000, 120_000_000_000_000.0]],
            "M2 Growth YoY (%)": [[1_700_000_000_000, 8.2]],
        }

        normalized = normalize_bgeometrics_macro(raw)

        self.assertEqual(list(normalized.columns), ["timestamp", "m2_global_supply_usd", "m2_growth_yoy_pct"])
        self.assertEqual(float(normalized.iloc[0]["m2_global_supply_usd"]), 120_000_000_000_000.0)
        self.assertEqual(float(normalized.iloc[0]["m2_growth_yoy_pct"]), 8.2)

    def test_macro_covariate_columns_include_new_liquidity_and_sentiment_inputs(self):
        self.assertIn("g4_global_liquidity_usd", MACRO_COVARIATE_COLUMNS)
        self.assertIn("fed_net_liquidity_usd", MACRO_COVARIATE_COLUMNS)
        self.assertIn("dxy_inverse", MACRO_COVARIATE_COLUMNS)
        self.assertIn("fear_greed_index", MACRO_COVARIATE_COLUMNS)
        self.assertIn("usdt_supply_net_change_usd", MACRO_COVARIATE_COLUMNS)
        self.assertIn("usdt_supply_mint_proxy_usd", MACRO_COVARIATE_COLUMNS)
        self.assertIn("usdt_supply_burn_proxy_usd", MACRO_COVARIATE_COLUMNS)

    def test_normalize_bis_g4_liquidity_sums_usd_monthly_assets(self):
        rows = pd.DataFrame(
            {
                "FREQ:Frequency": ["M: Monthly"] * 4,
                "REF_AREA:Reference area": ["US: United States", "XM: Euro area", "JP: Japan", "CN: China"],
                "UNIT_MEASURE:Unit of measure": ["USD: US dollar"] * 4,
                "TRANSFORMATION:Transformation": ["B: Adjusted for breaks"] * 4,
                "TIME_PERIOD:Time period or range": ["2026-01"] * 4,
                "OBS_VALUE:Observation Value": [6_700.0, 6_200.0, 4_400.0, 6_800.0],
            }
        )

        normalized = normalize_bis_g4_liquidity(rows)

        self.assertEqual(list(normalized.columns), ["timestamp", "g4_global_liquidity_usd"])
        self.assertEqual(pd.Timestamp(normalized.iloc[0]["timestamp"]).strftime("%Y-%m-%d"), "2026-01-01")
        self.assertEqual(float(normalized.iloc[0]["g4_global_liquidity_usd"]), 24_100_000_000_000.0)

    def test_normalize_bis_g4_liquidity_forward_fills_staggered_area_updates(self):
        rows = pd.DataFrame(
            {
                "FREQ:Frequency": ["M: Monthly"] * 5,
                "REF_AREA:Reference area": [
                    "US: United States",
                    "XM: Euro area",
                    "JP: Japan",
                    "CN: China",
                    "XM: Euro area",
                ],
                "UNIT_MEASURE:Unit of measure": ["USD: US dollar"] * 5,
                "TRANSFORMATION:Transformation": ["B: Adjusted for breaks"] * 5,
                "TIME_PERIOD:Time period or range": ["2026-01", "2026-01", "2026-01", "2026-01", "2026-02"],
                "OBS_VALUE:Observation Value": [6_700.0, 6_200.0, 4_400.0, 6_800.0, 6_300.0],
            }
        )

        normalized = normalize_bis_g4_liquidity(rows)

        self.assertEqual(float(normalized.iloc[-1]["g4_global_liquidity_usd"]), 24_200_000_000_000.0)

    def test_normalize_fed_net_liquidity_subtracts_tga_and_reverse_repo(self):
        series = {
            "WALCL": pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01"], utc=True), "WALCL": [6_700_000.0]}),
            "WTREGEN": pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01"], utc=True), "WTREGEN": [800_000.0]}),
            "RRPONTSYD": pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01"], utc=True), "RRPONTSYD": [100_000.0]}),
        }

        normalized = normalize_fed_net_liquidity(series)

        self.assertEqual(float(normalized.iloc[0]["fed_net_liquidity_usd"]), 5_800_000_000_000.0)

    def test_normalize_dxy_inverse_flips_dollar_strength(self):
        raw = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_700_000_000],
                        "indicators": {"quote": [{"close": [100.0]}]},
                    }
                ]
            }
        }

        normalized = normalize_dxy_inverse(raw)

        self.assertEqual(float(normalized.iloc[0]["dxy_inverse"]), 1.0)

    def test_normalize_fear_greed_reads_alternative_me_payload(self):
        payload = {"data": [{"timestamp": "1700000000", "value": "42"}]}

        normalized = normalize_fear_greed(payload)

        self.assertEqual(float(normalized.iloc[0]["fear_greed_index"]), 42.0)

    def test_normalize_usdt_issuance_proxy_splits_mints_and_burns(self):
        payload = [
            {"date": "1700000000", "totalCirculatingUSD": {"peggedUSD": 100.0}},
            {"date": "1700086400", "totalCirculatingUSD": {"peggedUSD": 125.0}},
            {"date": "1700172800", "totalCirculatingUSD": {"peggedUSD": 115.0}},
        ]

        normalized = normalize_usdt_issuance_proxy(payload)

        self.assertEqual(normalized["usdt_supply_net_change_usd"].tolist(), [0.0, 25.0, -10.0])
        self.assertEqual(normalized["usdt_supply_mint_proxy_usd"].tolist(), [0.0, 25.0, 0.0])
        self.assertEqual(normalized["usdt_supply_burn_proxy_usd"].tolist(), [0.0, 0.0, 10.0])

    def test_combine_macro_frames_forward_fills_sparse_source_dates(self):
        combined = combine_macro_frames(
            [
                pd.DataFrame(
                    {
                        "timestamp": pd.to_datetime(["2026-01-01"], utc=True),
                        "g4_global_liquidity_usd": [24_000_000_000_000.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "timestamp": pd.to_datetime(["2026-01-02"], utc=True),
                        "fear_greed_index": [48.0],
                    }
                ),
            ]
        )

        latest = combined.iloc[-1]

        self.assertEqual(float(latest["g4_global_liquidity_usd"]), 24_000_000_000_000.0)
        self.assertEqual(float(latest["fear_greed_index"]), 48.0)


if __name__ == "__main__":
    unittest.main()
