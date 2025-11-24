"""
Kingfood Mart beer products crawler.

- URL: https://kingfoodmart.com/bia
- Uses undetected_chromedriver to reduce bot detection.
- Uses the "Xem thêm sản phẩm" button to load all products.
- Each product is an anchor tag:

    <a class="pt-2" href="/bia-co-con/...">...</a>

Unified schema (no pack_type):
    source,
    code,
    name,
    brand,
    normalized_name,
    unit,
    packing,
    size,
    capacity,
    price,
    price_after_promotion,
    promotion,
    url,
    note,
    crawl_date,
    product_key

If this module is executed directly, it will:
    - Run the Kingfood crawler.
    - Export data to kingfood_beer_prices_YYYYMMDD.csv.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urljoin

import undetected_chromedriver as uc
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
    make_unique_code,
)

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://kingfoodmart.com"
CATEGORY_URL = "https://kingfoodmart.com/bia"

# XPaths for product and "load more" button
PRODUCT_XPATH = "//a[contains(@href, '/bia-co-con/')]"
SEE_MORE_XPATH = (
    "//button[.//span[contains(normalize-space(.), 'Xem thêm sản phẩm')]]"
)

# Allowed packings (same convention as BHX)
ALLOWED_PACKINGS = {"1", "4", "6", "12", "20", "24"}


class StealthChrome(uc.Chrome):
    """
    Wrapper around undetected_chromedriver.Chrome.

    This class overrides __del__ to avoid noisy WinError 6 logs
    on Windows. We explicitly call driver.quit() in the crawler
    instead of relying on __del__.
    """

    def __del__(self) -> None:
        # Do not call self.quit() here to avoid errors on interpreter shutdown.
        pass


def _build_driver(headless: bool = False) -> StealthChrome:
    """
    Build and return an undetected Chrome driver.

    Parameters
    ----------
    headless : bool
        If True, run browser in headless mode.

    Returns
    -------
    StealthChrome
    """
    if headless:
        driver = StealthChrome(headless=True)
    else:
        driver = StealthChrome()
    return driver


def _click_until_no_more(driver: StealthChrome) -> None:
    """
    Click "Xem thêm sản phẩm" until there is no more button.

    The loop stops when:
        - The button cannot be found, or
        - The button cannot be clicked (exception).

    Parameters
    ----------
    driver : StealthChrome
        WebDriver instance.
    """
    while True:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, SEE_MORE_XPATH))
            )
        except Exception:
            LOGGER.info(
                "No more 'Xem thêm sản phẩm' button found. Stop clicking."
            )
            break

        try:
            LOGGER.info("Clicking 'Xem thêm sản phẩm' button...")
            driver.execute_script("arguments[0].click();", btn)
            # Wait for DOM to append new products
            time.sleep(1.5)
        except Exception as exc:
            LOGGER.warning(
                "Error while clicking 'Xem thêm sản phẩm': %s",
                exc,
            )
            break


def crawl_kingfood(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Crawl beer products from Kingfood Mart.

    Parameters
    ----------
    headless : bool
        Run browser in headless mode if True.

    Returns
    -------
    List[Dict[str, Any]]
        List of product dictionaries following the common schema.
    """
    LOGGER.info("Starting Kingfood Mart crawler...")
    driver = _build_driver(headless=headless)
    products: List[Dict[str, Any]] = []

    try:
        LOGGER.info("Opening Kingfood URL: %s", CATEGORY_URL)
        driver.get(CATEGORY_URL)

        # Wait for initial React/JS loading
        time.sleep(8)

        # Ensure at least one product is visible before loading more
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, PRODUCT_XPATH))
            )
            LOGGER.info("Initial Kingfood products loaded.")
        except Exception:
            LOGGER.warning(
                "No initial beer products found within timeout window."
            )

        # Click "Xem thêm sản phẩm" until there is no more button
        _click_until_no_more(driver)

        # After all products are loaded, collect them
        elements = driver.find_elements(By.XPATH, PRODUCT_XPATH)
        LOGGER.info("Found %d Kingfood product items.", len(elements))

        crawl_date = datetime.now().strftime("%Y-%m-%d")

        for idx, element in enumerate(elements, start=1):
            try:
                # ---------------------------------------------------------
                # href, url, code
                # ---------------------------------------------------------
                href = element.get_attribute("href") or ""
                url = urljoin(BASE_URL, href) if href else ""

                # ---------------------------------------------------------
                # name
                # ---------------------------------------------------------
                try:
                    name_el = element.find_element(By.CSS_SELECTOR, "h3[title]")
                    name = name_el.text.strip()
                except Exception:
                    name = ""

                # ---------------------------------------------------------
                # Price after promotion (displayed price)
                # ---------------------------------------------------------
                price_after_text = ""
                try:
                    price_div = element.find_element(
                        By.XPATH,
                        (
                            ".//div[contains(@class,'flex') "
                            "and contains(@class,'items-baseline')]/div[1]"
                        ),
                    )
                    price_after_text = price_div.text.strip()
                except Exception:
                    price_after_text = ""

                price_after_int = extract_price_int(price_after_text)

                # ---------------------------------------------------------
                # Original price (if any)
                # ---------------------------------------------------------
                price_original_text = ""
                try:
                    old_price_div = element.find_element(
                        By.CSS_SELECTOR,
                        "div.line-through",
                    )
                    price_original_text = old_price_div.text.strip()
                except Exception:
                    price_original_text = ""

                price_original_int = extract_price_int(price_original_text)
                price = price_original_int or price_after_int

                # ---------------------------------------------------------
                # Promotion text & note
                # ---------------------------------------------------------
                promo_text_parts: List[str] = []

                # Overlay discount e.g. "-20%"
                try:
                    overlay_div = element.find_element(
                        By.XPATH,
                        (
                            ".//div[contains(@class,'absolute') "
                            "and contains(text(),'%')]"
                        ),
                    )
                    overlay_text = overlay_div.text.strip()
                    if overlay_text:
                        promo_text_parts.append(overlay_text)
                except Exception:
                    overlay_text = ""

                # "Tiết kiệm ..." text
                try:
                    save_div = element.find_element(
                        By.XPATH,
                        ".//div[contains(text(),'Tiết kiệm')]",
                    )
                    save_text = save_div.text.strip()
                    if save_text:
                        promo_text_parts.append(save_text)
                except Exception:
                    save_text = ""

                note = ""
                try:
                    note_container = element.find_element(
                        By.XPATH,
                        (
                            ".//div[@class='mb-1' "
                            "and contains(@style,'height: 16px')]"
                        ),
                    )
                    note_text = note_container.text.strip()
                    if note_text:
                        promo_text_parts.append(note_text)
                        note = note_text
                except Exception:
                    note = ""

                promo_text_raw = " ".join(promo_text_parts).strip()
                promotion = extract_promotion_from_text(promo_text_raw)

                # If no parsed promotion but price dropped, compute % discount
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
                        # Fallback to empty promotion on failure
                        pass

                # ---------------------------------------------------------
                # Parsing from name (unit, packing, capacity, brand, etc.)
                # ---------------------------------------------------------
                unit = extract_unit(name) if name else ""
                packing = extract_packing_quantity(name) if name else ""
                capacity = extract_capacity(name) if name else ""
                brand = extract_brand(name) if name else ""
                normalized_name = normalize_name(name) if name else ""
                size = ""

                if not packing or packing not in ALLOWED_PACKINGS:
                    packing = "1"

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                code = make_unique_code("kingfood", product_key, normalized_name)

                product: Dict[str, Any] = {
                    "source": "kingfoodmart",
                    "code": code,
                    "name": name,
                    "brand": brand,
                    "normalized_name": normalized_name,
                    "unit": unit,
                    "packing": packing,
                    "size": size,
                    "capacity": capacity,
                    "price": price,
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
                    "Error parsing Kingfood product index %d: %s",
                    idx,
                    exc,
                )
                continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    LOGGER.info("Kingfood crawl finished. Total products: %d", len(products))
    return products


# ---------------------------------------------------------------------
# Standalone execution (auto-export Kingfood CSV)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = crawl_kingfood(headless=False)
    print(f"Crawled {len(result)} products from Kingfood Mart.")

    if not result:
        print("No products found, CSV will not be generated.")
    else:
        import csv

        today = datetime.now().strftime("%Y%m%d")
        output_path = f"kingfood_beer_prices_{today}.csv"

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=result[0].keys())
            writer.writeheader()
            writer.writerows(result)

        print(
            f"Kingfood crawler finished → {len(result)} products "
            f"saved to {output_path}"
        )
