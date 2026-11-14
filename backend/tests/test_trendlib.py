"""trendlib statistics against independent reference implementations.

Reference numbers were produced with pymannkendall 1.4.3 (hamed_rao_modification_test,
original_test) and SciPy 1.18 (linregress, t, norm) on the series X below; neither
library is a runtime dependency. Agreement is required to 1e-9 (statistics) or 1e-6.
"""
import math

import numpy as np
import pandas as pd
import pytest

import trendlib
from trendlib import distributions as D, stats as S
from trendlib.exceptions import DataQualityError, InsufficientDataError

X = np.array([0.4, 0.3257, 0.3317, 1.1427, 1.5197, 1.0046, 0.9236, 1.3875, 1.062, 0.2239, 0.1994, 0.4443,
              -0.1487, -0.6766, -0.2046, 0.1644, -0.2039, -0.0524, 0.8947, 1.2537, 1.0347, 1.5409, 2.3497,
              2.2001, 1.7897, 2.1726, 2.3781, 1.6261, 1.1358, 1.4381, 1.2528, 0.4573, 0.4351, 1.0104, 0.8821,
              0.5741, 1.239, 2.0181, 1.9217, 1.9913])
T = np.arange(40, dtype=float)


def test_distributions_match_scipy():
    assert D.t_ppf(0.975, 10) == pytest.approx(2.228138851986274, abs=1e-8)
    assert D.t_sf(2.1, 15) == pytest.approx(0.026527628076021388, abs=1e-10)
    assert D.norm_ppf(0.995) == pytest.approx(2.5758293035489004, abs=1e-9)


def test_mann_kendall_and_hamed_rao_match_pymannkendall():
    r = S.hamed_rao_mk(T, X, np.arange(40))
    assert r.s == 202
    assert r.var_s_plain == pytest.approx(7366.666666666667, rel=1e-12)
    assert r.p_value_plain == pytest.approx(0.019188016537287966, abs=1e-9)
    assert r.var_s == pytest.approx(7707.6548500707695, rel=1e-9)
    assert r.p_value == pytest.approx(0.02205206792512726, abs=1e-9)
    assert S.sen_slope(T, X) == pytest.approx(0.02843625, abs=1e-12)


def test_ols_matches_scipy_linregress():
    o = S.ols(T, X, 0.95)
    assert o.slope == pytest.approx(0.029046885553470923, abs=1e-12)
    assert o.p_value == pytest.approx(0.0052971377508730134, abs=1e-9)
    assert o.lower < o.slope < o.upper


def test_sen_interval_brackets_slope_and_agrees_with_corrected_p():
    r = S.hamed_rao_mk(T, X, np.arange(40))
    ci = S.sen_with_ci(T, X, r.var_s, 0.95)
    assert ci.lower <= ci.slope <= ci.upper
    assert (ci.lower > 0) == (r.p_value < 0.05)


def test_bh_fdr_and_detection_time():
    assert S.bh_fdr([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.0533333333, 0.0533333333, 0.5])
    # Weatherhead et al. (1998): sigma=1, phi=0, slope=0.1/yr, monthly -> (3.24*1/0.1)^(2/3) ~ 10.2 years.
    assert S.years_to_detect(0.1, 1.0, 0.0, 12) == pytest.approx(10.17, abs=0.05)
    assert S.years_to_detect(0.0, 1.0, 0.0, 12) is None


def test_pettitt_finds_a_step():
    x = np.r_[np.zeros(20), np.ones(20)] + np.tile([0.01, -0.01], 20)
    idx, _, p = S.pettitt(x)
    assert idx == 19 and p < 0.001


def _frame(values, start="2003-01", qc=None):
    dates = pd.date_range(start, periods=len(values), freq="MS").date
    frame = pd.DataFrame({"date": dates, "value": values, "valid_fraction": 1.0,
                          "qc_flag": qc or ["ok" if v is not None and not math.isnan(v) else "missing" for v in values]})
    frame.attrs.update(region_id="R", variable="aod", source_id="S", unit="1", frequency="month",
                       period={"start": dates[0].strftime("%Y-%m"), "end": dates[-1].strftime("%Y-%m")})
    return frame


def test_compute_trend_recovers_a_known_trend_through_the_seasonal_cycle():
    rng = np.random.default_rng(7)
    n = 264
    months = np.arange(n) % 12
    values = 0.5 + 0.2 * np.sin(2 * np.pi * months / 12) + 0.003 * np.arange(n) / 12 * 10 / 10 + rng.normal(0, 0.02, n)
    # True slope: 0.003 per year = 0.03 per decade.
    result = trendlib.compute_trend(_frame(list(values)), season="all")
    assert result["series_type"] == "monthly_deseasonalised"
    assert result["sen_slope"] == pytest.approx(0.03, abs=0.006)
    assert result["significant"] and result["direction"] == "increasing"
    assert result["slope_ci"][0] <= result["sen_slope"] <= result["slope_ci"][1]
    names = [r["name"] for r in result["evidence"]["sensitivity"]]
    assert names == ["end_2021", "seasonal_kendall", "ols"]
    assert result["evidence"]["evidence_label"] == "strong"


def test_seasonal_selection_uses_complete_seasons_only():
    values = [1.0 + 0.01 * i for i in range(264)]
    values[5] = None  # June 2003 missing -> JJAS 2003 skipped, not averaged from 3 months
    result = trendlib.compute_trend(_frame(values), season="JJAS")
    assert result["series_type"] == "seasonal_mean"
    assert result["n_expected"] == 88 and result["n_valid"] == 87
    assert result["direction"] == "increasing"


def test_missing_values_are_never_filled_and_gaps_keep_spacing():
    values = [float(i % 12) + 0.002 * i for i in range(264)]
    for i in range(60, 84):
        values[i] = None  # two whole years missing
    result = trendlib.compute_trend(_frame(values), season="all")
    assert result["n_valid"] == 240 and result["n_expected"] == 264
    assert result["sen_slope"] == pytest.approx(0.24, abs=1e-6)  # 0.002 per month = 0.24 per decade


def test_named_exceptions():
    with pytest.raises(InsufficientDataError):
        trendlib.compute_trend(_frame([1.0] * 30), season="all")
    frame = _frame([1.0] * 130)
    frame.loc[1, "date"] = frame.loc[0, "date"]
    with pytest.raises(DataQualityError):
        trendlib.compute_trend(frame, season="all")


def test_flat_series_is_not_significant_and_label_rule():
    result = trendlib.compute_trend(_frame([0.5 + 0.1 * (i % 12) for i in range(264)]), season="all")
    assert result["sen_slope"] == 0 and not result["significant"]
    assert result["direction"] == "no_significant_trend" and result["slope_sign"] == "zero"
    assert trendlib.evidence_label(record_years=9, valid_obs_pct=99, p_value=0.001, alpha=0.05,
                                   ci_excludes_zero=True, sensitivity=[]) == "insufficient_data"


def test_analyze_values_annual_real_research_series():
    # Real annual Aqua MODIS AOD, IGP box (Group 3 export, slide 14).
    igp = [0.4528, 0.4927, 0.4311, 0.4398, 0.4603, 0.5171, 0.4713, 0.4973, 0.5402, 0.5196, 0.5225, 0.5227,
           0.5411, 0.573, 0.5252, 0.5922, 0.5908, 0.5656, 0.6199, 0.6002, 0.5733, 0.606]
    out = trendlib.analyze_values([f"{y}-01-01" for y in range(2003, 2025)], igp, frequency="year")
    assert out["significant"] and out["direction"] == "increasing"
    assert out["sen_slope_per_decade"] == pytest.approx(0.0791, abs=5e-4)
    assert out["mk_p_value"] < 0.001
    assert len(out["fit"]) == 22 and all(f["lower"] <= f["upper"] for f in out["fit"])
