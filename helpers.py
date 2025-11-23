"""
Common helper functions for product parsing and normalization.

Author: minhsangitdev
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Known beer brands. Can be reused across crawlers.
BRANDS = [
    "Heineken",
    "Tiger",
    "Sài Gòn",
    "Budweiser",
    "Hoegaarden",
    "1664 Blanc",
    "Larue",
    "Huda",
    "Red Ruby",
    "Sapporo",
    "Bia Việt",
    "333",
    "Corona",
    "San Miguel",
    "Edelweiss",
    "Beck’s",
    "Carlsberg",
    "Strongbow",
    "Somersby",
    "Lạc Việt",
    "Tuborg",
    "Chill",
    "Hà Nội",
    "Chang",
    "Trúc Bạch Sleek",
    "Halida",
    "Chimay",
    "East West",
    "Red Horse",
    "Tsingtao",
    "Asahi",
    "Budweiser",
    "Sanwald",
    "Duvel",
    "Paulaner",
    "Dalat Cider",
    "Trúc Bạch",
    "Abbaye",
    "Pilsner Urquell",
    "G De Grand Cru",
    "Orion",
    "St. Sebastiaan",
    "Ngũ Hành",
    "Cherie",
]


def build_chrome_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Create a Chrome WebDriver instance shared across crawlers.

    Parameters
    ----------
    headless : bool
        If True, run Chrome in headless mode.

    Returns
    -------
    webdriver.Chrome
        Configured Chrome WebDriver.
    """
    options = webdriver.ChromeOptions()
    if headless:
        # New headless mode for Chrome 109+
        options.add_argument("--headless=new")

    # Flags for more stable execution in various environments
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    return driver


def extract_capacity(text: str) -> str:
    """
    Extract capacity from product name, supporting both ml and cl.

    Examples
    --------
    "Thùng 24 lon bia 330ml" -> "330ml"
    "Bia 33 CL"              -> "33cl"

    Parameters
    ----------
    text : str
        Raw product name text.

    Returns
    -------
    str
        Capacity string with unit, e.g. "330ml", "33cl",
        or empty string if not found.
    """
    lowered = text.lower()

    # Prefer ml first
    match_ml = re.search(r"(\d+)\s*ml", lowered)
    if match_ml:
        return f"{match_ml.group(1)}ml"

    # Then cl
    match_cl = re.search(r"(\d+)\s*cl", lowered)
    if match_cl:
        return f"{match_cl.group(1)}cl"

    return ""


def extract_unit(text: str) -> str:
    """
    Infer selling unit from product name.

    Rules
    -----
    - Contains "thùng" -> "Thùng"
    - Contains "lon"   -> "Lon"
    - Contains "chai"  -> "Chai"

    Parameters
    ----------
    text : str
        Raw product name text.

    Returns
    -------
    str
        Unit as one of {"Thùng", "Lon", "Chai"} or empty string if unknown.
    """
    lowered = text.lower()
    if "thùng" in lowered:
        return "Thùng"
    if "lon" in lowered:
        return "Lon"
    if "chai" in lowered:
        return "Chai"
    return ""


def extract_packing_quantity(text: str) -> str:
    """
    Extract packing quantity (number of items in a pack).

    Rules
    -----
    - Prefer numbers immediately before "lon"/"chai".
    - If not found, use numbers after "thùng"/"lốc"/"hộp".
    - Ignore numbers belonging to capacity (ml/cl).
    - Fallback: first number that is not part of ml/cl token.

    Parameters
    ----------
    text : str
        Raw product name text.

    Returns
    -------
    str
        Packing quantity as digits, or empty string if not found.
    """
    lowered = text.lower()

    # 1) Number before lon/chai: "thùng 24 lon", "lốc 6 lon"
    match = re.search(r"(\d+)\s*(lon|chai)", lowered)
    if match:
        return match.group(1)

    # 2) Number after 'thùng' / 'lốc' / 'hộp'
    match2 = re.search(r"(thùng|lốc|hop|hộp)\s*(\d+)", lowered)
    if match2:
        return match2.group(2)

    # 3) Fallback: first number that is not capacity (ml/cl)
    candidates = []
    for m in re.finditer(r"(\d+)", lowered):
        num = m.group(1)
        end = m.end()
        after = lowered[end:].strip()
        if after.startswith(("ml", "cl")):
            # Skip capacities such as 330ml, 33cl
            continue
        candidates.append(num)

    return candidates[0] if candidates else ""


def extract_price_int(price_text: str) -> int:
    """
    Parse price string and convert it to integer VND.

    Example
    -------
    "410.000đ /24 lon 330ml" -> 410000

    Parameters
    ----------
    price_text : str
        Raw price string from the website.

    Returns
    -------
    int
        Price as integer (VND). Returns 0 if parsing fails or text is empty.
    """
    if not price_text:
        return 0

    # Split at 'đ' (VND symbol)
    money_part = price_text.split("đ", maxsplit=1)[0]
    digits = re.sub(r"\D", "", money_part)
    return int(digits) if digits else 0


def extract_brand(text: str) -> str:
    """
    Extract brand name from product name.

    Special rules
    -------------
    - If product contains '1664' or 'blanc'/'blance' -> '1664 Blanc'.
    - Normalize some Vietnamese and English variants:
        'hanoi'     -> 'Hà Nội'
        'saigon'    -> 'Sài Gòn'
        'carsberg'  -> 'Carlsberg'
        'east west' / 'far east' / 'eastwest' -> 'East West'
        'bud'       -> 'Budweiser'
        'dalat cider' / 'da lat cider' -> 'Dalat Cider'
    - Otherwise, match from BRANDS list (case-insensitive).

    Parameters
    ----------
    text : str
        Raw product name text.

    Returns
    -------
    str
        Brand name or empty string if not recognized.
    """
    lowered = text.lower()

    # Special override for 1664 Blanc
    if "1664" in lowered or "blanc" in lowered or "blance" in lowered:
        return "1664 Blanc"

    if "hanoi" in lowered or "hà nội" in lowered:
        return "Hà Nội"

    if "saigon" in lowered or "sài gòn" in lowered:
        return "Sài Gòn"

    if "carlsberg" in lowered or "carsberg" in lowered:
        return "Carlsberg"

    if (
        "far east" in lowered
        or "east west" in lowered
        or "eastwest" in lowered
    ):
        return "East West"

    if "bud " in lowered or lowered.startswith("bud"):
        return "Budweiser"

    if "dalat cider" in lowered or "da lat cider" in lowered:
        return "Dalat Cider"

    # Normal brand detection via list
    for brand in BRANDS:
        if brand.lower() in lowered:
            return brand

    return ""


def extract_promotion_from_text(text: str) -> str:
    """
    Extract promotion percentage from raw text, supporting decimals.

    Examples
    --------
    "-3%"              -> "3%"
    "Giảm 1.98%"       -> "1.98%"
    "Giảm 1,98% ABC"   -> "1.98%"

    Strategy
    --------
    Take all percentage-like numbers and return the last one,
    assuming the final percentage is the actual discount.

    Parameters
    ----------
    text : str
        Raw promotion text.

    Returns
    -------
    str
        Promotion percentage string like '3%' or '1.98%'.
        Returns empty string if no percentage is found.
    """
    if not text:
        return ""

    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not matches:
        return ""

    value = matches[-1].replace(",", ".")
    try:
        num = float(value)
        if num.is_integer():
            return f"{int(num)}%"
        return f"{num}%"
    except ValueError:
        return f"{value}%"


def normalize_name(text: str) -> str:
    """
    Normalize product name for cross-site matching.

    Steps
    -----
    - Lowercase.
    - Remove accents/diacritics.
    - Keep only alphanumeric characters and spaces.
    - Collapse multiple spaces into one.

    Parameters
    ----------
    text : str
        Original product name.

    Returns
    -------
    str
        Normalized product name.
    """
    lowered = text.lower().strip()

    # Remove accents (e.g. Vietnamese diacritics)
    normalized = unicodedata.normalize("NFD", lowered)
    normalized = "".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    )

    # Keep alphanumeric and spaces only
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)

    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def make_product_key(
    brand: Optional[str],
    capacity: Optional[str],
    packing: Optional[str],
) -> str:
    """
    Build a product key for cross-site comparison (variant removed).

    Example
    -------
    brand="Heineken", capacity="330ml", packing="24"
        -> "HEINEKEN_330ML_24"

    Parameters
    ----------
    brand : str or None
        Brand name.
    capacity : str or None
        Capacity string (e.g. '330ml').
    packing : str or None
        Packing quantity (e.g. '24').

    Returns
    -------
    str
        Normalized composite key like "HEINEKEN_330ML_24".
    """
    brand_part = (brand or "").strip().replace(" ", "")
    cap_part = (capacity or "").strip()
    pack_part = (packing or "").strip()

    parts = [p for p in (brand_part, cap_part, pack_part) if p]
    return "_".join(p.upper() for p in parts)