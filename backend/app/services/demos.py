"""Watchable demonstration walkthroughs (challenge: 'a couple of demonstration examples').

Each demo is a short story: a question, the API calls a user (or the frontend's
'play demo' button) makes, narration for each step and what to notice. The first two
use the REAL annual NASA-derived series bundled in data/research; the rest use whatever
store is loaded (mock or real), and say so.
"""
from __future__ import annotations

from typing import Any

DEMOS: list[dict[str, Any]] = [
    {
        "id": "haze_rising",
        "title": "Is the air over India getting hazier?",
        "data": "real",
        "question": "Has aerosol optical depth (haze) changed over the Indo-Gangetic Plain and Tamil Nadu since 2003?",
        "steps": [
            {"narration": "Start with what AOD means: how much sunlight particles in the air block.",
             "method": "GET", "path": "/api/v1/catalog", "body": None, "look_at": "variables[id=aod].plain_definition"},
            {"narration": "Test 22 years of annual mean Aqua MODIS AOD for the Indo-Gangetic Plain.",
             "method": "POST", "path": "/api/v1/analyze/series", "body": {"research_id": "IGP_aod_annual_mean"},
             "look_at": "plain_language, sen_slope_per_decade, mk_p_value"},
            {"narration": "Repeat for the Tamil Nadu box, about 1,800 km further south.",
             "method": "POST", "path": "/api/v1/analyze/series", "body": {"research_id": "TN_aod_annual_mean"},
             "look_at": "percent_change_per_decade"},
        ],
        "what_to_notice": "Both boxes show a statistically significant rise. The southern box starts cleaner but rises "
                          "at a similar percentage rate. AOD is column haze, not ground-level PM2.5, and the test says "
                          "nothing about what caused the change.",
    },
    {
        "id": "not_significant_yet",
        "title": "A trend that is not significant (yet)",
        "data": "real",
        "question": "Is annual rainfall over the Indo-Gangetic Plain changing?",
        "steps": [
            {"narration": "Test annual rainfall totals from GPM IMERG, 2003-2024.",
             "method": "POST", "path": "/api/v1/analyze/series", "body": {"research_id": "IGP_rainfall_annual_total"},
             "look_at": "significant, sen_ci_per_decade"},
            {"narration": "The likely range includes zero. Check how many years would be needed to detect a trend this size.",
             "method": None, "path": None, "body": None, "look_at": "detection.years_needed vs detection.years_available"},
            {"narration": "Compare with a heavy-rain indicator in Tamil Nadu: closer, but still not significant.",
             "method": "POST", "path": "/api/v1/analyze/series", "body": {"research_id": "TN_heavy_rain_share"},
             "look_at": "mk_p_value, detection.additional_years"},
        ],
        "what_to_notice": "Not significant does not mean 'no change'. Rainfall is noisy, so a small trend needs decades "
                          "of data before it stands out from natural year-to-year swings.",
    },
    {
        "id": "seasons_matter",
        "title": "Remove the seasons before looking for a trend",
        "data": "store",
        "question": "Does the monsoon season trend the same way as the whole year?",
        "steps": [
            {"narration": "Analyse all months after removing the average seasonal cycle.",
             "method": "POST", "path": "/api/v1/analyze/detail",
             "body": {"region_id": "IGP", "variable": "aod", "season": "all"}, "look_at": "analysis.fit, trend.direction"},
            {"narration": "Now only the June-September monsoon, one seasonal mean per year.",
             "method": "POST", "path": "/api/v1/analyze/detail",
             "body": {"region_id": "IGP", "variable": "aod", "season": "JJAS"}, "look_at": "trend.sen_slope, trend.p_value"},
        ],
        "what_to_notice": "A raw monthly series is dominated by the seasons; the trend only appears once the seasonal "
                          "cycle is removed, and individual seasons can trend differently.",
    },
    {
        "id": "products_disagree",
        "title": "Two NASA products, two answers: always cross-check",
        "data": "store",
        "question": "Is rainfall over the Indo-Gangetic Plain increasing?",
        "steps": [
            {"narration": "Test GPM IMERG satellite rainfall, 2003-2024, with the seasons removed.",
             "method": "POST", "path": "/api/v1/analyze/detail",
             "body": {"region_id": "IGP", "variable": "rainfall", "season": "all"},
             "look_at": "trend.significant, trend.evidence.sensitivity"},
            {"narration": "Look at the sensitivity runs: the MERRA-2-based NASA POWER rainfall is tested the same way.",
             "method": None, "path": None, "body": None,
             "look_at": "trend.evidence.sensitivity[name=merra2_power_rainfall]"},
        ],
        "what_to_notice": "With real data, IMERG shows no significant trend while the model-based MERRA-2 rainfall "
                          "shows a significant rise. A trend that appears in only one product is weak evidence; the "
                          "evidence label stays 'weak' because the runs disagree.",
    },
    {
        "id": "two_cities_no2",
        "title": "Two cities, one satellite: nitrogen dioxide in Los Angeles and Delhi",
        "data": "store",
        "question": "Is NO2 pollution changing the same way in Los Angeles and Delhi?",
        "steps": [
            {"narration": "Scan OMI tropospheric NO2 for both city boxes, 2005-2024, with the seasons removed.",
             "method": "GET", "path": "/api/v1/scan?variable=no2", "body": None,
             "look_at": "rows[].headline, rows[].percent_change_per_decade"},
        ],
        "what_to_notice": "With the real data, Los Angeles NO2 falls by about half per decade while Delhi shows no "
                          "significant all-year trend. The app shows that the trends differ, not why. Open the map "
                          "(What's changing?, NO2) to see it at a glance.",
    },
    {
        "id": "scan_everything",
        "title": "What is changing, where, and how much?",
        "data": "store",
        "question": "Which loaded region-variable pairs show a significant trend?",
        "steps": [
            {"narration": "Test every region and variable at once, with a false-discovery-rate correction.",
             "method": "GET", "path": "/api/v1/scan?season=all", "body": None,
             "look_at": "summary, rows[].headline, opposite_directions"},
        ],
        "what_to_notice": "Testing many series at once raises the chance of a lucky 'significant' result; q-values "
                          "correct for that.",
    },
    {
        "id": "guided_discovery",
        "title": "Be a data detective: from a question to a variable",
        "data": "catalog",
        "question": "Is the air in my city getting more polluted?",
        "steps": [
            {"narration": "Answer the guided questions.", "method": "GET", "path": "/api/v1/discover/questions",
             "body": None, "look_at": "questions"},
            {"narration": "Get suggestions with reasons.", "method": "POST", "path": "/api/v1/discover",
             "body": {"place_type": "city", "theme": "air", "question": "Is the air in my city getting more polluted?"},
             "look_at": "suggestions[].reasons, suggestions[].next_step"},
        ],
        "what_to_notice": "Each suggestion says why it was chosen and how to get the data: analyse now if it is "
                          "loaded, or download a Giovanni area-averaged CSV and upload it.",
    },
]


def demos() -> list[dict[str, Any]]:
    return DEMOS
