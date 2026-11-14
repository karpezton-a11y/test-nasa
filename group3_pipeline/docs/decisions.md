# Decisions and unresolved agreements

Source authority: the original Group 3 assignment and Aadarsh's 42-page handbook describe team proposals. No new agreement with Aadarsh is implied by this package.

Current implementation uses a proposed V07 Final pipeline because that is the product shown in the user's Giovanni selection and the original plan. A switch to V08 Final requires verification of full historical coverage, metadata and joint agreement; never splice versions.

The nine original CSV fields remain canonical. data_version, method and coverage definitions are sidecar metadata until Group 1 agrees Aadarsh's proposed extra CSV columns. Exact source identifiers follow the original assignment. Changing an existing frozen contract requires a version update.

Proposed algorithm conventions now explicit in code: linear quantiles, sample-SD log AOD, 15 eligible same-month baseline observations, suppression of tied rainfall thresholds, season-specific wet-day P95, strict above-P95 numerator, missing days interrupt spells and >=95% year/season completeness. Aadarsh must review these implementation choices before scientific use.

Exact CSV headers, fill values, product identities, selected boxes and included grid centres have now been recorded from twelve real exports. Daily/monthly pairings are explicit in inputs.json. The exact spatial weighting and valid-cell coverage still require review.

Unresolved: team approval of the geographic mask and product pairings; raw p versus adjusted q for labels; required sensitivity set; gap-aware modified MK procedure; autocorrelation-aware uncertainty; optional detrended anomaly implementation.

