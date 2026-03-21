"""
Sotkanet REST API client.
Base: https://sotkanet.fi/rest/1.1/
No auth. No pagination on data endpoints.

CRITICAL SCALE FACTS (verified from probes):
  - /indicators returns 3,695 items, 2.45 MB — cache on startup, never re-fetch
  - /json data endpoint returns ALL regions for selected years
  - 1 year × all regions = ~467 rows — NEVER pass raw to LLM
  - Hard cap: data tools return max 25 raw rows
  - Aggregation tools fetch all rows server-side, summarize before returning

REGION CATEGORIES (from probe):
  KUNTA: 308 municipalities
  HYVINVOINTIALUE: 23 wellbeing services counties  ← DEFAULT
  MAAKUNTA: 19 regions
  SAIRAANHOITOPIIRI: 21 hospital districts
  ALUEHALLINTOVIRASTO: 7 regional state admin agencies
  SUURALUE: 5 major regions
  YTA: 6 collaborative areas
  ERVA: 5 university hospital special responsibility areas
  MAA: 1 (Whole country, id=658)
"""
import httpx
from typing import Optional

BASE = "https://sotkanet.fi/rest/1.1"
HEADERS = {"User-Agent": "sotkanet-mcp/1.0"}
TIMEOUT = 45.0

REGION_CATEGORIES = {
    "KUNTA": "Municipality",
    "HYVINVOINTIALUE": "Wellbeing services county",
    "MAAKUNTA": "Region",
    "SAIRAANHOITOPIIRI": "Hospital district",
    "ALUEHALLINTOVIRASTO": "Regional state administrative agency",
    "ERVA": "University hospital special responsibility area",
    "SUURALUE": "Major region",
    "YTA": "Collaborative area",
    "SEUTUKUNTA": "Sub-region",
    "MAA": "Whole country",
    "EUROOPPA": "Europe",
    "POHJOISMAAT": "Nordic countries",
}

# Whole country region ID (verified from probe: id=658, category=MAA)
WHOLE_COUNTRY_REGION_ID = 658

_indicator_cache: Optional[list] = None
_region_cache: Optional[list] = None


def _get(url: str, params: dict | None = None) -> httpx.Response:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        return r


def get_indicators_cached() -> list:
    """
    Returns ALL indicators. Cached after first call.
    Called once on server startup. Never called per-request.
    3,695 indicators, ~2.45 MB on the wire.
    """
    global _indicator_cache
    if _indicator_cache is None:
        r = _get(f"{BASE}/indicators")
        _indicator_cache = r.json()
    return _indicator_cache


def get_regions_cached() -> list:
    """Returns ALL regions. Cached after first call."""
    global _region_cache
    if _region_cache is None:
        r = _get(f"{BASE}/regions")
        _region_cache = r.json()
    return _region_cache


def search_indicators(query: str, lang: str = "en", max_results: int = 15) -> list:
    """
    Search indicator list by keyword. Runs against in-memory cache.
    Never makes an API call — all filtering is local.
    Returns list of {id, title, organization} dicts.
    """
    all_indicators = get_indicators_cached()
    query_lower = query.lower()
    matches = []
    for ind in all_indicators:
        title = ind.get("title", {}).get(lang, "")
        if query_lower in title.lower():
            matches.append({
                "id": ind["id"],
                "title": title,
                "organization": ind.get("organization", {}).get("title", {}).get(lang, ""),
                "classifications": ind.get("classifications", {}),
            })
    return matches[:max_results]


def get_indicator_metadata(indicator_id: int) -> dict:
    """Fetch full metadata for one indicator."""
    r = _get(f"{BASE}/indicators/{indicator_id}")
    return r.json()


def get_indicator_data(
    indicator_id: int,
    years: list[int],
    genders: str = "total",
    region_category: str | None = None,
    region_ids: list[int] | None = None,
) -> list:
    """
    Fetch data rows. Returns raw list of dicts.
    Caller is responsible for capping before returning to LLM.

    Multi-year: pass repeated years= params (e.g. years=2020&years=2021).
    If region_ids provided: filter to those regions only.
    If region_category provided: filter by category from region cache.
    """
    # Build params — repeated years= keys
    params = [("indicator", indicator_id), ("genders", genders)]
    for y in years:
        params.append(("years", y))

    r = _get(f"{BASE}/json", params=params)
    data = r.json()

    # Filter by region category or specific IDs
    if region_ids:
        id_set = set(region_ids)
        data = [d for d in data if d["region"] in id_set]
    elif region_category:
        regions = get_regions_cached()
        cat_ids = {reg["id"] for reg in regions if reg.get("category") == region_category}
        data = [d for d in data if d["region"] in cat_ids]

    return data


def enrich_with_region_names(data: list, lang: str = "en") -> list:
    """Add region_name to each data row. Runs against cached regions."""
    regions = get_regions_cached()
    region_map = {
        reg["id"]: reg.get("title", {}).get(lang, str(reg["id"]))
        for reg in regions
    }
    for row in data:
        row["region_name"] = region_map.get(row["region"], f"Region {row['region']}")
    return data
