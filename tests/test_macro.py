import unittest

from bitcoin_chronos.macro import decode_bgeometrics_series, normalize_bgeometrics_macro


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


if __name__ == "__main__":
    unittest.main()
