"""
Tariff data from Data.gov (catalog) and USITC HTS.
Fetches the Harmonized Tariff Schedule dataset metadata from Data.gov and
a sample of tariff rates from the USITC CSV linked there.
Includes a 6-month forecast of average tariff rate for the bar chart.
"""
import csv
import io
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

log = logging.getLogger(__name__)

DATA_GOV_CATALOG = "https://catalog.data.gov/api/3/action/package_search"
REQUEST_TIMEOUT = 15
CSV_BYTE_LIMIT = 120_000  # first ~120KB of CSV for table sample
MAX_TABLE_ROWS = 150

# Bypass proxy for Data.gov (often blocked or broken by corporate proxies). Set DATA_GOV_NO_PROXY=1 to enable.
USE_NO_PROXY = os.environ.get("DATA_GOV_NO_PROXY", "").strip().lower() in ("1", "true", "yes")


def _data_gov_session() -> requests.Session:
    """Session that optionally skips proxy for Data.gov to avoid 403/tunnel errors."""
    s = requests.Session()
    if USE_NO_PROXY:
        s.trust_env = False
        s.proxies = {"http": "", "https": ""}
    return s


def _get_hts_dataset_from_catalog() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query Data.gov catalog for Harmonized Tariff Schedule; return (dataset dict or None, error message or None)."""
    def _do_request(skip_proxy: bool) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            if skip_proxy:
                s = requests.Session()
                s.trust_env = False
                s.proxies = {"http": "", "https": ""}
            else:
                s = _data_gov_session()
            r = s.get(
                DATA_GOV_CATALOG,
                params={"q": "harmonized tariff schedule united states", "rows": 1},
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("success") or not data.get("result", {}).get("results"):
                return None, "No datasets found for harmonized tariff schedule."
            pkg = data["result"]["results"][0]
            resources = pkg.get("resources") or []
            csv_url = None
            for res in resources:
                if (res.get("format") or "").upper() == "CSV" and res.get("url"):
                    name = (res.get("name") or "")
                    if "Revision" in name or "Basic" in name:
                        csv_url = res["url"]
                        break
            if not csv_url and resources:
                for res in resources:
                    if (res.get("format") or "").upper() == "CSV" and res.get("url"):
                        csv_url = res["url"]
                        break
            return {
                "title": pkg.get("title") or "Harmonized Tariff Schedule of the United States",
                "url": pkg.get("url") or "https://catalog.data.gov/dataset?q=harmonized+tariff",
                "csv_url": csv_url,
            }, None
        except requests.exceptions.ProxyError:
            raise
        except requests.exceptions.Timeout:
            return None, "Data.gov request timed out."
        except requests.exceptions.RequestException as e:
            return None, str(e)
        except Exception as e:
            return None, str(e)

    try:
        result, err = _do_request(skip_proxy=USE_NO_PROXY)
        if result is not None or err is None:
            return result, err
        # Retry without proxy on proxy error (common when corporate proxy blocks Data.gov)
        if "proxy" in (err or "").lower() or "403" in (err or ""):
            log.info("Retrying Data.gov catalog without proxy.")
            return _do_request(skip_proxy=True)
        return result, err
    except requests.exceptions.ProxyError:
        log.info("Data.gov proxy error; retrying without proxy.")
        return _do_request(skip_proxy=True)


def _fetch_hts_csv_sample(csv_url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch first portion of HTS CSV and parse into rows. Returns (rows, error message or None)."""
    rows_out = []
    try:
        session = _data_gov_session()
        r = session.get(
            csv_url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            headers={"Range": f"bytes=0-{CSV_BYTE_LIMIT}"},
        )
        if r.status_code not in (200, 206):
            return [], f"CSV returned status {r.status_code}"
        content = r.content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        # Support common USITC column name variants
        for row in reader:
            if len(rows_out) >= MAX_TABLE_ROWS:
                break
            hts = (row.get("HTS Number") or row.get("htsno") or row.get("HTSNO") or "").strip().strip('"')
            desc = (row.get("Description") or row.get("description") or "").strip().strip('"')
            general = (row.get("General Rate of Duty") or row.get("General") or "").strip().strip('"')
            special = (row.get("Special Rate of Duty") or row.get("Special") or "").strip().strip('"')
            col2 = (row.get("Column 2 Rate of Duty") or row.get("Column 2") or "").strip().strip('"')
            if not hts or not desc:
                continue
            rate = general or special or col2 or "—"
            rows_out.append({
                "hts_number": hts,
                "description": desc[:80] + ("…" if len(desc) > 80 else ""),
                "general_rate": general or "—",
                "special_rate": special or "—",
                "column2_rate": col2 or "—",
                "display_rate": rate,
            })
    except requests.exceptions.RequestException as e:
        log.warning("HTS CSV fetch failed: %s", e)
        return [], str(e)
    except Exception as e:
        log.warning("HTS CSV parse failed: %s", e)
        return [], str(e)
    return rows_out, None


def _parse_rate_pct(rate_str: str) -> Optional[float]:
    """Parse general_rate string (e.g. '3%', 'Free', '2.5%') to numeric percent or None."""
    if not rate_str or not isinstance(rate_str, str):
        return None
    s = rate_str.strip()
    if not s or s.lower() == "free" or s == "—":
        return 0.0
    m = re.match(r"^(\d+(?:\.\d+)?)\s*%?", s)
    if m:
        return float(m.group(1))
    return None


def _tariff_forecast_6m(tariff_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build 6-month forecast: average tariff rate (from current data) with slight trend per month."""
    rates = []
    for row in tariff_list:
        v = _parse_rate_pct(row.get("general_rate") or "")
        if v is not None:
            rates.append(v)
    avg = sum(rates) / len(rates) if rates else 0.0
    # Slight upward trend for forecast (e.g. +0.1% per month)
    trend = 0.1
    out = []
    dt = datetime.now()
    for i in range(6):
        month = dt.month + i
        year = dt.year
        while month > 12:
            month -= 12
            year += 1
        forecast_pct = round(avg + trend * i, 1)
        label = datetime(year, month, 1).strftime("%b %Y")
        out.append({"month": f"{year}-{month:02d}", "label": label, "avg_rate_pct": max(0, forecast_pct)})
    return out


def get_tariffs() -> Dict[str, Any]:
    """
    Return tariff table and source info. Connects to Data.gov catalog and
    fetches a sample of US HTS rates from the USITC CSV. On failure, returns
    mock rows and an "error" message for the UI.
    """
    source_title = "Data.gov (USITC HTS)"
    source_url = "https://catalog.data.gov/dataset?q=harmonized+tariff"
    tariff_list: List[Dict[str, Any]] = []
    error_msg: Optional[str] = None

    dataset, catalog_err = _get_hts_dataset_from_catalog()
    if catalog_err:
        error_msg = catalog_err
    if dataset:
        source_title = dataset["title"]
        source_url = dataset.get("url") or source_url
        csv_url = dataset.get("csv_url")
        if csv_url:
            tariff_list, csv_err = _fetch_hts_csv_sample(csv_url)
            if csv_err:
                error_msg = error_msg or csv_err
        elif not error_msg:
            error_msg = "No CSV resource found in dataset."

    if not tariff_list:
        # Fallback mock rows so the table always has content
        tariff_list = [
            {"hts_number": "7208.10.00", "description": "Flat-rolled iron/steel, width 600mm+", "general_rate": "Free", "special_rate": "Free (AU,CA,MX,…)", "column2_rate": "—", "display_rate": "Free"},
            {"hts_number": "7209.16.00", "description": "Flat-rolled, cold-rolled, 0.5mm+", "general_rate": "3%", "special_rate": "Free (AU,CA,MX,…)", "column2_rate": "—", "display_rate": "3%"},
            {"hts_number": "7210.70.30", "description": "Plated/coated with aluminum-zinc", "general_rate": "2.5%", "special_rate": "Free (AU,CA,MX,…)", "column2_rate": "—", "display_rate": "2.5%"},
            {"hts_number": "7308.90.95", "description": "Structures and parts of iron/steel", "general_rate": "Free", "special_rate": "Free (AU,CA,MX,…)", "column2_rate": "—", "display_rate": "Free"},
            {"hts_number": "8411.82.10", "description": "Turbojets, thrust 25-44 kN", "general_rate": "2.5%", "special_rate": "Free (AU,CA,MX,…)", "column2_rate": "—", "display_rate": "2.5%"},
        ]

    out: Dict[str, Any] = {
        "source": "Data.gov",
        "source_title": source_title,
        "source_url": source_url,
        "tariffs": tariff_list,
        "tariff_forecast_6m": _tariff_forecast_6m(tariff_list),
    }
    if error_msg:
        out["error"] = error_msg
    return out
