import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd

from bitcoin_chronos.outputs import forecast_summary, point_forecast_column, write_forecast_svg


class ForecastOutputTests(unittest.TestCase):
    def test_point_forecast_column_prefers_chronos_predictions(self):
        frame = pd.DataFrame({"timestamp": [pd.Timestamp("2026-01-01")], "predictions": [100.0], "0.5": [99.0]})

        self.assertEqual(point_forecast_column(frame), "predictions")

    def test_forecast_summary_reports_first_and_last_points(self):
        forecast = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "0.1": [90.0, 91.0],
                "0.5": [100.0, 102.0],
                "0.9": [110.0, 115.0],
            }
        )

        summary = forecast_summary(forecast)

        self.assertEqual(summary["point_column"], "0.5")
        self.assertEqual(summary["first_point"], 100.0)
        self.assertEqual(summary["last_point"], 102.0)
        self.assertEqual(summary["last_low"], 91.0)
        self.assertEqual(summary["last_high"], 115.0)

    def test_forecast_summary_accepts_numeric_quantile_column_names(self):
        forecast = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01"]),
                0.5: [100.0],
            }
        )

        summary = forecast_summary(forecast)

        self.assertEqual(summary["point_column"], "0.5")
        self.assertEqual(summary["last_point"], 100.0)

    def test_write_forecast_svg_accepts_mixed_timezone_inputs(self):
        history = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                "close": [100.0, 101.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-01-03", "2026-01-04"]),
                "0.5": [102.0, 103.0],
            }
        )

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "forecast.svg"
            write_forecast_svg(history, forecast, path)

            self.assertIn("BTCUSDT Chronos-2 Forecast", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
