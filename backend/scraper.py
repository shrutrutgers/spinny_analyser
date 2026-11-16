"""
Scrapes a Spinny used-car listing page for pricing, Spinny Assured EMI/loan
terms, assured buyback (when published), maintenance/servicing package cost,
roadside-assistance (RSA) cost, and extended-warranty tiers.

Spinny's listing page is server-rendered: the full product record is embedded
in the HTML as a JS object literal assigned to `window.__INITIAL_STATE__`
(minified, unquoted keys, `!0`/`!1` for booleans, bare `.5`-style floats).
We locate the `productDetail:{...}` object inside it with a brace-balanced
scan (regex alone can't handle arbitrary nesting), patch it into valid JSON,
and parse it. This avoids needing a headless browser.
"""
from __future__ import annotations

import re
import time
from typing import Any

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PRODUCT_DETAIL_KEY = "productDetail:"


class ScrapeError(Exception):
    """Raised when a Spinny listing can't be fetched or parsed."""


def is_spinny_url(url: str) -> bool:
    return bool(re.match(r"^https?://(www\.)?spinny\.com/", url.strip(), re.I))


def _fetch_html(url: str) -> str:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ScrapeError(f"Could not reach Spinny: {exc}") from exc

    if resp.status_code != 200:
        raise ScrapeError(f"Spinny returned HTTP {resp.status_code} for this URL")
    return resp.text


def _extract_balanced_object(text: str, start_idx: int) -> str:
    """Given the index of the opening '{', return the matching balanced
    JS-object-literal substring, respecting quoted strings."""
    depth = 0
    in_str = False
    str_char = ""
    escape = False
    for i in range(start_idx, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == str_char:
                in_str = False
        else:
            if c in ("'", '"'):
                in_str = True
                str_char = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start_idx : i + 1]
    raise ScrapeError("Could not find the end of the product data block")


def _js_object_to_json(js: str) -> str:
    # quote bare identifier keys: {key: or ,key:
    js = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', js)
    # webpack-minified booleans
    js = js.replace("!0", "true").replace("!1", "false")
    js = re.sub(r":\s*undefined", ": null", js)
    # trailing commas
    js = re.sub(r",\s*}", "}", js)
    js = re.sub(r",\s*]", "]", js)
    # bare leading-dot floats (.5 -> 0.5), valid JS, invalid JSON
    js = re.sub(r"([:\[,]\s*)(-?)\.(\d)", r"\g<1>\g<2>0.\3", js)
    return js


def _extract_product_detail(html: str) -> dict:
    idx = html.find(PRODUCT_DETAIL_KEY)
    if idx == -1:
        raise ScrapeError(
            "Couldn't find car data on this page. Make sure this is a Spinny "
            "car listing URL (e.g. spinny.com/buy-used-cars/.../<id>/)."
        )
    brace_idx = html.find("{", idx)
    raw_obj = _extract_balanced_object(html, brace_idx)
    converted = _js_object_to_json(raw_obj)

    import json

    try:
        return json.loads(converted)
    except json.JSONDecodeError as exc:
        raise ScrapeError(f"Failed to parse Spinny's product data: {exc}") from exc


def _parse_rupees(value: Any) -> int | None:
    """'4,07,000' -> 407000"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def scrape_spinny_listing(url: str) -> dict:
    if not is_spinny_url(url):
        raise ScrapeError("That doesn't look like a spinny.com URL")

    html = _fetch_html(url)
    pd = _extract_product_detail(html)

    variant = pd.get("variant") or {}
    pricing = pd.get("pricing") or {}
    finance_best = ((pd.get("finance") or {}).get("best") or {}).get("details") or {}

    listing_price = _parse_rupees((pricing.get("listing_price") or {}).get("price"))
    market_price = _parse_rupees((pricing.get("market_price") or {}).get("price"))

    buyback_raw = pd.get("buy_back_pricing") or pricing.get("buyback_pricing")
    buyback_available = buyback_raw is not None

    servicing = pricing.get("servicing_package") or {}
    rsa = pricing.get("rsa_pricing") or {}
    warranty = pricing.get("extended_warranty_pricing") or {}

    loan_amount = finance_best.get("loan_amount") or {}
    loan_age = finance_best.get("loan_age") or {}
    emi_best = _parse_rupees((finance_best.get("emi") or {}).get("best"))

    return {
        "source_url": url,
        "scraped_at": int(time.time()),
        "car": {
            "title": variant.get("full_name")
            or f"{pd.get('make', '')} {pd.get('model', '')}".strip(),
            "make": pd.get("make"),
            "model": pd.get("model"),
            "variant": variant.get("display_name"),
            "body_type": variant.get("body_type"),
            "make_year": pd.get("make_year"),
            "registration_year": pd.get("registration_year"),
            "no_of_owners": pd.get("no_of_owners"),
            "fuel_type": pd.get("fuel_type"),
            "transmission": pd.get("transmission"),
            "color": pd.get("color"),
            "km_driven": _parse_rupees(pd.get("mileage")),
            "city": pd.get("city"),
        },
        "pricing": {
            "listing_price": listing_price,
            "market_price": market_price,
            "savings_vs_market": (
                market_price - listing_price
                if listing_price and market_price
                else None
            ),
        },
        "finance": {
            "available": bool(finance_best),
            "emi_quoted": emi_best,
            "loan_amount_best": loan_amount.get("best"),
            "loan_amount_max": loan_amount.get("max"),
            "roi_percent": finance_best.get("roi"),
            "tenure_years_best": loan_age.get("best"),
            "tenure_years_max": loan_age.get("max"),
            "max_ltv_percent": finance_best.get("max_ltv"),
        },
        "buyback": {
            "available": buyback_available,
            "raw": buyback_raw,
        },
        "maintenance": {
            "service_1yr": servicing.get("1_year"),
            "service_2yr": servicing.get("2_year"),
            "service_3yr": servicing.get("3_year"),
        },
        "rsa": {
            "rsa_1yr": rsa.get("1_year"),
            "rsa_2yr": rsa.get("2_year"),
            "rsa_3yr": rsa.get("3_year"),
        },
        "extended_warranty": {
            "assured": warranty.get("assured"),
            "protect_plus": warranty.get("protect_plus"),
            "protect_star": warranty.get("protect_star"),
            "super_protect": warranty.get("super_protect"),
            "protect": warranty.get("protect"),
        },
    }
