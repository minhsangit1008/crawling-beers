"""
Beer products crawler for BachHoaXanh (BHX).

This script uses Selenium to crawl beer products from BachHoaXanh's beer
category page and exports the normalized data to a CSV file.

Author: minhsangitdev
"""

import csv
import logging
import re
import time

from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://www.bachhoaxanh.com/bia"
OUTPUT_CSV = "bhx_beer_products_full.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BRANDS = [
    "Heineken",
    "Tiger",
    "Sài Gòn",
    "Budweiser",
    "Hoegaarden",
    "Blanc 1664",
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
]


# ========= HELPERS =========
def extract_capacity(text: str) -> str:
    """
    Extract capacity in milliliters from product name.

    Examples:
        "Thùng 24 lon bia 330ml" -> "330"
        "Bia Tiger 500 ml" -> "500"

    Args:
        text: Raw product name text.

    Returns:
        Capacity in ml as string (digits only), or empty string if not found.
    """
    match = re.search(r"(\d+)\s*ml", text.lower())
    return match.group(1) if match else ""


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
    Extract packing quantity (number of items in a pack) from product name.

    Examples:
        "Thùng 24 lon bia ..." -> "24"
        "Lốc 6 lon 330ml ..."  -> "6"

    Rules:
        - Prefer the number directly attached to "lon" or "chai".
        - Ignore numbers that are followed by "ml" (e.g. 330ml is capacity,
          not packing).
        - If still not found, return the first remaining numeric token.

    Args:
        text: Raw product name text.

    Returns:
        Packing quantity as string (digits only), or empty string if not found.
    """
    lowered = text.lower()

    # Case 1: number before "lon"/"chai"
    match = re.search(r"(\d+)\s*(lon|chai)", lowered)
    if match:
        return match.group(1)

    # Case 2: fallback to first numeric token that is not followed by "ml"
    candidates = []
    for m in re.finditer(r"(\d+)", lowered):
        num = m.group(1)
        end = m.end()
        after = lowered[end:].lstrip()

        # Skip capacity like "330ml"
        if after.startswith("ml"):
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

    # Only use the part before the currency symbol "đ".
    parts = price_text.split("đ", maxsplit=1)
    money_part = parts[0]
    digits = re.sub(r"\D", "", money_part)
    return int(digits) if digits else 0


def extract_brand(text: str) -> str:
    """
    Detect beer brand from product name using the BRANDS list.

    Matching is case-insensitive and uses substring search.

    Args:
        text: Raw product name text.

    Returns:
        Brand string if found, otherwise empty string.
    """
    lowered = text.lower()
    for brand in BRANDS:
        if brand.lower() in lowered:
            return brand
    return ""


def extract_promotion_from_text(text: str) -> str:
    """
    Extract promotion percentage from raw promotion text.

    Examples:
        "-3%"        -> "3%"
        "Giảm -5 %"  -> "5%"

    Args:
        text: Raw text inside promotion area.

    Returns:
        Promotion percentage as string, e.g. "3%", or empty string if not found.
    """
    if not text:
        return ""
    match = re.search(r"-?\s*(\d+)\s*%", text)
    if match:
        return f"{match.group(1)}%"
    return ""


# ========= DRIVER =========
def init_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Initialize and return a Chrome WebDriver instance.

    Args:
        headless: If True, run Chrome in headless mode.

    Returns:
        Configured Chrome WebDriver.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")

    # Common options for stability in different environments
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    return driver


def crawl_beer() -> None:
    """
    Crawl beer products from BachHoaXanh and export them to a CSV file.

    This function:
        1. Opens the beer category page.
        2. Waits for products container to load.
        3. Iterates all product items and extracts:
           - Code, Name, Unit, Size, Brand, Capacity, Packing,
             Price (original/current), Promotion, URL.
        4. Applies heuristic rules for Unit and Packing.
        5. Writes the final dataset to OUTPUT_CSV.
    """
    driver = init_driver(headless=False)
    products: list[dict[str, object]] = []
    # Use a single crawl date for this run
    crawl_date = datetime.now().strftime("%Y-%m-%d")

    try:
        logging.info("Opening page: %s", URL)
        driver.get(URL)

        logging.info("Waiting 30 seconds for page to fully load...")
        time.sleep(30)

        wait = WebDriverWait(driver, 30)

        # Main container that holds all the product items
        container_selector = (
            "div.-mt-1.-mx-1.flex.flex-wrap.content-stretch.px-0"
        )
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, container_selector)
            )
        )
        container = driver.find_element(By.CSS_SELECTOR, container_selector)

        # Each product item
        product_selector = "div.this-item"
        items = container.find_elements(By.CSS_SELECTOR, product_selector)
        logging.info("Found %d products.", len(items))

        name_selector = "h3.product_name"
        price_selector = "div.product_price"

        for element in items:
            # -------------------------
            # Basic fields: name & URL
            # -------------------------
            try:
                name = element.find_element(
                    By.CSS_SELECTOR,
                    name_selector,
                ).text.strip()
            except Exception:
                name = ""

            try:
                url = element.find_element(
                    By.CSS_SELECTOR,
                    "a",
                ).get_attribute("href")
            except Exception:
                url = ""

            # -------------------------
            # Product code:
            #   Case 1: "product-code" attribute on a div
            #   Case 2: id="product_<id>" on <a> tag
            # -------------------------
            code = ""

            # Case 1: Use "product-code" attribute if present
            try:
                code = element.find_element(
                    By.CSS_SELECTOR,
                    "div[product-code]",
                ).get_attribute("product-code").strip()
            except Exception:
                code = ""

            # Case 2: Fallback to id="product_xxx" on anchor
            if not code:
                try:
                    anchor_tag = element.find_element(
                        By.CSS_SELECTOR,
                        "a[id^='product_']",
                    )
                    raw_id = anchor_tag.get_attribute("id")  # e.g. "product_268673"
                    # Extract numeric part after "product_"
                    code = raw_id.strip()
                except Exception:
                    code = ""

            # -------------------------
            # Price (current / after promotion)
            # -------------------------
            try:
                price_after_text = element.find_element(
                    By.CSS_SELECTOR,
                    price_selector,
                ).text.strip()
            except Exception:
                price_after_text = ""

            # -------------------------
            # Original price & promotion text
            # -------------------------
            price_original_text = ""
            promotion_text_raw = ""

            try:
                promo_div = element.find_element(
                    By.XPATH,
                    (
                        './/div[contains(@class,"mb-2px") '
                        'and contains(@class,"leading-3")]'
                    ),
                )

                # Original price (line-through)
                try:
                    span_old = promo_div.find_element(
                        By.CSS_SELECTOR,
                        'span[class*="line-through"]',
                    )
                    price_original_text = span_old.text.strip()
                except Exception:
                    price_original_text = ""

                promotion_text_raw = promo_div.text.strip()
            except Exception:
                price_original_text = ""
                promotion_text_raw = ""

            # Parse promotion percentage from raw promo text
            promotion = extract_promotion_from_text(promotion_text_raw)

            # -----------------------------------
            # Parse Unit / Packing / Capacity /
            # Brand / Size / Note
            # -----------------------------------
            unit = extract_unit(name)
            packing_qty = extract_packing_quantity(name)
            capacity = extract_capacity(name)
            brand = extract_brand(name)
            size = ""  # Reserved for future use
            note = ""

            # -------------------------
            # Convert price strings to int
            # -------------------------
            price_after_int = extract_price_int(price_after_text)
            price_original_int = extract_price_int(price_original_text)

            # Use original price if available; otherwise current price
            price_int = price_original_int or price_after_int

            # Heuristic: if no unit and price < 40,000 VND,
            # assume it is a single can.
            if not unit and price_int and price_int < 40_000:
                unit = "Lon"

            # Normalize packing:
            # Allowed packing values: 1, 4, 6, 12, 20, 24.
            # Any missing or unexpected value is forced to "1".
            allowed_packings = {"24", "20", "12", "6", "4", "1"}
            if not packing_qty:
                packing_qty = "1"
            elif packing_qty not in allowed_packings:
                packing_qty = "1"

            products.append(
                {
                    "Code": code,
                    "Name": name,
                    "Unit": unit,
                    "Size": size,
                    "Brand": brand,
                    "Capacity (ml)": capacity,
                    "Packing": packing_qty,
                    "Price": price_int,
                    "Price after Promotion": price_after_int,
                    "Promotion": promotion,
                    "Note": note,
                    "URL": url,
                    "CrawlDate": crawl_date,
                }
            )
    finally:
        # Always close the browser, even if an exception occurs.
        driver.quit()

    # -------------------------
    # Write the results to CSV
    # -------------------------
    fields = [
        "Code",
        "Name",
        "Unit",
        "Size",
        "Brand",
        "Capacity (ml)",
        "Packing",
        "Price",
        "Price after Promotion",
        "Promotion",
        "Note",
        "URL",
        "CrawlDate",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(products)

    logging.info("Exported file: %s", OUTPUT_CSV)


if __name__ == "__main__":
    crawl_beer()
