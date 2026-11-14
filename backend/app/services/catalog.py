"""Variable catalogue, guided discovery questions and region presets.

Discovery is a transparent rule-based recommender (no black-box model): each suggestion
lists the exact reasons it scored, so a student can see *why* a variable is suggested for
a desert, a rain forest, a tidal estuary or the air above a large city.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from ..config import REPO_ROOT
from ..errors import api_error

CATALOG_PATH = REPO_ROOT / "data" / "catalog" / "variables_catalog.json"

# Everyday words -> catalogue variables. Matching is on whole words, case-insensitive.
KEYWORDS: dict[str, list[str]] = {
    "pollution": ["no2", "aod", "so2"], "polluted": ["no2", "aod"], "smog": ["aod", "no2"], "haze": ["aod", "aod_merra2"],
    "hazy": ["aod"], "traffic": ["no2"], "cars": ["no2"], "industry": ["no2", "so2", "aod"], "coal": ["so2", "aod"],
    "smoke": ["uv_aerosol_index", "aod"], "fire": ["uv_aerosol_index", "aod", "ndvi"], "fires": ["uv_aerosol_index", "aod", "ndvi"],
    "wildfire": ["uv_aerosol_index", "aod", "ndvi"], "dust": ["aod", "uv_aerosol_index"],
    "drought": ["soil_moisture", "rainfall", "ndvi", "tws_anomaly", "evapotranspiration"], "dry": ["soil_moisture", "rainfall"],
    "rain": ["rainfall"], "rainfall": ["rainfall"], "monsoon": ["rainfall", "water_vapor_airs"], "flood": ["rainfall", "surface_runoff"],
    "floods": ["rainfall", "surface_runoff"], "storm": ["rainfall", "water_vapor_airs"], "heat": ["air_temperature", "land_surface_temperature"],
    "hot": ["air_temperature", "land_surface_temperature"], "warming": ["air_temperature", "surface_air_temperature_airs", "sea_surface_temperature"],
    "temperature": ["air_temperature", "land_surface_temperature", "surface_air_temperature_airs"],
    "groundwater": ["tws_anomaly"], "aquifer": ["tws_anomaly"], "irrigation": ["tws_anomaly", "evapotranspiration", "ndvi", "soil_moisture"],
    "snow": ["snow_cover", "snow_water_equivalent"], "glacier": ["snow_cover", "snow_water_equivalent"], "ice": ["snow_cover"],
    "forest": ["ndvi", "land_surface_temperature"], "deforestation": ["ndvi", "land_surface_temperature", "uv_aerosol_index"],
    "trees": ["ndvi"], "green": ["ndvi"], "crops": ["ndvi", "soil_moisture", "evapotranspiration"], "farm": ["ndvi", "soil_moisture"],
    "farming": ["ndvi", "soil_moisture", "evapotranspiration"], "ozone": ["ozone_total"], "uv": ["ozone_total"],
    "river": ["surface_runoff", "rainfall"], "streamflow": ["surface_runoff"], "evaporation": ["evapotranspiration"],
    "plankton": ["chlorophyll_a"], "algae": ["chlorophyll_a"], "ocean": ["sea_surface_temperature", "chlorophyll_a"],
    "sea": ["sea_surface_temperature", "chlorophyll_a"], "coral": ["sea_surface_temperature"], "estuary": ["chlorophyll_a", "surface_runoff"],
    "humidity": ["water_vapor_airs"], "humid": ["water_vapor_airs"], "cloud": ["cloud_fraction"], "clouds": ["cloud_fraction"],
    "city": ["no2", "aod", "land_surface_temperature"], "urban": ["no2", "land_surface_temperature", "aod"],
}

QUESTIONS = [
    {"id": "theme", "question": "What part of the Earth system are you curious about?", "type": "choice", "required": False,
     "choices_from": "themes", "help": "Pick one, or skip to see everything."},
    {"id": "place_type", "question": "What kind of place do you want to investigate?", "type": "choice", "required": False,
     "choices_from": "place_types", "help": "Deserts, rain forests, estuaries and big cities change in different ways."},
    {"id": "question", "question": "In your own words, what do you want to find out?", "type": "text", "required": False,
     "help": "For example: 'Is the air in my city getting more polluted?' or 'Is the snow melting earlier?'"},
    {"id": "region_id", "question": "Do you already have a region in mind?", "type": "choice", "required": False,
     "choices_from": "regions", "help": "Choose a loaded region, or a preset to download data for."},
]


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _loaded_variables(store) -> set[str]:
    try:
        return {v.variable for v in store.variables()}
    except Exception:  # noqa: BLE001 - a store without metadata simply has nothing loaded
        return set()


def catalog_for(store) -> dict[str, Any]:
    raw = load_catalog()
    loaded = _loaded_variables(store)
    variables = [{**v, "available_now": v["id"] in loaded} for v in raw["variables"]]
    return {"catalog_version": raw["catalog_version"], "note": raw["note"], "themes": raw["themes"],
            "place_types": raw["place_types"], "variables": variables, "region_presets": raw["region_presets"]}


def questions_for(store) -> dict[str, Any]:
    raw = load_catalog()
    try:
        regions = [{"id": r.region_id, "name": r.name, "loaded": True} for r in store.regions().regions]
    except Exception:  # noqa: BLE001
        regions = []
    loaded_ids = {r["id"] for r in regions}
    regions += [{"id": p["id"], "name": p["name"], "loaded": False} for p in raw["region_presets"] if p["id"] not in loaded_ids]
    return {"questions": QUESTIONS, "choices": {"themes": raw["themes"], "place_types": raw["place_types"], "regions": regions}}


def discover(store, *, theme: str | None, place_type: str | None, question: str | None,
             region_id: str | None, limit: int = 6) -> dict[str, Any]:
    raw = load_catalog()
    if theme is not None and theme not in raw["themes"]:
        raise api_error("VALIDATION_ERROR", "Unknown theme.", {"param": "theme", "allowed": list(raw["themes"])})
    if place_type is not None and place_type not in raw["place_types"]:
        raise api_error("VALIDATION_ERROR", "Unknown place type.", {"param": "place_type", "allowed": list(raw["place_types"])})
    loaded = _loaded_variables(store)
    try:
        store_regions = {r.region_id: r for r in store.regions().regions}
    except Exception:  # noqa: BLE001
        store_regions = {}
    presets = {p["id"]: p for p in raw["region_presets"]}
    if region_id is not None and region_id not in store_regions and region_id not in presets:
        raise api_error("INVALID_REGION", "Unknown region.", {"param": "region_id",
                                                               "allowed": sorted(set(store_regions) | set(presets))})
    words = set(re.findall(r"[a-z0-9]+", (question or "").lower()))
    hits = {w: KEYWORDS[w] for w in words if w in KEYWORDS}
    region_places = set(presets.get(region_id, {}).get("place_types", [])) if region_id else set()
    if region_id in store_regions and not region_places and region_id in presets:
        region_places = set(presets[region_id]["place_types"])
    scored = []
    for v in raw["variables"]:
        score, reasons = 0, []
        if theme and theme in v["themes"]:
            score += 3
            reasons.append(f"Part of the '{theme}' theme you chose.")
        places = set(v["place_types"])
        if place_type and place_type in places:
            score += 3
            reasons.append(f"Known to change in {raw['place_types'][place_type].lower()} settings.")
        elif place_type and "any" in places:
            score += 1
        for place in sorted(region_places & places):
            score += 1
            reasons.append(f"The selected region is a {raw['place_types'][place].lower()} setting.")
            break
        matched = sorted(w for w, ids in hits.items() if v["id"] in ids)
        if matched:
            score += 2 * len(matched)
            reasons.append("Matches your words: " + ", ".join(f"'{w}'" for w in matched) + ".")
        if v["id"] in loaded:
            score += 1
            reasons.append("Already loaded: you can analyse it right now.")
        if not (theme or place_type or hits or region_places):
            score = 1 + (v["id"] in loaded)
        if score > 0:
            scored.append((score, v, reasons))
    scored.sort(key=lambda s: (-s[0], not (s[1]["id"] in loaded), s[1]["name"]))
    suggestions = []
    for score, v, reasons in scored[:limit]:
        available = v["id"] in loaded
        if available:
            # Only suggest a region that actually holds this variable (the chosen one if it does).
            holders = [rid for rid, r in store_regions.items() if v["id"] in r.variables]
            target = region_id if region_id in holders else (holders[0] if holders else None)
            next_step = {"action": "analyze", "method": "POST", "path": "/api/v1/analyze/detail",
                         "body": {"region_id": target, "variable": v["id"], "season": "all"}}
        else:
            next_step = {"action": "download_then_analyze",
                         "how": ("In Giovanni choose 'Time Series, Area-Averaged', monthly, your region box, "
                                 f"variable {v['giovanni_id'] or v['product'] + ' / ' + v['field']}; download CSV; "
                                 "then POST it to /api/v1/analyze/series as giovanni_csv."),
                         "giovanni_id": v["giovanni_id"]}
        suggestions.append({"variable_id": v["id"], "name": v["name"], "score": score, "reasons": reasons,
                            "plain_definition": v["plain_definition"], "why_trends": v["why_trends"],
                            "mission": v["mission"], "instrument": v["instrument"], "unit": v["unit"],
                            "caveat": v["caveat"], "available_now": available,
                            "suggested_season": "all (seasonal cycle removed)" if v["seasonal_cycle"] == "strong" else "all",
                            "next_step": next_step})
    region_suggestions = [p for p in raw["region_presets"] if place_type and place_type in p["place_types"]][:4]
    tips = ["Trends need long records: aim for at least 10 years of monthly data.",
            "Compare two regions: the same process can push a variable up in one place and down in another."]
    return {"inputs": {"theme": theme, "place_type": place_type, "question": question, "region_id": region_id},
            "matched_keywords": sorted(hits), "suggestions": suggestions,
            "region_suggestions": region_suggestions, "tips": tips}
