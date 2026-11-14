"""Trend statistics on a gap-aware series.

All functions take ``t`` (decimal years, strictly increasing, gaps allowed) and ``x``
(finite values at those times). Slopes are returned **per year**; callers convert to
per decade. References:

* Mann (1945); Kendall (1975): Mann-Kendall S and its tie-corrected variance.
* Hamed & Rao (1998), J. Hydrology 204: variance correction for serial correlation,
  using the significant autocorrelations of the ranks of the Sen-detrended series.
* Sen (1968); Theil (1950): median pairwise slope; Gilbert (1987) rank-based interval.
* Hirsch, Slack & Smith (1982): Seasonal Kendall test.
* Pettitt (1979): non-parametric single change-point test.
* Weatherhead et al. (1998), JGR 103(D14): years of data needed to detect a trend.
* Benjamini & Hochberg (1995): false discovery rate for many simultaneous tests.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .distributions import norm_ppf, norm_sf, t_ppf, t_sf


@dataclass(frozen=True)
class MKResult:
    s: float
    var_s: float          # variance actually used (corrected for Hamed-Rao)
    var_s_plain: float    # classic tie-corrected variance
    z: float
    p_value: float
    p_value_plain: float
    correction_factor: float
    tau: float


@dataclass(frozen=True)
class SlopeResult:
    slope: float           # per year
    lower: float
    upper: float
    intercept: float       # value at t = 0 of the centred time axis (see caller)


@dataclass(frozen=True)
class OLSResult:
    slope: float
    lower: float
    upper: float
    p_value: float
    intercept: float
    stderr: float


def _sign_matrix(x: np.ndarray) -> np.ndarray:
    return np.sign(x[None, :] - x[:, None])


def mk_s(x: np.ndarray) -> float:
    """Mann-Kendall S = sum over i<j of sign(x_j - x_i)."""
    return float(np.triu(_sign_matrix(x), k=1).sum())


def mk_var(x: np.ndarray) -> float:
    n = len(x)
    _, counts = np.unique(x, return_counts=True)
    ties = counts[counts > 1]
    return (n * (n - 1) * (2 * n + 5) - float(np.sum(ties * (ties - 1) * (2 * ties + 5)))) / 18.0


def _z_from_s(s: float, var: float) -> float:
    if var <= 0:
        return 0.0
    if s > 0:
        return (s - 1) / math.sqrt(var)
    if s < 0:
        return (s + 1) / math.sqrt(var)
    return 0.0


def sen_slope(t: np.ndarray, x: np.ndarray) -> float:
    i, j = np.triu_indices(len(x), k=1)
    dt = t[j] - t[i]
    keep = dt != 0
    return float(np.median((x[j] - x[i])[keep] / dt[keep]))


def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    sorted_x = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sorted_x[j + 1] == sorted_x[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def gap_aware_acf(values_on_grid: np.ndarray, max_lag: int) -> np.ndarray:
    """Autocorrelation on a regular time grid where gaps are NaN.

    Each lag uses only pairs that are both observed, so a missing month never makes two
    observations 'adjacent' (handbook pp24-26: preserve true spacing).
    """
    v = np.asarray(values_on_grid, dtype=float)
    ok = np.isfinite(v)
    mean = np.nanmean(v)
    d = np.where(ok, v - mean, 0.0)
    denom = float(np.sum(d * d))  # standard (biased) estimator, as in Hamed & Rao and pymannkendall
    acf = np.zeros(max_lag + 1)
    acf[0] = 1.0
    if denom == 0:
        return acf
    for k in range(1, max_lag + 1):
        both = ok[:-k] & ok[k:]
        if both.sum() < 3:
            break
        acf[k] = float(np.sum(d[:-k][both] * d[k:][both])) / denom
    return acf


def hamed_rao_mk(t: np.ndarray, x: np.ndarray, grid_index: np.ndarray, alpha_acf: float = 0.05) -> MKResult:
    """Mann-Kendall with Hamed-Rao (1998) variance correction.

    ``grid_index`` gives each observation's integer position on the regular time grid
    (month number or year number) so the rank autocorrelation is gap-aware.
    """
    n = len(x)
    s = mk_s(x)
    var_plain = mk_var(x)
    # Detrend with Sen's slope, rank, and keep only significant rank autocorrelations.
    b = sen_slope(t, x)
    ranks = _rank(x - b * t)
    size = int(grid_index.max() - grid_index.min()) + 1
    grid = np.full(size, np.nan)
    grid[grid_index - grid_index.min()] = ranks
    acf = gap_aware_acf(grid, max_lag=min(size - 1, n - 1))
    bound = norm_ppf(1 - alpha_acf / 2) / math.sqrt(n)
    total = 0.0
    for k in range(1, len(acf)):
        if abs(acf[k]) > bound and n - k - 2 > 0:
            total += (n - k) * (n - k - 1) * (n - k - 2) * acf[k]
    factor = 1.0 + 2.0 / (n * (n - 1) * (n - 2)) * total
    if not math.isfinite(factor) or factor <= 0:
        factor = 1.0  # documented guard: never shrink variance to zero/negative
    var = var_plain * factor
    z = _z_from_s(s, var)
    z_plain = _z_from_s(s, var_plain)
    return MKResult(s=s, var_s=var, var_s_plain=var_plain, z=z, p_value=min(1.0, 2 * norm_sf(abs(z))),
                    p_value_plain=min(1.0, 2 * norm_sf(abs(z_plain))), correction_factor=factor,
                    tau=s / (n * (n - 1) / 2))


def sen_with_ci(t: np.ndarray, x: np.ndarray, var_s: float, ci_level: float) -> SlopeResult:
    """Theil-Sen slope with the Gilbert (1987) rank interval.

    Passing the Hamed-Rao corrected variance makes the interval as conservative as the
    corrected p-value, so 'interval excludes zero' agrees with 'p < alpha'.
    """
    i, j = np.triu_indices(len(x), k=1)
    dt = t[j] - t[i]
    keep = dt != 0
    slopes = np.sort((x[j] - x[i])[keep] / dt[keep])
    n_slopes = len(slopes)
    slope = float(np.median(slopes))
    c = norm_ppf(1 - (1 - ci_level) / 2) * math.sqrt(max(var_s, 0.0))
    m1 = (n_slopes - c) / 2.0          # 1-based order statistics
    m2 = (n_slopes + c) / 2.0 + 1.0
    positions = np.arange(1, n_slopes + 1)
    lower = float(np.interp(np.clip(m1, 1, n_slopes), positions, slopes))
    upper = float(np.interp(np.clip(m2, 1, n_slopes), positions, slopes))
    intercept = float(np.median(x - slope * t))
    return SlopeResult(slope=slope, lower=min(lower, slope), upper=max(upper, slope), intercept=intercept)


def ols(t: np.ndarray, x: np.ndarray, ci_level: float) -> OLSResult:
    n = len(x)
    tm, xm = t.mean(), x.mean()
    sxx = float(np.sum((t - tm) ** 2))
    slope = float(np.sum((t - tm) * (x - xm)) / sxx)
    intercept = xm - slope * tm
    resid = x - (intercept + slope * t)
    dof = n - 2
    s2 = float(np.sum(resid ** 2)) / dof
    se = math.sqrt(s2 / sxx) if s2 > 0 else 0.0
    if se == 0:
        p = 0.0 if slope != 0 else 1.0
        return OLSResult(slope, slope, slope, p, float(intercept), 0.0)
    tval = slope / se
    p = min(1.0, 2 * t_sf(abs(tval), dof))
    half = t_ppf(1 - (1 - ci_level) / 2, dof) * se
    return OLSResult(slope, slope - half, slope + half, p, float(intercept), se)


def seasonal_kendall(t: np.ndarray, x: np.ndarray, month: np.ndarray) -> tuple[float, float]:
    """Hirsch et al. (1982): sum of per-month S/variances; slope = median within-month slope.

    Returns (slope_per_year, p_value). Cross-season covariance is ignored (the classic test).
    """
    s_total, var_total, slopes = 0.0, 0.0, []
    for m in np.unique(month):
        sel = month == m
        if sel.sum() < 3:
            continue
        xm, tm = x[sel], t[sel]
        s_total += mk_s(xm)
        var_total += mk_var(xm)
        i, j = np.triu_indices(len(xm), k=1)
        dt = tm[j] - tm[i]
        keep = dt != 0
        slopes.append((xm[j] - xm[i])[keep] / dt[keep])
    if not slopes or var_total <= 0:
        return 0.0, 1.0
    z = _z_from_s(s_total, var_total)
    return float(np.median(np.concatenate(slopes))), min(1.0, 2 * norm_sf(abs(z)))


def lag1(values_on_grid: np.ndarray) -> float:
    acf = gap_aware_acf(values_on_grid, 1)
    return float(acf[1])


def pettitt(x: np.ndarray) -> tuple[int, float, float]:
    """Pettitt (1979) change-point test. Returns (index of last point before change, K, approx p)."""
    n = len(x)
    sign = _sign_matrix(x)  # sign(x_j - x_i)
    # U_k = sum_{i<=k} sum_{j>k} sign(x_i - x_j)
    u = np.array([-float(sign[: k + 1, k + 1:].sum()) for k in range(n - 1)])
    k_idx = int(np.argmax(np.abs(u)))
    k_stat = float(abs(u[k_idx]))
    p = min(1.0, 2 * math.exp(-6 * k_stat ** 2 / (n ** 3 + n ** 2)))
    return k_idx, k_stat, p


def years_to_detect(slope_per_year: float, noise_sd: float, phi: float, obs_per_year: int,
                    alpha: float = 0.05, power: float = 0.90) -> float | None:
    """Record length (years) needed to detect ``slope_per_year`` (Weatherhead et al. 1998).

    n* = [ (z_{1-a/2} + z_{power}) * sigma * sqrt(12/m) * sqrt((1+phi)/(1-phi)) / |slope| ]^(2/3)

    With m = 12 monthly values, z sum = 3.24, this is Weatherhead's well-known
    n* = [3.3 sigma_N/|w0| * sqrt((1+phi)/(1-phi))]^(2/3).
    """
    if slope_per_year == 0 or not math.isfinite(slope_per_year) or noise_sd <= 0:
        return None
    phi = min(max(phi, -0.95), 0.95)
    zsum = norm_ppf(1 - alpha / 2) + norm_ppf(power)
    value = (zsum * noise_sd * math.sqrt(12.0 / obs_per_year) * math.sqrt((1 + phi) / (1 - phi))
             / abs(slope_per_year)) ** (2.0 / 3.0)
    return float(value)


def bh_fdr(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted q-values, in the input order."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p_values[i] * m / rank)
        q[i] = min(1.0, running)
    return q
