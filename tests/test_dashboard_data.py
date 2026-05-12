import json
import unittest
from pathlib import Path


class DashboardDataTests(unittest.TestCase):
    def test_scenario_manifest_contains_covariate_switch_matrix(self):
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "data" / "latest" / "scenarios.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        expected = {
            "price_only": [],
            "macro_core": [
                "g4_global_liquidity_usd",
                "fed_net_liquidity_usd",
                "dxy_inverse",
                "fear_greed_index",
                "usdt_supply_net_change_usd",
                "usdt_supply_mint_proxy_usd",
                "usdt_supply_burn_proxy_usd",
                "btc_power_law_price_usd",
            ],
            "macro_m2_supply": [
                "g4_global_liquidity_usd",
                "fed_net_liquidity_usd",
                "dxy_inverse",
                "fear_greed_index",
                "usdt_supply_net_change_usd",
                "usdt_supply_mint_proxy_usd",
                "usdt_supply_burn_proxy_usd",
                "btc_power_law_price_usd",
                "m2_global_supply_usd",
            ],
            "macro_m2_growth": [
                "g4_global_liquidity_usd",
                "fed_net_liquidity_usd",
                "dxy_inverse",
                "fear_greed_index",
                "usdt_supply_net_change_usd",
                "usdt_supply_mint_proxy_usd",
                "usdt_supply_burn_proxy_usd",
                "btc_power_law_price_usd",
                "m2_growth_yoy_pct",
            ],
            "macro_all": [
                "g4_global_liquidity_usd",
                "fed_net_liquidity_usd",
                "dxy_inverse",
                "fear_greed_index",
                "usdt_supply_net_change_usd",
                "usdt_supply_mint_proxy_usd",
                "usdt_supply_burn_proxy_usd",
                "btc_power_law_price_usd",
                "m2_global_supply_usd",
                "m2_growth_yoy_pct",
            ],
        }
        actual = {key: scenario["covariates"] for key, scenario in manifest["scenarios"].items()}

        self.assertEqual(actual, expected)
        self.assertEqual(manifest["baseline"], "price_only")
        self.assertEqual(manifest["default"], "macro_all")
        self.assertEqual(manifest["coreCovariates"], expected["macro_core"])

        for scenario in manifest["scenarios"].values():
            for asset_key in ("summary", "forecast", "svg", "logSvg"):
                asset_path = root / scenario[asset_key].lstrip("/")
                self.assertTrue(asset_path.exists(), f"Missing {asset_key}: {asset_path}")


if __name__ == "__main__":
    unittest.main()
