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
    Tạo Chrome WebDriver dùng chung cho các crawler.

    Args:
        headless: True nếu muốn chạy chế độ không hiện cửa sổ Chrome.

    Returns:
        webdriver.Chrome đã cấu hình sẵn.
    """
    options = webdriver.ChromeOptions()
    if headless:
        # Headless mới cho Chrome 109+
        options.add_argument("--headless=new")

    # Các flag giúp chạy ổn định hơn
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
    Extract capacity, supports both ml and cl.

    Examples:
        "Thùng 24 lon bia 330ml" -> "330ml"
        "Bia 33 CL"              -> "33cl"

    Args:
        text: Raw product name text.

    Returns:
        Capacity string with unit, e.g. "330ml", "33cl",
        or empty string if not found.
    """
    t = text.lower()

    # Ưu tiên ml
    m_ml = re.search(r"(\d+)\s*ml", t)
    if m_ml:
        return f"{m_ml.group(1)}ml"

    # Sau đó tới cl
    m_cl = re.search(r"(\d+)\s*cl", t)
    if m_cl:
        return f"{m_cl.group(1)}cl"

    return ""



def extract_unit(text: str) -> str:
    """
    Infer selling unit from product name.

    Examples:
        Contains "thùng" -> "Thùng"
        Contains "lon"   -> "Lon"
        Contains "chai"  -> "Chai"

    Args:
        text: Raw product name text.

    Returns:
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

    Rules:
        - Ưu tiên số đứng ngay trước 'lon' / 'chai'.
        - Nếu không có, dùng số sau 'thùng' / 'lốc' / 'hộp'.
        - Loại bỏ các số thuộc capacity (ml / cl).
        - Cuối cùng, fallback: lấy số đầu tiên không phải ml/cl.

    Args:
        text: Raw product name text.

    Returns:
        Packing quantity as digits, or empty string if not found.
    """
    t = text.lower()

    # 1) Số trước lon/chai: "thùng 24 lon", "lốc 6 lon"
    m = re.search(r"(\d+)\s*(lon|chai)", t)
    if m:
        return m.group(1)

    # 2) Số sau 'thùng' / 'lốc' / 'hộp'
    m2 = re.search(r"(thùng|lốc|hop|hộp)\s*(\d+)", t)
    if m2:
        return m2.group(2)

    # 3) Fallback: số đầu tiên nhưng không phải capacity (ml/cl)
    candidates = []
    for m3 in re.finditer(r"(\d+)", t):
        num = m3.group(1)
        end = m3.end()
        after = t[end:].strip()
        if after.startswith(("ml", "cl")):
            # bỏ capacity như 330ml, 33cl
            continue
        candidates.append(num)

    return candidates[0] if candidates else ""



def extract_price_int(price_text: str) -> int:
    """
    Parse price string and convert to integer.

    Example:
        "410.000đ /24 lon 330ml" -> 410000

    Args:
        price_text: Raw price string from the website.

    Returns:
        Price as integer (VND). Returns 0 if parsing fails or text is empty.
    """
    if not price_text:
        return 0

    parts = price_text.split("đ", maxsplit=1)
    money_part = parts[0]
    digits = re.sub(r"\D", "", money_part)
    return int(digits) if digits else 0


def extract_brand(text: str) -> str:
    """
    Extract brand name with special rules:
        - If product contains '1664' or 'blanc'/'blance', return '1664 Blanc'.
        - Otherwise, match from BRANDS list.
    """
    t = text.lower()

    # Special override for 1664 Blanc
    if "1664" in t or "blanc" in t or "blance" in t:
        return "1664 Blanc"

    if "Hanoi" in t or "hà nội" in t:
        return "Hà Nội"

    if "Saigon" in t or "sài gòn" in t:
        return "Sài Gòn"
    
    if "Carlsberg" in t or "carsberg" in t:
        return "Carlsberg"

    if "Far East" in t or "east west" in t or "Eastwest" in t:
        return "East West"

    if "Bud" in t:
        return "Budweiser"

    if "Dalat Cider" in t or "Da Lat Cider" in t:
        return "Dalat Cider"

    # Normal brand detection
    for b in BRANDS:
        if b.lower() in t:
            return b

    return ""


def extract_promotion_from_text(text: str) -> str:
    """
    Extract promotion percentage from raw text, support decimals.

    Examples:
        "-3%"     -> "3%"
        "Giảm 1.98%" or "1,98%" -> "1.98%"
    """
    if not text:
        return ""

    # Lấy TẤT CẢ số có kèm % rồi chọn số cuối cùng (thường là % giảm)
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
    Normalize product name for matching across different sources.

    Steps:
        - Lowercase
        - Remove accents/diacritics
        - Keep only alphanumeric and spaces
        - Collapse multiple spaces

    Args:
        text: Original product name.

    Returns:
        Normalized name string.
    """
    # Convert to lowercase
    lowered = text.lower().strip()

    # Remove accents (Vietnamese, etc.)
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
    brand: str,
    capacity: str,
    packing: str,
) -> str:
    """
    Build a product key for cross-site comparison (variant removed).

    Example:
        brand="Heineken", capacity_ml="330", packing="24" -> "HEINEKEN_330_24"
    """
    brand_part = (brand or "").strip().replace(" ", "")
    cap_part = (capacity or "").strip()
    pack_part = (packing or "").strip()

    parts = [p for p in (brand_part, cap_part, pack_part) if p]
    return "_".join(p.upper() for p in parts)
