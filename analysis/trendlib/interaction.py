"""Rainfall-AOD event composites (Aadarsh's handbook pp27-29, contract section H).

Association only: MODIS AOD is retrieved in clear skies, so rainy days are under-sampled. Nothing here
attributes a cause. Missing AOD stays missing; non-positive AOD retrievals are excluded from window means
(Group 3 flagged one such retrieval for review).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np

from .distributions import norm_sf, t_sf

SEASON_MONTHS = {"all": tuple(range(1, 13)), "JF": (1, 2), "MAM": (3, 4, 5), "JJAS": (6, 7, 8, 9), "OND": (10, 11, 12)}
WINDOW = 3
SEPARATION = 7
CONTROLS_PER_EVENT = 5
MIN_EVENTS = 10
BOOTSTRAP = 5000
SEED = 20261114
GUARDRAIL = "Association only. AOD is retrieved in clear skies, so rainy days are under-sampled."
TOO_FEW = "too few events for a reliable comparison"


def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    s = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def wilcoxon_signed_rank(d: np.ndarray) -> float:
    """Two-sided Wilcoxon signed-rank p (zeros dropped, tie-corrected normal approximation, continuity 0.5)."""
    d = d[d != 0]
    n = len(d)
    if n == 0:
        return 1.0
    r = _rank(np.abs(d))
    w_plus = float(r[d > 0].sum())
    mean = n * (n + 1) / 4
    _, counts = np.unique(np.abs(d), return_counts=True)
    var = n * (n + 1) * (2 * n + 1) / 24 - float(np.sum(counts ** 3 - counts)) / 48
    if var <= 0:
        return 1.0
    z = (abs(w_plus - mean) - 0.5) / math.sqrt(var)
    return min(1.0, 2 * norm_sf(max(z, 0.0)))


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Spearman rho and two-sided p (t approximation with n-2 df)."""
    rx, ry = _rank(x), _rank(y)
    rho = float(np.corrcoef(rx, ry)[0, 1])
    n = len(x)
    if n < 4 or abs(rho) >= 1:
        return rho, 0.0 if abs(rho) >= 1 else 1.0
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return rho, min(1.0, 2 * t_sf(abs(t), n - 2))


def _window_mean(aod: dict[date, float], day: date, sign: int) -> tuple[float | None, int]:
    vals = [aod.get(day + timedelta(days=sign * k)) for k in range(1, WINDOW + 1)]
    vals = [v for v in vals if v is not None and v > 0]
    return (float(np.mean(vals)) if vals else None), len(vals)


def compute_interaction(*, region_id: str, season: str, rain_daily: dict[date, float | None],
                        aod_daily: dict[date, float | None], rain_monthly: dict[date, float | None],
                        aod_monthly: dict[date, float | None], period: dict[str, str],
                        source_ids: dict[str, str]) -> dict[str, Any]:
    months = set(SEASON_MONTHS[season])
    in_season = sorted(d for d, v in rain_daily.items() if v is not None and d.month in months)
    threshold = float(np.percentile([rain_daily[d] for d in in_season], 90))
    events: list[date] = []
    for d in in_season:
        if rain_daily[d] >= threshold and (not events or (d - events[-1]).days >= SEPARATION):
            events.append(d)
    aod = {d: v for d, v in aod_daily.items() if v is not None}
    before_means, after_means, changes = [], [], []
    valid_before = valid_after = 0
    for e in events:
        b, nb = _window_mean(aod, e, -1)
        a, na = _window_mean(aod, e, +1)
        valid_before += nb
        valid_after += na
        if b is not None and a is not None:
            before_means.append(b)
            after_means.append(a)
            changes.append(a - b)
    n_events, n_used = len(events), len(changes)
    rng = np.random.default_rng(SEED)
    # Controls: up to five random non-event days per used event, same calendar month and year,
    # at least three days away from every event.
    event_set = set(events)
    near = {e + timedelta(days=k) for e in events for k in range(-WINDOW, WINDOW + 1)}
    control_changes = []
    for e in events:
        b, _ = _window_mean(aod, e, -1)
        a, _ = _window_mean(aod, e, +1)
        if b is None or a is None:
            continue
        pool = [d for d in in_season if d.year == e.year and d.month == e.month and d not in near and d not in event_set]
        if not pool:
            continue
        pick = rng.choice(len(pool), size=min(CONTROLS_PER_EVENT, len(pool)), replace=False)
        for i in sorted(pick):
            cb, _ = _window_mean(aod, pool[i], -1)
            ca, _ = _window_mean(aod, pool[i], +1)
            if cb is not None and ca is not None:
                control_changes.append(ca - cb)
    enough = n_used >= MIN_EVENTS
    diffs = np.array(changes)
    if enough:
        boots = np.median(rng.choice(diffs, size=(BOOTSTRAP, n_used), replace=True), axis=1)
        ci = [round(float(np.percentile(boots, 2.5)), 6), round(float(np.percentile(boots, 97.5)), 6)]
        p = round(wilcoxon_signed_rank(diffs), 8)
    else:
        ci, p = None, None
    # Monthly association on deseasonalised anomalies (calendar-month means removed), season months only.
    common = sorted(d for d in rain_monthly if rain_monthly[d] is not None and aod_monthly.get(d) is not None and d.month in months)
    clim_r = {m: np.mean([rain_monthly[d] for d in common if d.month == m]) for m in months}
    clim_a = {m: np.mean([aod_monthly[d] for d in common if d.month == m]) for m in months}
    xr = np.array([rain_monthly[d] - clim_r[d.month] for d in common])
    xa = np.array([aod_monthly[d] - clim_a[d.month] for d in common])
    rho, rho_p = spearman(xr, xa) if len(common) >= 4 else (None, None)
    pct = (lambda v: None if n_events == 0 else round(100 * v / (n_events * WINDOW), 2))
    med = (lambda xs: None if n_used == 0 else round(float(np.median(xs)), 6))
    return {
        "result_id": f"interaction_{region_id}_{season}_{period['start']}_{period['end']}", "region_id": region_id,
        "season": season, "period": period, "source_ids": source_ids,
        "event_definition": {"rain_threshold": "seasonal_p90_of_daily_regional_mean", "threshold_period": period,
                             "min_separation_days": SEPARATION, "window_days": WINDOW, "event_day_excluded": True,
                             "min_valid_aod_days_per_window": 1},
        "status": "ok" if enough else "too_few_events", "note": None if enough else TOO_FEW,
        "n_events": n_events, "n_events_used": n_used,
        "valid_aod_pct_before": pct(valid_before), "valid_aod_pct_after": pct(valid_after),
        "aod_before_median": med(before_means), "aod_after_median": med(after_means), "median_change": med(changes),
        "median_change_ci": ci, "ci_level": 0.95, "ci_method": "bootstrap", "test": "wilcoxon_signed_rank", "p_value": p,
        "control": {"method": "random_non_event_days_same_month", "n": len(control_changes),
                    "median_change": round(float(np.median(control_changes)), 6) if control_changes else None},
        "monthly_association": {"method": "spearman_on_deseasonalised_anomalies",
                                "rho": None if rho is None else round(rho, 6), "n": len(common),
                                "p_value": None if rho_p is None else round(rho_p, 8)},
        "guardrail": GUARDRAIL,
        "_threshold_mm_day": round(threshold, 4),
    }
