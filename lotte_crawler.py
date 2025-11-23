"""
Lotte Mart beer products crawler.

This module defines a function `crawl_lotte` that:
    - Opens Lotte Mart beer category page.
    - Scrolls the page to trigger lazy-loading of all products.
    - Extracts normalized product information using the common schema:

        source, code, name, brand, normalized_name, unit,
        packing, size, capacity, price,
        price_after_promotion, promotion, url, note, crawl_date,
        product_key.

If this module is executed directly, it will:
    - Run the Lotte crawler.
    - Export data to lotte_beer_prices_YYYYMMDD.csv.

Author: minhsangitdev (adapted for Lotte by ChatGPT)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from helpers import (
    extract_price_int,
    extract_promotion_from_text,
    extract_brand,
    extract_capacity,
    extract_packing_quantity,
    extract_unit,
    normalize_name,
    make_product_key,
    build_chrome_driver,
)

LOGGER = logging.getLogger(__name__)

LOTTE_URL = "https://www.lottemart.vn/vi-nsg/category/bia-c123"

# Allowed packings (same convention as other crawlers)
ALLOWED_PACKINGS = {"1", "4", "6", "12", "20", "24"}


# ---------------------------------------------------------------------
# Driver & scrolling helpers
# ---------------------------------------------------------------------
def _build_driver(headless: bool = True) -> webdriver.Chrome:
    """
    Initialize Chrome WebDriver using the shared helper.

    Parameters
    ----------
    headless : bool
        Run browser in headless mode if True.

    Returns
    -------
    webdriver.Chrome
    """
    return build_chrome_driver(headless=headless)


def _scroll_full_page(
    driver: webdriver.Chrome,
    total_time: int = 60,
    interval: int = 5,
) -> None:
    """
    Continuously scroll the page to trigger lazy-loading of products.

    Every `interval` seconds:
        - Scroll to the bottom of the page.
        - Wait half of the interval.
        - Scroll up slightly to help trigger any lazy-load logic.
        - Wait the remaining half of the interval.

    The process runs for at most `total_time` seconds or stops earlier
    when no additional page height is loaded.

    Parameters
    ----------
    driver : webdriver.Chrome
    total_time : int
        Total duration (in seconds) to keep scrolling.
    interval : int
        Delay between scroll movements (in seconds).
    """
    start = time.time()
    last_height = driver.execute_script("return document.body.scrollHeight")

    while time.time() - start < total_time:
        # Scroll to the bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(interval / 2)

        # Scroll up slightly to trigger lazy-load if needed
        driver.execute_script(
            "window.scrollBy(0, -Math.floor(window.innerHeight * 0.3));"
        )
        time.sleep(interval / 2)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            LOGGER.info(
                "Page height did not change further. Stop scrolling."
            )
            break

        last_height = new_height


# ---------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------
def crawl_lotte(headless: bool = True) -> List[Dict[str, Any]]:
    """
    Crawl beer products from Lotte Mart.

    Parameters
    ----------
    headless : bool
        Run browser in headless mode if True.

    Returns
    -------
    List[Dict[str, Any]]
        List of product dictionaries using the common schema:

        [
            "source",
            "code",
            "name",
            "brand",
            "normalized_name",
            "unit",
            "packing",
            "size",
            "capacity",
            "price",
            "price_after_promotion",
            "promotion",
            "url",
            "note",
            "crawl_date",
            "product_key",
        ]
    """
    LOGGER.info("Starting Lotte Mart crawler...")
    driver = _build_driver(headless=headless)
    products: List[Dict[str, Any]] = []

    try:
        LOGGER.info("Opening Lotte URL: %s", LOTTE_URL)
        driver.get(LOTTE_URL)

        # Wait for product list container to appear
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.proudct-list")
                )
            )
            LOGGER.info("Lotte product list container found.")
        except Exception:
            LOGGER.warning(
                "Could not find 'proudct-list' container within timeout."
            )

        # Scroll to load all products
        _scroll_full_page(driver, total_time=60, interval=5)

        # Find all product items
        item_selector = (
            "div.proudct-list div.item[itemtype='https://schema.org/Product']"
        )
        elements = driver.find_elements(By.CSS_SELECTOR, item_selector)
        LOGGER.info("Found %d Lotte product items.", len(elements))

        crawl_date = datetime.now().strftime("%Y-%m-%d")

        for idx, element in enumerate(elements, start=1):
            try:
                # ---------------------------------------------------------
                # Name & URL
                # ---------------------------------------------------------
                try:
                    name_el = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-name[itemprop='name'] a",
                    )
                    name = name_el.text.strip()
                    href = name_el.get_attribute("href") or ""
                except Exception:
                    name = ""
                    href = ""

                url = urljoin(LOTTE_URL, href) if href else ""

                # ---------------------------------------------------------
                # Code (parsed from href)
                # Example: /vi-nsg/product/...-18935012413328-p10826
                # We extract the sequence before "-p..."
                # ---------------------------------------------------------
                code = ""
                if href:
                    try:
                        path = href.split("/")[-1]
                        # path example: "thung-...-18935012413328-p10826"
                        before_p = path.split("-p", maxsplit=1)[0]
                        code = before_p.split("-")[-1].strip()
                    except Exception:
                        code = ""

                # ---------------------------------------------------------
                # Price after promotion (displayed price)
                # ---------------------------------------------------------
                price_after_text = ""

                # Case 1: div.field-price span[itemprop='price']
                try:
                    price_span = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-price span[itemprop='price']",
                    )
                    price_after_text = price_span.text.strip()
                except Exception:
                    # Case 2: price is directly in div.field-price[itemprop='price']
                    try:
                        price_div = element.find_element(
                            By.CSS_SELECTOR,
                            "div.field-price[itemprop='price']",
                        )
                        price_after_text = price_div.text.strip()
                    except Exception:
                        price_after_text = ""

                price_after_int = extract_price_int(price_after_text)

                # ---------------------------------------------------------
                # Original price
                # ---------------------------------------------------------
                price_original_text = ""
                try:
                    price_original_text = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-price-old",
                    ).text.strip()
                except Exception:
                    price_original_text = ""

                price_original_int = extract_price_int(price_original_text)

                # If no original price is available, use current price
                price = price_original_int or price_after_int

                # ---------------------------------------------------------
                # Promotion text: discount % + extra promo text
                # ---------------------------------------------------------
                promo_text_raw_parts: List[str] = []

                # Discount percentage
                try:
                    discount_span = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-price span.lbl-discount",
                    )
                    discount_txt = discount_span.text.strip()
                    if discount_txt:
                        promo_text_raw_parts.append(discount_txt)
                except Exception:
                    pass

                # Extra promotion conditions in div.field-more
                note = ""
                try:
                    more_div = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-more",
                    )
                    more_txt = more_div.text.strip()
                    if more_txt:
                        promo_text_raw_parts.append(more_txt)
                        # Store conditions in note
                        note = more_txt
                except Exception:
                    note = ""

                promo_text_raw = " ".join(promo_text_raw_parts).strip()
                promotion = extract_promotion_from_text(promo_text_raw)

                # If promotion not parsed but price difference exists,
                # compute discount percentage from price & price_after_int.
                if (
                    not promotion
                    and price
                    and price_after_int
                    and price > price_after_int
                ):
                    try:
                        discount = (price - price_after_int) * 100.0 / float(
                            price
                        )
                        discount = round(discount, 2)
                        if abs(discount - int(discount)) < 1e-6:
                            promotion = f"{int(discount)}%"
                        else:
                            promotion = f"{discount}%"
                    except Exception:
                        # If calculation fails, leave promotion empty
                        pass

                # ---------------------------------------------------------
                # Text-based parsing: unit, packing, capacity, brand, etc.
                # ---------------------------------------------------------
                unit = extract_unit(name) if name else ""
                packing = extract_packing_quantity(name) if name else ""
                capacity = extract_capacity(name) if name else ""
                brand = extract_brand(name) if name else ""

                # Enforce allowed packing values
                if not packing or packing not in ALLOWED_PACKINGS:
                    packing = "1"

                normalized_name = normalize_name(name) if name else ""
                size = ""  # Not used for now

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                product: Dict[str, Any] = {
                    "source": "lottemart",
                    "code": code,
                    "name": name,
                    "brand": brand,
                    "normalized_name": normalized_name,
                    "unit": unit,
                    "packing": packing,
                    "size": size,
                    "capacity": capacity,
                    "price": price,
                    # Always final price after discount; conditions go into note.
                    "price_after_promotion": price_after_int,
                    "promotion": promotion,
                    "url": url,
                    "note": note,
                    "crawl_date": crawl_date,
                    "product_key": product_key,
                }

                products.append(product)

            except Exception as exc:
                LOGGER.warning(
                    "Error parsing Lotte product index %d: %s", idx, exc
                )
                continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    LOGGER.info("Lotte crawl finished. Total products: %d", len(products))
    return products


# ---------------------------------------------------------------------
# Standalone execution (auto-export Lotte CSV)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = crawl_lotte(headless=False)
    print(f"Crawled {len(result)} products from Lotte Mart.")

    if not result:
        print("No products found, CSV will not be generated.")
    else:
        import csv

        today = datetime.now().strftime("%Y%m%d")
        output_path = f"lotte_beer_prices_{today}.csv"

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=result[0].keys())
            writer.writeheader()
            writer.writerows(result)

        print(
            f"Lotte crawler finished → {len(result)} products "
            f"saved to {output_path}"
        )