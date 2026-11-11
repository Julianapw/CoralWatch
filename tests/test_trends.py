
import unittest

import numpy as np
import pandas as pd

from dashboard.trends import (
    prepare_annual_sst,
    estimate_sst_trends,
)


def create_daily_history(
    years=range(2000, 2022),
    slope=0.025,
    noise=False,
):
    rows = []

    for year in years:
        for month in range(1, 13):
            for day in range(1, 16):
                value = 25.0 + slope * (year - 2000)

                if noise:
                    value += 0.03 * np.sin(
                        (year - 2000) * 0.7 + month
                    )

                rows.append({
                    "region": "Test Reef",
                    "date": (
                        f"{year}-{month:02d}-{day:02d}"
                    ),
                    "SST_mean": value,
                    "SST_valid_count": 20,
                })

    return pd.DataFrame(rows)


class TrendAnalysisTests(unittest.TestCase):

    def test_increasing_trend_is_detected(self):
        history = create_daily_history(noise=True)

        # The loader normally converts SST_mean to sst_mean.
        history = history.rename(
            columns={"SST_mean": "sst_mean"}
        )

        annual = prepare_annual_sst(history)
        summary = estimate_sst_trends(annual)

        self.assertEqual(len(annual), 22)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]["status"], "Tested")
        self.assertGreater(
            summary.iloc[0]["slope_c_per_year"],
            0,
        )
        self.assertLess(
            summary.iloc[0]["p_value"],
            0.05,
        )

    def test_constant_series_is_not_significant(self):
        history = create_daily_history(slope=0.0)
        history = history.rename(
            columns={"SST_mean": "sst_mean"}
        )

        annual = prepare_annual_sst(history)
        summary = estimate_sst_trends(annual)

        self.assertEqual(summary.iloc[0]["status"], "Tested")
        self.assertAlmostEqual(
            summary.iloc[0]["slope_c_per_year"],
            0.0,
        )
        self.assertEqual(summary.iloc[0]["p_value"], 1.0)
        self.assertFalse(summary.iloc[0]["significant_fdr"])

    def test_insufficient_history_is_not_tested(self):
        history = create_daily_history(
            years=range(2015, 2023),
            slope=0.03,
        )
        history = history.rename(
            columns={"SST_mean": "sst_mean"}
        )

        annual = prepare_annual_sst(history)
        summary = estimate_sst_trends(annual)

        self.assertEqual(len(annual), 8)
        self.assertEqual(
            summary.iloc[0]["status"],
            "Insufficient data",
        )
        self.assertTrue(
            pd.isna(summary.iloc[0]["p_value"])
        )


if __name__ == "__main__":
    unittest.main()
