import unittest

from bitcoin_chronos.forecast import selected_m2_covariates


class ForecastCliTests(unittest.TestCase):
    def test_selected_m2_covariates_accepts_single_macro_column(self):
        self.assertEqual(selected_m2_covariates("m2_global_supply_usd", enabled=True), ["m2_global_supply_usd"])

    def test_selected_m2_covariates_supports_none(self):
        self.assertEqual(selected_m2_covariates("none", enabled=True), [])
        self.assertEqual(selected_m2_covariates("m2_growth_yoy_pct", enabled=False), [])

    def test_selected_m2_covariates_rejects_unknown_column(self):
        with self.assertRaises(ValueError):
            selected_m2_covariates("m2_global_supply_usd,unknown_column", enabled=True)


if __name__ == "__main__":
    unittest.main()
