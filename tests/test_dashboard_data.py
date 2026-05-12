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
            "m2_supply": ["m2_global_supply_usd"],
            "m2_growth": ["m2_growth_yoy_pct"],
            "m2_both": ["m2_global_supply_usd", "m2_growth_yoy_pct"],
        }
        actual = {key: scenario["covariates"] for key, scenario in manifest["scenarios"].items()}

        self.assertEqual(actual, expected)
        self.assertEqual(manifest["baseline"], "price_only")
        self.assertEqual(manifest["default"], "m2_both")

        for scenario in manifest["scenarios"].values():
            for asset_key in ("summary", "forecast", "svg", "logSvg"):
                asset_path = root / scenario[asset_key].lstrip("/")
                self.assertTrue(asset_path.exists(), f"Missing {asset_key}: {asset_path}")


if __name__ == "__main__":
    unittest.main()
