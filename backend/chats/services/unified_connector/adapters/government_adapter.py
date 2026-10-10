from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
import requests

from backend.chats.services.unified_connector.models import (
    GovernmentMetadata,
    ResultCategory,
    StandardizedResult,
)
from backend.chats.services.web_search_service import perform_web_search

logger = logging.getLogger(__name__)

# World Bank Open Data API endpoints for official national indicators
WORLDBANK_API = "http://api.worldbank.org/v2/country/{country}/indicator/{indicator}?format=json&per_page=5"

INDICATOR_MAP = {
    "gdp": ("NY.GDP.MKTP.CD", "GDP (Current US$)", "World Bank National Accounts data"),
    "inflation": ("FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)", "International Monetary Fund / World Bank"),
    "population": ("SP.POP.TOTL", "Total Population", "United Nations Population Division"),
    "unemployment": ("SL.UEM.TOTL.ZS", "Unemployment, total (% of total labor force)", "International Labour Organization (ILO)"),
}


def fetch_government_data(query: str, limit: int = 4) -> List[StandardizedResult]:
    """
    Retrieve official open government statistics and public datasets.
    Supports World Bank indicators and Open Government Data (Data.gov.in / Data.gov) portals.
    """
    clean_q = (query or "").strip().lower()
    if not clean_q:
        return []

    results: List[StandardizedResult] = []

    # Detect country code (Default to India 'IND')
    country_code = "IND"
    if "usa" in clean_q or "united states" in clean_q:
        country_code = "USA"
    elif "uk" in clean_q or "united kingdom" in clean_q:
        country_code = "GBR"

    # 1. Check for official World Bank Open Data indicators
    for ind_key, (ind_id, ind_label, ind_source) in INDICATOR_MAP.items():
        if ind_key in clean_q:
            try:
                wb_url = WORLDBANK_API.format(country=country_code, indicator=ind_id)
                resp = requests.get(wb_url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) >= 2 and isinstance(data[1], list):
                        recent_entries = [d for d in data[1] if d.get("value") is not None]
                        if recent_entries:
                            latest = recent_entries[0]
                            val = latest.get("value")
                            year = latest.get("date")
                            formatted_val = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)

                            results.append(
                                StandardizedResult(
                                    id=f"wb_{ind_id}_{year}",
                                    category=ResultCategory.GOVERNMENT,
                                    title=f"Official {ind_label} ({country_code}) - {year}",
                                    description=f"Latest official government indicator value: {formatted_val}. Recorded for year {year}.",
                                    source="World Bank Open Data / Official Government Statistics",
                                    source_domain="data.worldbank.org",
                                    url=f"https://data.worldbank.org/indicator/{ind_id}?locations={country_code}",
                                    published_at=f"{year}-01-01",
                                    attribution=f"{ind_source} (CC-BY 4.0 Open License)",
                                    government=GovernmentMetadata(
                                        portal="World Bank Open Data",
                                        department="Development Data Group",
                                        dataset_id=ind_id,
                                        license_name="Creative Commons Attribution 4.0 (CC-BY 4.0)",
                                    ),
                                )
                            )
            except Exception as exc:
                logger.warning("World Bank indicator fetch error: %s", exc)

    # 2. Query Open Government Data (data.gov.in / data.gov) portals
    try:
        search_q = f"site:data.gov.in OR site:data.gov {clean_q} official dataset"
        hits = perform_web_search(search_q, max_results=4)
        for idx, hit in enumerate(hits):
            url = hit.get("url", "")
            title = hit.get("title", "")
            snip = hit.get("snippet", "")

            is_datagov_in = "data.gov.in" in url
            portal_name = "Data.gov.in (Open Government Data India)" if is_datagov_in else "Data.gov (U.S. Open Government)"

            results.append(
                StandardizedResult(
                    id=f"gov_data_{idx}_{hash(url) % 100000}",
                    category=ResultCategory.GOVERNMENT,
                    title=title,
                    description=snip,
                    source=portal_name,
                    source_domain="data.gov.in" if is_datagov_in else "data.gov",
                    url=url,
                    attribution="Open Government Data (OGD) License",
                    government=GovernmentMetadata(
                        portal=portal_name,
                        department="Government Open Data Initiative",
                        license_name="National Open Data License",
                    ),
                )
            )
    except Exception as exc:
        logger.warning("Government portal search exception: %s", exc)

    return results[:limit]
