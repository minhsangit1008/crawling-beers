"""
Mega Market beer products crawler.

This module provides the `crawl_mega` function that:
    - Opens Mega Market beer category page.
    - Scrolls the page to fully load products.
    - Extracts normalized information from each product card.
    - Returns a list of dictionaries following the unified schema.

If this module is executed directly (not imported), it will:
    - Run the Mega crawler.
    - Print total crawled items.
    - Export results to mega_beer_prices_YYYYMMDD.csv.

Author: minhsangitdev
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from helpers import (
    extract_brand,
    extract_capacity,
    extract_packing_quantity,
    extract_price_int,
    extract_promotion_from_text,
    extract_unit,
    make_product_key,
    normalize_name,
    build_chrome_driver,
    make_unique_code,
)

LOGGER = logging.getLogger(__name__)

URL_MEGA_BEER = "https://online.mmvietnam.com/category/bia.html"

# Stable selector for pagination button
NEXT_BUTTON_SELECTOR = "button[aria-label='move to the next page']"


# ---------------------------------------------------------------------
# Driver initialization
# ---------------------------------------------------------------------
def init_driver(headless: bool = False) -> WebDriver:
    """
    Initialize and return a Chrome WebDriver.

    Parameters
    ----------
    headless : bool
        Run Chrome in headless mode if True.

    Returns
    -------
    WebDriver
    """
    return build_chrome_driver(headless=headless)


# ---------------------------------------------------------------------
# Scrolling & pagination helpers
# ---------------------------------------------------------------------
def go_to_next_page(
    driver: WebDriver,
    wait: WebDriverWait,
    timeout: int = 10,
) -> bool:
    """
    Click the 'next page' button if available.

    Parameters
    ----------
    driver : WebDriver
    wait : WebDriverWait
    timeout : int
        Seconds to wait for button to become clickable.

    Returns
    -------
    bool
        True if next page is clicked, False if no more pages.
    """
    try:
        next_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR))
        )
        driver.execute_script("arguments[0].click();", next_btn)
        LOGGER.info("Mega: clicked next page button.")
        time.sleep(5)
        return True

    except TimeoutException:
        LOGGER.info("Mega: no next page button found → stop pagination.")
        return False

    except Exception as exc:
        LOGGER.warning("Mega: error clicking next page button: %s", exc)
        return False


def scroll_to_load_all(
    driver: WebDriver,
    total_time: int = 60,
    interval: int = 5,
) -> None:
    """
    Multiple scroll actions to trigger lazy-loading content.

    Parameters
    ----------
    driver : WebDriver
    total_time : int
        Max total time for scrolling (seconds).
    interval : int
        Sleep time between scrolls (seconds).
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    end_time = time.time() + total_time

    while time.time() < end_time:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        LOGGER.info("Mega: scrolled to bottom → waiting %d sec...", interval)
        time.sleep(interval)

        new_height = driver.execute_script("return document.body.scrollHeight")

        if new_height == last_height:
            LOGGER.info("Mega: no more new content loaded → stop scrolling.")
            break

        last_height = new_height


# ---------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------
def crawl_mega(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Crawl beer products from Mega Market.

    Steps
    -----
    1. Open category page.
    2. Scroll to load products.
    3. Extract name, price, discount, URL, etc.
    4. Normalize and map to unified schema.

    Parameters
    ----------
    headless : bool
        Run browser in headless mode.

    Returns
    -------
    List[Dict[str, Any]]
        List of product dictionaries.
    """
    driver = init_driver(headless=headless)
    products: List[Dict[str, Any]] = []
    crawl_date = datetime.now().strftime("%Y-%m-%d")

    try:
        LOGGER.info("Opening Mega beer page: %s", URL_MEGA_BEER)
        driver.get(URL_MEGA_BEER)

        wait = WebDriverWait(driver, 30)
        time.sleep(5)

        page_index = 1
        max_pages = 50  # Arbitrary high limit for safety

        while page_index <= max_pages:
            LOGGER.info("Mega: processing page %d", page_index)

            scroll_to_load_all(driver, total_time=20, interval=5)

            # Product selectors
            product_list_selector = "div.gallery-module__items___YTUpR"
            product_item_selector = "div.item-module__root___hJBdd"
            name_selector = "a.item-module__name___IP-3e"
            link_selector = "a.item-module__images___1Ucb1"

            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, product_list_selector)
                )
            )
            container = driver.find_element(By.CSS_SELECTOR, product_list_selector)
            items = container.find_elements(By.CSS_SELECTOR, product_item_selector)

            LOGGER.info(
                "Mega: found %d items on page %d.",
                len(items),
                page_index,
            )

            for element in items:
                # -------------------------------------------------------------
                # Name & product link
                # -------------------------------------------------------------
                try:
                    name = element.find_element(
                        By.CSS_SELECTOR, name_selector
                    ).text.strip()
                except Exception:
                    name = ""

                try:
                    url = element.find_element(
                        By.CSS_SELECTOR, link_selector
                    ).get_attribute("href")
                except Exception:
                    url = ""

                # -------------------------------------------------------------
                # Code or note
                # -------------------------------------------------------------
                note = ""

                try:
                    dnr_text = element.find_element(
                        By.CSS_SELECTOR, "div[class^='item-module__dnrInner']"
                    ).text.strip()

                    if dnr_text:
                        # Nếu là chuỗi toàn chữ/số (SKU) thì bỏ qua, không dùng làm note
                        if not re.fullmatch(r"[A-Za-z0-9]+", dnr_text):
                            note = dnr_text

                except Exception:
                    pass

                except Exception:
                    pass

                # -------------------------------------------------------------
                # Price extraction
                # -------------------------------------------------------------
                # Final price
                try:
                    final_price_text = element.find_element(
                        By.CSS_SELECTOR, "div.item-module__finalPrice___zqAf5"
                    ).get_attribute("innerText").replace("\n", "").strip()
                except Exception:
                    final_price_text = ""

                # Old price
                try:
                    old_price_text = element.find_element(
                        By.CSS_SELECTOR, "div.item-module__oldPrice___b-kvC"
                    ).get_attribute("innerText").replace("\n", "").strip()
                except Exception:
                    old_price_text = ""

                # Promotion badge (e.g. -10%)
                try:
                    promo_source_text = element.find_element(
                        By.CSS_SELECTOR, "div[class^='item-module__discount']"
                    ).get_attribute("innerText").replace("\n", " ").strip()
                except Exception:
                    promo_source_text = ""

                final_price = extract_price_int(final_price_text)
                old_price = extract_price_int(old_price_text)
                promotion = extract_promotion_from_text(promo_source_text)

                # Mega price logic
                if old_price > 0:
                    price = old_price
                    price_after_promotion = final_price
                else:
                    price = final_price
                    price_after_promotion = final_price

                # -------------------------------------------------------------
                # Text parsing (brand, unit, packing)
                # -------------------------------------------------------------
                unit = extract_unit(name)
                packing = extract_packing_quantity(name)
                capacity = extract_capacity(name)
                brand = extract_brand(name)
                normalized_name = normalize_name(name)

                allowed_packings = {"1", "4", "6", "12", "20", "24"}
                if not packing or packing not in allowed_packings:
                    packing = "1"

                # If missing unit & price < 40K → assume 1 can
                if not unit and price and price < 40_000:
                    unit = "Lon"

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                code = make_unique_code("mega", product_key, normalized_name)


                products.append(
                    {
                        "source": "megamarket",
                        "code": code,
                        "name": name,
                        "brand": brand,
                        "normalized_name": normalized_name,
                        "unit": unit,
                        "packing": packing,
                        "size": "",
                        "capacity": capacity,
                        "price": price,
                        "price_after_promotion": price_after_promotion,
                        "promotion": promotion,
                        "url": url,
                        "note": note,
                        "crawl_date": crawl_date,
                        "product_key": product_key,
                    }
                )

            # If no next page → stop loop
            if not go_to_next_page(driver, wait):
                break

            page_index += 1

    finally:
        driver.quit()

    LOGGER.info("Mega crawl finished. Total products: %d", len(products))
    return products


# ---------------------------------------------------------------------
# Standalone execution (export CSV automatically)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    results = crawl_mega(headless=False)

    today = datetime.now().strftime("%Y%m%d")
    output_path = f"mega_beer_prices_{today}.csv"

    import csv

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(
        f"Mega crawler finished → {len(results)} products saved to {output_path}"
    )
