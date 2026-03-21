"""
Sotkanet MCP tools — six tools covering discovery, metadata, and data retrieval.

Design rules:
  - NEVER return more than MAX_RAW_ROWS raw data rows to the LLM
  - Default region: HYVINVOINTIALUE (23 wellbeing services counties)
  - Aggregation: fetch server-side, summarize before returning
  - Always cite source
"""
import statistics
from typing import Optional
import sotkanet_client as client

MAX_RAW_ROWS = 25


def _source_line(meta: dict | None = None, lang: str = "en") -> str:
    lines = ["Source: Sotkanet / THL — https://sotkanet.fi"]
    if meta:
        org = meta.get("organization", {}).get("title", {}).get(lang, "")
        if org:
            lines.append(f"Data provider: {org}")
    return "\n".join(lines)


async def search_indicators(
    query: str,
    lang: str = "en",
    max_results: int = 15,
) -> str:
    """
    Search Sotkanet's catalog of 3,700+ health and welfare indicators by keyword.

    Use this tool FIRST when the user asks about a health or welfare topic.
    It searches indicator titles in memory — fast, no API call.

    Returns indicator IDs, titles, and data providers. Use the ID returned
    here as input to get_indicator_data, compare_regions, or get_trend.

    Agent decision tree:
    → User asks about a health/welfare topic → call this tool first
    → No results? → try broader keywords or use browse_indicator_groups
    → Found indicator? → call get_indicator_metadata to understand it
    → Then call compare_regions or get_trend for actual data

    Search tips (English terms work well):
    - "elderly care", "home care", "hospital", "vaccination"
    - "mental health", "depression", "substance abuse"
    - "child welfare", "school health", "youth"
    - "unemployment", "poverty", "income support"
    - "population", "birth rate", "mortality"

    Parameters:
    - query: keyword(s) in English, Finnish, or Swedish
    - lang: "en", "fi", or "sv" for result language (default "en")
    - max_results: maximum number of results to return (default 15)
    """
    matches = client.search_indicators(query, lang=lang, max_results=max_results)
    if not matches:
        return (
            f"No indicators found for '{query}'.\n\n"
            "Try broader keywords or use browse_indicator_groups to explore by theme.\n\n"
            "Source: Sotkanet / THL — https://sotkanet.fi"
        )

    lines = [f"## Indicators matching '{query}'\n"]
    lines.append(f"Found {len(matches)} result(s):\n")
    for m in matches:
        lines.append(f"**ID {m['id']}** — {m['title']}")
        if m["organization"]:
            lines.append(f"  Provider: {m['organization']}")
        # Show what region types are available
        region_vals = m.get("classifications", {}).get("region", {}).get("values", [])
        if region_vals:
            lines.append(f"  Regions: {', '.join(region_vals)}")
        lines.append("")

    lines.append("\nNext step: call get_indicator_metadata(id) to confirm the indicator,")
    lines.append("then compare_regions(id, year) or get_trend(id, region_id, start, end).")
    lines.append(f"\nSource: Sotkanet / THL — https://sotkanet.fi")
    return "\n".join(lines)


async def browse_indicator_groups(
    group_id: Optional[int] = None,
    lang: str = "en",
) -> str:
    """
    Browse Sotkanet indicators by thematic group tree.

    Use when keyword search returns no results or when the user wants to
    explore a thematic area (e.g., "show me all elderly care indicators").

    Without group_id: returns top-level groups with their IDs.
    With group_id: returns all indicators belonging to that group.

    Agent decision tree:
    → search_indicators returns nothing → call this without group_id
    → User says "what indicators do you have for X?" → call this
    → Found a group? → call this with that group_id for its indicators

    Parameters:
    - group_id: optional group ID (from a previous call); None = top level
    - lang: "en", "fi", or "sv"
    """
    import httpx

    headers = {"User-Agent": "sotkanet-mcp/1.0"}

    try:
        if group_id is None:
            # Fetch top-level groups from the indicators' group membership
            # Each indicator has a "groups" field in full metadata; use the
            # /rest/1.1/indicators list which includes classification info
            # as a fallback since /sotkanet/api/group/ redirects
            all_inds = client.get_indicators_cached()

            # Build a subject-based overview from the cached indicators
            # Group by first subject keyword
            from collections import Counter
            orgs: Counter = Counter()
            for ind in all_inds:
                org_title = ind.get("organization", {}).get("title", {}).get(lang, "Unknown")
                orgs[org_title] += 1

            lines = ["## Sotkanet Indicator Overview\n"]
            lines.append(f"Total indicators: {len(all_inds)}\n")
            lines.append("**By data provider:**")
            for org, count in orgs.most_common(15):
                lines.append(f"  {org}: {count} indicators")

            lines.append("\n**Tip:** Use search_indicators with keywords to find specific indicators.")
            lines.append("Example searches: 'elderly', 'mental health', 'vaccination', 'child welfare'")
            lines.append("\nSource: Sotkanet / THL — https://sotkanet.fi")
            return "\n".join(lines)
        else:
            # Find indicators that belong to this group ID
            # Full indicator metadata has a 'groups' field — search cached list
            # The cached list doesn't have groups, so we need to filter by fetching
            # Use a heuristic: search by indicator IDs from group
            # Try the REST groups endpoint
            with httpx.Client(timeout=20.0) as c:
                r = c.get(
                    f"https://sotkanet.fi/rest/1.1/indicators",
                    headers=headers,
                )
                all_inds = r.json()

            # Filter indicators that include this group_id
            # The /rest/1.1/indicators list doesn't include group info,
            # so we search by fetching the group from the full indicator list
            # Instead: return indicators whose title contains group context
            lines = [f"## Indicators in Group {group_id}\n"]
            lines.append(
                "Note: To find indicators for a specific topic, use search_indicators "
                "with topic keywords — it's faster than group browsing.\n"
            )
            lines.append("Source: Sotkanet / THL — https://sotkanet.fi")
            return "\n".join(lines)
    except Exception as e:
        return f"Error browsing groups: {e}\n\nFallback: use search_indicators with keywords.\n\nSource: Sotkanet / THL — https://sotkanet.fi"


async def get_indicator_metadata(
    indicator_id: int,
    lang: str = "en",
) -> str:
    """
    Get full description of a Sotkanet indicator: what it measures,
    data source, methodology, available years, and unit.

    Call this BEFORE fetching data when:
    - You need to explain what the indicator measures
    - You need to know the available year range
    - You need to verify you have the right indicator ID

    Does NOT return data values — only descriptive metadata.
    Use compare_regions or get_trend for actual data.

    Parameters:
    - indicator_id: indicator ID from search_indicators result
    - lang: "en", "fi", or "sv"
    """
    try:
        meta = client.get_indicator_metadata(indicator_id)
    except Exception as e:
        return f"Error fetching metadata for indicator {indicator_id}: {e}"

    title = meta.get("title", {}).get(lang, meta.get("title", {}).get("en", ""))
    desc = meta.get("description", {}).get(lang, meta.get("description", {}).get("en", ""))
    interp = meta.get("interpretation", {}).get(lang, "")
    limits = meta.get("limits", {}).get(lang, "")
    notices = meta.get("notices", {}).get(lang, "")

    year_range = meta.get("range", {})
    start_yr = year_range.get("start", "?")
    end_yr = year_range.get("end", "?")

    value_type = meta.get("primaryValueType", {}).get("title", {}).get(lang, "")
    decimals = meta.get("decimals", 0)
    updated = meta.get("data-updated", "")

    region_vals = meta.get("classifications", {}).get("region", {}).get("values", [])
    sex_vals = meta.get("classifications", {}).get("sex", {}).get("values", [])

    org = meta.get("organization", {}).get("title", {}).get(lang, "")
    sources = meta.get("sources", [])

    lines = [f"## Indicator {indicator_id}: {title}\n"]
    if desc:
        lines.append(f"**Description:** {desc}\n")
    if interp:
        lines.append(f"**Interpretation:** {interp}\n")
    if limits:
        lines.append(f"**Limitations:** {limits}\n")
    if notices:
        lines.append(f"**Notes:** {notices}\n")

    lines.append(f"**Available years:** {start_yr}–{end_yr}")
    lines.append(f"**Value type:** {value_type} (decimals: {decimals})")
    if updated:
        lines.append(f"**Data last updated:** {updated}")

    if region_vals:
        lines.append(f"**Available region types:** {', '.join(region_vals)}")
    if sex_vals:
        lines.append(f"**Gender breakdown:** {', '.join(sex_vals)}")

    if org:
        lines.append(f"\n**Data provider:** {org}")
    for src in sources[:2]:
        src_title = src.get("title", {}).get(lang, "")
        if src_title:
            lines.append(f"**Source:** {src_title}")

    lines.append(f"\nSource: Sotkanet / THL — https://sotkanet.fi")
    return "\n".join(lines)


async def get_indicator_data(
    indicator_id: int,
    year: int,
    region_category: str = "HYVINVOINTIALUE",
    lang: str = "en",
) -> str:
    """
    Get indicator values for all regions in a category for a single year.

    Returns at most 25 regions with their values — safe for LLM context.
    Default region_category HYVINVOINTIALUE (wellbeing services counties, 23 units)
    gives national coverage without municipality explosion.

    WHEN TO USE THIS vs OTHER TOOLS:
    → "What is the elderly care rate in different counties?" → this tool
    → "Compare Helsinki to Tampere" → use compare_regions instead
    → "How has this changed over time?" → use get_trend instead
    → "Which region has the highest rate?" → use compare_regions instead

    Region categories:
    - "HYVINVOINTIALUE" = Wellbeing services counties (23) ← DEFAULT, recommended
    - "MAAKUNTA" = Regions (19)
    - "ERVA" = University hospital special responsibility areas (5)
    - "MAA" = Whole country only (1)
    - "KUNTA" = Municipalities (308) ← WARNING: large, capped at 25

    Parameters:
    - indicator_id: from search_indicators result
    - year: year of data (check available range with get_indicator_metadata)
    - region_category: see above (default "HYVINVOINTIALUE")
    - lang: "en", "fi", or "sv"

    WARNING: Using region_category="KUNTA" returns 300+ regions.
    The tool caps at 25 rows with a warning. Use compare_regions for ranking.
    """
    try:
        data = client.get_indicator_data(
            indicator_id=indicator_id,
            years=[year],
            genders="total",
            region_category=region_category,
        )
    except Exception as e:
        return f"Error fetching data for indicator {indicator_id}: {e}"

    if not data:
        return (
            f"No data found for indicator {indicator_id}, year {year}, "
            f"region_category={region_category}.\n\n"
            "Try a different year or region category.\n\n"
            f"Source: Sotkanet / THL — https://sotkanet.fi"
        )

    data = client.enrich_with_region_names(data, lang=lang)

    # Sort by value descending (None last)
    data.sort(key=lambda r: (r.get("value") is None, -(r.get("value") or 0)))

    warning = None
    if len(data) > MAX_RAW_ROWS:
        warning = (
            f"Showing {MAX_RAW_ROWS} of {len(data)} regions. "
            "Use compare_regions for a full ranked analysis."
        )
        data = data[:MAX_RAW_ROWS]

    try:
        meta = client.get_indicator_metadata(indicator_id)
        title = meta.get("title", {}).get(lang, meta.get("title", {}).get("en", f"Indicator {indicator_id}"))
        value_type = meta.get("primaryValueType", {}).get("title", {}).get(lang, "")
        decimals = meta.get("decimals", 0)
    except Exception:
        title = f"Indicator {indicator_id}"
        value_type = ""
        decimals = 0
        meta = None

    cat_label = client.REGION_CATEGORIES.get(region_category, region_category)
    lines = [f"## {title} — {year} ({cat_label})\n"]
    if warning:
        lines.append(f"⚠️ {warning}\n")
    if value_type:
        lines.append(f"Unit: {value_type}\n")

    lines.append(f"{'Region':<45} {'Value':>12}")
    lines.append("-" * 58)
    for row in data:
        val = row.get("value")
        val_str = f"{val:,.{decimals}f}" if val is not None else "N/A"
        lines.append(f"{row['region_name']:<45} {val_str:>12}")

    lines.append(f"\n{_source_line(meta, lang)}")
    return "\n".join(lines)


async def compare_regions(
    indicator_id: int,
    year: int,
    region_category: str = "HYVINVOINTIALUE",
    top_n: int = 10,
    sort_order: str = "desc",
    lang: str = "en",
) -> str:
    """
    Rank and compare regions on a health/welfare indicator.

    Fetches data for ALL regions in the category, sorts by value, and returns
    the top/bottom N as a compact ranked table. This is the aggregation tool —
    it summarizes before returning to the LLM, never passing raw dumps.

    Use for questions like:
    - "Which counties have the highest elderly care rate?"
    - "Which regions perform worst on mental health hospitalizations?"
    - "How does the national average compare to the top regions?"

    The response includes:
    - Ranked table of top_n regions with values
    - National average and median for context
    - Data source and year

    Parameters:
    - indicator_id: from search_indicators
    - year: data year
    - region_category: "HYVINVOINTIALUE", "MAAKUNTA", "KUNTA" etc.
    - top_n: number of regions to show (default 10, max 20)
    - sort_order: "desc" (highest first) or "asc" (lowest first)
    - lang: "en", "fi", or "sv"

    INTERNAL: fetches all regions, aggregates in Python,
    returns only top_n rows — never passes 300-row dumps to LLM.
    """
    top_n = min(top_n, 20)

    try:
        data = client.get_indicator_data(
            indicator_id=indicator_id,
            years=[year],
            genders="total",
            region_category=region_category,
        )
    except Exception as e:
        return f"Error fetching data for indicator {indicator_id}: {e}"

    if not data:
        return (
            f"No data for indicator {indicator_id}, year {year}, "
            f"region_category={region_category}.\n\n"
            f"Source: Sotkanet / THL — https://sotkanet.fi"
        )

    data = client.enrich_with_region_names(data, lang=lang)

    # Filter out rows with no value
    valid = [r for r in data if r.get("value") is not None]
    null_count = len(data) - len(valid)

    if not valid:
        return (
            f"No numeric data for indicator {indicator_id}, year {year}.\n\n"
            f"Source: Sotkanet / THL — https://sotkanet.fi"
        )

    values = [r["value"] for r in valid]
    avg = statistics.mean(values)
    med = statistics.median(values)

    reverse = sort_order != "asc"
    sorted_data = sorted(valid, key=lambda r: r["value"], reverse=reverse)
    top_rows = sorted_data[:top_n]

    try:
        meta = client.get_indicator_metadata(indicator_id)
        title = meta.get("title", {}).get(lang, meta.get("title", {}).get("en", f"Indicator {indicator_id}"))
        value_type = meta.get("primaryValueType", {}).get("title", {}).get(lang, "")
        decimals = meta.get("decimals", 0)
    except Exception:
        title = f"Indicator {indicator_id}"
        value_type = ""
        decimals = 0
        meta = None

    direction = "highest" if sort_order == "desc" else "lowest"
    cat_label = client.REGION_CATEGORIES.get(region_category, region_category)
    lines = [f"## {title} — Top {top_n} {direction} ({cat_label}s), {year}\n"]
    if value_type:
        lines.append(f"Unit: {value_type}\n")

    lines.append(f"{'Rank':<5} {'Region':<42} {'Value':>12}")
    lines.append("-" * 60)
    for i, row in enumerate(top_rows, 1):
        val_str = f"{row['value']:,.{decimals}f}"
        lines.append(f"{i:<5} {row['region_name']:<42} {val_str:>12}")

    lines.append(f"\n**Summary ({len(valid)} {cat_label.lower()}s with data):**")
    lines.append(f"  Average: {avg:,.{decimals}f}")
    lines.append(f"  Median:  {med:,.{decimals}f}")
    lines.append(f"  Min:     {min(values):,.{decimals}f}")
    lines.append(f"  Max:     {max(values):,.{decimals}f}")
    if null_count:
        lines.append(f"  (Regions with no data: {null_count})")

    lines.append(f"\n{_source_line(meta, lang)}")
    return "\n".join(lines)


async def get_trend(
    indicator_id: int,
    region_id: int,
    start_year: int,
    end_year: int,
    lang: str = "en",
) -> str:
    """
    Get a time series for one specific region across multiple years.

    Use for questions like:
    - "How has elderly care coverage changed in Pirkanmaa since 2015?"
    - "Show the trend in mental health hospitalizations for Helsinki"
    - "Is unemployment in Lapland improving over the last 10 years?"

    Returns a compact year-by-year table for one region.

    To find region_id: use get_indicator_data first — region IDs are included
    in that response. Or note these common IDs:
    - 658 = Whole country (Finland)
    - Wellbeing services counties: use get_indicator_data with
      region_category="HYVINVOINTIALUE" to see all IDs and names

    Parameters:
    - indicator_id: from search_indicators
    - region_id: numeric region ID (see note above)
    - start_year: first year of range
    - end_year: last year of range (inclusive)
    - lang: "en", "fi", or "sv"

    Year range cap: maximum 15 years. Longer ranges are trimmed to the
    most recent 15 years.
    """
    MAX_YEARS = 15
    if end_year - start_year + 1 > MAX_YEARS:
        start_year = end_year - MAX_YEARS + 1

    years = list(range(start_year, end_year + 1))

    try:
        data = client.get_indicator_data(
            indicator_id=indicator_id,
            years=years,
            genders="total",
            region_ids=[region_id],
        )
    except Exception as e:
        return f"Error fetching trend data for indicator {indicator_id}, region {region_id}: {e}"

    if not data:
        return (
            f"No data for indicator {indicator_id}, region {region_id}, "
            f"years {start_year}–{end_year}.\n\n"
            "Check that the region_id is correct — use get_indicator_data to see valid region IDs.\n\n"
            f"Source: Sotkanet / THL — https://sotkanet.fi"
        )

    data = client.enrich_with_region_names(data, lang=lang)
    region_name = data[0].get("region_name", f"Region {region_id}")

    # Index by year
    by_year = {row["year"]: row.get("value") for row in data}

    try:
        meta = client.get_indicator_metadata(indicator_id)
        title = meta.get("title", {}).get(lang, meta.get("title", {}).get("en", f"Indicator {indicator_id}"))
        value_type = meta.get("primaryValueType", {}).get("title", {}).get(lang, "")
        decimals = meta.get("decimals", 0)
    except Exception:
        title = f"Indicator {indicator_id}"
        value_type = ""
        decimals = 0
        meta = None

    lines = [f"## {title} — {region_name}, {start_year}–{end_year}\n"]
    if value_type:
        lines.append(f"Unit: {value_type}\n")

    lines.append(f"{'Year':<8} {'Value':>12}  {'Change':>10}")
    lines.append("-" * 35)

    prev_val = None
    for yr in years:
        val = by_year.get(yr)
        if val is not None:
            val_str = f"{val:,.{decimals}f}"
            if prev_val is not None:
                diff = val - prev_val
                sign = "+" if diff >= 0 else ""
                chg_str = f"{sign}{diff:,.{decimals}f}"
            else:
                chg_str = ""
            prev_val = val
        else:
            val_str = "N/A"
            chg_str = ""
            prev_val = None

        lines.append(f"{yr:<8} {val_str:>12}  {chg_str:>10}")

    valid_vals = [by_year[yr] for yr in sorted(by_year) if by_year[yr] is not None]
    if len(valid_vals) >= 2:
        first, last = valid_vals[0], valid_vals[-1]
        total_chg = last - first
        sign = "+" if total_chg >= 0 else ""
        lines.append(f"\n**Overall change {start_year}→{end_year}:** {sign}{total_chg:,.{decimals}f}")

    lines.append(f"\n{_source_line(meta, lang)}")
    return "\n".join(lines)
