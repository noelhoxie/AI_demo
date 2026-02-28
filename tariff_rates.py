"""
US tariff rate by country of origin (simplified for COGS / landed cost).
Used to compute tariff amount and total cost (COGS) on purchase orders.
Rates are illustrative defaults; production systems may use HTS/product-specific rates.
"""
from typing import Dict

# Default tariff rate (%) when country is not in the map
DEFAULT_TARIFF_PCT = 5.0

# Country name (as in PO data) -> typical US tariff rate % (0 = FTA/preferential, 25 = Section 301, etc.)
COUNTRY_TARIFF_PCT: Dict[str, float] = {
    "China": 25.0,
    "Mexico": 0.0,
    "Canada": 0.0,
    "South Korea": 0.0,
    "Australia": 0.0,
    "Chile": 0.0,
    "Colombia": 0.0,
    "Israel": 0.0,
    "Japan": 2.5,
    "United Kingdom": 2.5,
    "Germany": 2.5,
    "France": 2.5,
    "Italy": 2.5,
    "Spain": 2.5,
    "Netherlands": 2.5,
    "Belgium": 2.5,
    "Austria": 2.5,
    "Sweden": 2.5,
    "Ireland": 2.5,
    "Portugal": 2.5,
    "Poland": 2.5,
    "Czech Republic": 2.5,
    "Hungary": 2.5,
    "Romania": 2.5,
    "Slovakia": 2.5,
    "Switzerland": 2.5,
    "Vietnam": 8.0,
    "India": 5.0,
    "Taiwan": 4.0,
    "Thailand": 5.0,
    "Malaysia": 5.0,
    "Indonesia": 5.0,
    "Brazil": 6.0,
    "Turkey": 5.0,
    "South Africa": 4.0,
    "Argentina": 6.0,
}


def get_tariff_rate_pct(country: str) -> float:
    """Return tariff rate (percent) for a country. Empty/missing country uses default."""
    if not country or not str(country).strip():
        return DEFAULT_TARIFF_PCT
    return COUNTRY_TARIFF_PCT.get(str(country).strip(), DEFAULT_TARIFF_PCT)


def enrich_procurement_with_tariff(procurement: list) -> list:
    """
    Add tariff_rate_pct, tariff_amount, total_cost (COGS) to each PO.
    total_cost = value + tariff_amount; tariff_amount = value * (tariff_rate_pct / 100).
    """
    out = []
    for r in list(procurement):
        row = dict(r)
        base_value = float(row.get("value") or 0)
        country = (row.get("country") or "").strip()
        rate_pct = get_tariff_rate_pct(country)
        tariff_amount = round(base_value * (rate_pct / 100.0), 2)
        total_cost = round(base_value + tariff_amount, 2)
        row["tariffRatePct"] = rate_pct
        row["tariffAmount"] = tariff_amount
        row["totalCost"] = total_cost
        out.append(row)
    return out
