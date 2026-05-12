import unittest

import pandas as pd

from bitcoin_chronos.data import (
    attach_power_law_covariate,
    build_context_frame,
    interval_to_milliseconds,
    interval_to_pandas_freq,
    merge_macro_covariates,
    parse_binance_klines,
)


class BinanceDataTests(unittest.TestCase):
    def test_parse_binance_klines_keeps_clean_price_history(self):
        rows = [
            [
                1_700_000_000_000,
                "100.0",
                "110.0",
                "90.0",
                "105.5",
                "12.3",
                1_700_086_399_999,
                "1297.65",
                42,
                "6.1",
                "640.0",
                "0",
            ],
            [
                1_700_086_400_000,
                "105.5",
                "115.0",
                "101.0",
                "112.0",
                "8.0",
                1_700_172_799_999,
                "896.0",
                31,
                "4.0",
                "448.0",
                "0",
            ],
        ]

        parsed = parse_binance_klines(rows)

        self.assertEqual(list(parsed.columns), ["timestamp", "open", "high", "low", "close", "volume"])
        self.assertEqual(str(parsed["timestamp"].dt.tz), "UTC")
        self.assertEqual(parsed["close"].tolist(), [105.5, 112.0])
        self.assertEqual(parsed["volume"].tolist(), [12.3, 8.0])

    def test_build_context_frame_uses_chronos_columns(self):
        history = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                "close": [100.0, 101.0],
            }
        )

        context = build_context_frame(history, item_id="BTCUSDT")

        self.assertEqual(list(context.columns), ["id", "timestamp", "close"])
        self.assertEqual(context["id"].tolist(), ["BTCUSDT", "BTCUSDT"])
        self.assertTrue(context["timestamp"].dt.tz is None)

    def test_build_context_frame_keeps_requested_covariate_columns(self):
        history = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                "close": [100.0, 101.0],
                "m2_global_supply_usd": [120_000_000_000_000.0, 120_100_000_000_000.0],
                "m2_growth_yoy_pct": [8.1, 8.2],
            }
        )

        context = build_context_frame(
            history,
            item_id="BTCUSDT",
            covariate_columns=["m2_global_supply_usd", "m2_growth_yoy_pct"],
        )

        self.assertEqual(
            list(context.columns),
            ["id", "timestamp", "close", "m2_global_supply_usd", "m2_growth_yoy_pct"],
        )
        self.assertEqual(context["m2_growth_yoy_pct"].tolist(), [8.1, 8.2])

    def test_merge_macro_covariates_forward_fills_latest_known_macro_values(self):
        history = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-09"], utc=True),
                "close": [100.0, 101.0, 102.0],
            }
        )
        macro = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2025-12-29", "2026-01-05"], utc=True),
                "m2_global_supply_usd": [120.0, 121.0],
                "m2_growth_yoy_pct": [8.0, 8.5],
            }
        )

        merged = merge_macro_covariates(history, macro, required=["m2_global_supply_usd", "m2_growth_yoy_pct"])

        self.assertEqual(merged["m2_global_supply_usd"].tolist(), [120.0, 120.0, 121.0])
        self.assertEqual(merged["m2_growth_yoy_pct"].tolist(), [8.0, 8.0, 8.5])

    def test_merge_macro_covariates_drops_rows_before_macro_coverage(self):
        history = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                "close": [100.0, 101.0],
            }
        )
        macro = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-02"], utc=True),
                "fear_greed_index": [45.0],
            }
        )

        merged = merge_macro_covariates(history, macro, required=["fear_greed_index"], drop_incomplete_start=True)

        self.assertEqual(merged["close"].tolist(), [101.0])
        self.assertEqual(merged["fear_greed_index"].tolist(), [45.0])

    def test_attach_power_law_covariate_fits_log_time_price_curve(self):
        origin = pd.Timestamp("2020-01-01", tz="UTC")
        history = pd.DataFrame(
            {
                "timestamp": origin + pd.to_timedelta([1, 2, 4], unit="D"),
                "close": [3.0, 12.0, 48.0],
            }
        )

        enriched = attach_power_law_covariate(history, origin=origin)

        self.assertIn("btc_power_law_price_usd", enriched.columns)
        self.assertEqual([round(value, 6) for value in enriched["btc_power_law_price_usd"]], [3.0, 12.0, 48.0])

    def test_interval_to_pandas_freq_maps_common_crypto_intervals(self):
        self.assertEqual(interval_to_pandas_freq("1d"), "D")
        self.assertEqual(interval_to_pandas_freq("4h"), "4h")
        self.assertEqual(interval_to_pandas_freq("15m"), "15min")

    def test_interval_to_milliseconds_maps_common_crypto_intervals(self):
        self.assertEqual(interval_to_milliseconds("1d"), 86_400_000)
        self.assertEqual(interval_to_milliseconds("4h"), 14_400_000)
        self.assertEqual(interval_to_milliseconds("15m"), 900_000)


if __name__ == "__main__":
    unittest.main()
