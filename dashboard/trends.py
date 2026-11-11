
"""Long-term NOAA SST trend analysis."""

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, theilslopes


MIN_MONTHS_PER_YEAR = 9
MIN_DAYS_PER_MONTH = 15
MIN_YEARS_FOR_TEST = 10
SIGNIFICANCE_LEVEL = 0.05


def prepare_annual_sst(
    history,
    min_months=MIN_MONTHS_PER_YEAR,
    min_days_per_month=MIN_DAYS_PER_MONTH,
):
    """
    Convert daily regional SST means into annual means.

    A month is valid when it contains at least 15 daily observations.
    A year is valid when it contains at least 9 valid months.
    Each month receives equal weight in the annual mean.
    """
    required = {"region", "date", "sst_mean"}

    if history is None or history.empty:
        return pd.DataFrame()

    if not required.issubset(history.columns):
        return pd.DataFrame()

    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["sst_mean"] = pd.to_numeric(
        data["sst_mean"], errors="coerce"
    )

    if "sst_valid_count" in data:
        valid_count = pd.to_numeric(
            data["sst_valid_count"], errors="coerce"
        )
        data.loc[valid_count <= 0, "sst_mean"] = np.nan

    data = data.dropna(subset=["region", "date", "sst_mean"])
    data = data[np.isfinite(data["sst_mean"])]

    if data.empty:
        return pd.DataFrame()

    data["region"] = data["region"].astype(str)
    data = data.drop_duplicates(["region", "date"], keep="last")
    data["year"] = data["date"].dt.year
    data["month"] = data["date"].dt.month

    monthly = (
        data.groupby(["region", "year", "month"], as_index=False)
        .agg(
            monthly_sst_mean=("sst_mean", "mean"),
            valid_days=("sst_mean", "count"),
        )
    )

    monthly = monthly[
        monthly["valid_days"] >= min_days_per_month
    ]

    if monthly.empty:
        return pd.DataFrame()

    annual = (
        monthly.groupby(["region", "year"], as_index=False)
        .agg(
            annual_sst_mean=("monthly_sst_mean", "mean"),
            months_covered=("month", "nunique"),
            valid_days=("valid_days", "sum"),
        )
    )

    annual = annual[
        annual["months_covered"] >= min_months
    ].copy()

    return annual.sort_values(["region", "year"]).reset_index(drop=True)


def benjamini_hochberg(p_values):
    """Benjamini-Hochberg false discovery rate correction."""
    p_values = np.asarray(p_values, dtype=float)
    adjusted = np.full(p_values.shape, np.nan)

    valid_indices = np.where(np.isfinite(p_values))[0]
    if len(valid_indices) == 0:
        return adjusted

    valid_p = p_values[valid_indices]
    order = np.argsort(valid_p)
    sorted_p = valid_p[order]

    count = len(sorted_p)
    ranked = sorted_p * count / np.arange(1, count + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    ranked = np.clip(ranked, 0, 1)

    sorted_adjusted = np.empty(count, dtype=float)
    sorted_adjusted[order] = ranked
    adjusted[valid_indices] = sorted_adjusted

    return adjusted


def estimate_sst_trends(
    annual,
    min_years=MIN_YEARS_FOR_TEST,
    alpha=SIGNIFICANCE_LEVEL,
):
    """
    Estimate per-region SST trends.

    Theil-Sen estimates the slope and its 95% confidence interval.
    Kendall's tau provides a two-sided monotonic-trend test.
    P-values are also adjusted across regions using Benjamini-Hochberg.

    Serial autocorrelation is not corrected; results should be interpreted
    as exploratory trend evidence rather than a definitive climate attribution.
    """
    columns = [
        "region",
        "slope_c_per_year",
        "slope_c_per_decade",
        "ci_low_c_per_decade",
        "ci_high_c_per_decade",
        "kendall_tau",
        "p_value",
        "q_value",
        "years",
        "first_year",
        "last_year",
        "significant_fdr",
        "trend",
        "status",
    ]

    if annual is None or annual.empty:
        return pd.DataFrame(columns=columns)

    required = {"region", "year", "annual_sst_mean"}
    if not required.issubset(annual.columns):
        return pd.DataFrame(columns=columns)

    results = []

    for region, group in annual.groupby("region"):
        group = group.sort_values("year").dropna(
            subset=["year", "annual_sst_mean"]
        )

        group = group.drop_duplicates("year", keep="last")
        years = group["year"].astype(float).to_numpy()
        values = group["annual_sst_mean"].astype(float).to_numpy()

        row = {
            "region": region,
            "slope_c_per_year": np.nan,
            "slope_c_per_decade": np.nan,
            "ci_low_c_per_decade": np.nan,
            "ci_high_c_per_decade": np.nan,
            "kendall_tau": np.nan,
            "p_value": np.nan,
            "q_value": np.nan,
            "years": len(group),
            "first_year": int(years.min()) if len(years) else np.nan,
            "last_year": int(years.max()) if len(years) else np.nan,
            "significant_fdr": False,
            "trend": "Not evaluated",
            "status": "Insufficient data",
        }

        if len(group) >= min_years and len(np.unique(values)) > 1:
            slope = theilslopes(values, years, alpha=1 - alpha)
            kendall = kendalltau(
                years,
                values,
                alternative="two-sided",
                method="auto",
            )

            row.update({
                "slope_c_per_year": float(slope.slope),
                "slope_c_per_decade": float(slope.slope * 10),
                "ci_low_c_per_decade": float(slope.low_slope * 10),
                "ci_high_c_per_decade": float(slope.high_slope * 10),
                "kendall_tau": float(kendall.statistic),
                "p_value": float(kendall.pvalue),
                "status": "Tested",
            })

            if slope.slope > 0:
                row["trend"] = "Increasing"
            elif slope.slope < 0:
                row["trend"] = "Decreasing"
            else:
                row["trend"] = "No slope"

        elif len(group) >= min_years:
            # A constant series has no increasing/decreasing trend.
            row.update({
                "slope_c_per_year": 0.0,
                "slope_c_per_decade": 0.0,
                "ci_low_c_per_decade": 0.0,
                "ci_high_c_per_decade": 0.0,
                "kendall_tau": 0.0,
                "p_value": 1.0,
                "trend": "No trend",
                "status": "Tested",
            })

        results.append(row)

    summary = pd.DataFrame(results)

    tested = summary["p_value"].notna()
    if tested.any():
        summary.loc[tested, "q_value"] = benjamini_hochberg(
            summary.loc[tested, "p_value"].to_numpy()
        )

        summary.loc[tested, "significant_fdr"] = (
            summary.loc[tested, "q_value"] < alpha
        )

    return summary[columns]


def analyze_sst_history(history):
    """Convenience function returning annual data and trend statistics."""
    annual = prepare_annual_sst(history)
    summary = estimate_sst_trends(annual)
    return annual, summary
