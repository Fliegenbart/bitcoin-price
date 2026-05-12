import unittest

import pandas as pd

from bitcoin_chronos.data import (
    build_context_frame,
    interval_to_milliseconds,
    interval_to_pandas_freq,
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
