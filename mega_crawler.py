"""
Mega Market beer products crawler.

This module defines a function `crawl_mega` that:
    - Opens Mega Market beer category page.
    - Scrolls the page to load all products on the first page.
    - Extracts normalized product information.
    - Returns a list of product dictionaries following
      the common schema.

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
)


LOGGER = logging.getLogger(__name__)

URL_MEGA_BEER = "https://online.mmvietnam.com/category/bia.html"

# BEST, STABLE SELECTOR
NEXT_BUTTON_SELECTOR = "button[aria-label='move to the next page']"

# ---------------------------------------------------------------------
# Driver & scroll helpers
# ---------------------------------------------------------------------
def init_driver(headless: bool = False) -> WebDriver:
    """
    Initialize and return a Chrome WebDriver instance.
    """
    return build_chrome_driver(headless=headless)


def go_to_next_page(driver: WebDriver, wait: WebDriverWait, timeout: int = 10) -> bool:
    """
    Click the "next page" button if it exists.

    Args:
        driver: Selenium WebDriver instance.
        wait: WebDriverWait instance for reuse.
        timeout: Max seconds to wait for the next button.

    Returns:
        True if we successfully clicked to a next page, False otherwise.
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
        LOGGER.info("Mega: no next page button found (stop pagination).")
        return False
    except Exception as exc: 
        LOGGER.warning("Mega: error when clicking next page: %s", exc)
        return False

def scroll_to_load_all(
    driver: WebDriver,
    total_time: int = 60,
    interval: int = 5,
) -> None:
    """
    Scroll the page multiple times to trigger lazy loading.

    Args:
        driver: Selenium WebDriver instance.
        total_time: Maximum total time to keep scrolling (seconds).
        interval: Delay between scrolls (seconds).
    """
    last_height = driver.execute_script(
        "return document.body.scrollHeight"
    )
    end_time = time.time() + total_time

    while time.time() < end_time:
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )
        LOGGER.info("Mega: scrolled to bottom, waiting %d seconds...", interval)
        time.sleep(interval)

        new_height = driver.execute_script(
            "return document.body.scrollHeight"
        )
        if new_height == last_height:
            LOGGER.info("Mega: no more new content loaded, stop scrolling.")
            break
        last_height = new_height


# ---------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------
def crawl_mega(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Crawl beer products from Mega Market and return a list of products.

    Steps:
        1. Open Mega beer category page.
        2. Scroll to load all products on the first page.
        3. Find all product cards on the page.
        4. For each card, extract name, price, URL, etc.
        5. Map into the common schema.

    Args:
        headless: If True, run the browser in headless mode.

    Returns:
        List of product dictionaries following the common schema.
    """
    driver = init_driver(headless=headless)
    products: List[Dict[str, Any]] = []
    crawl_date = datetime.now().strftime("%Y-%m-%d")

    try:
        LOGGER.info("Opening Mega beer page: %s", URL_MEGA_BEER)
        driver.get(URL_MEGA_BEER)

        wait = WebDriverWait(driver, 30)
        LOGGER.info("Waiting 5 seconds for initial Mega page load...")
        time.sleep(5)

        page_index = 1
        max_pages = 50 

        while page_index <= max_pages:
            LOGGER.info("Mega: processing page %d", page_index)

            scroll_to_load_all(driver, total_time=20, interval=5)

            product_list_selector = "div.gallery-module__items___YTUpR"
            product_item_selector = "div.item-module__root___hJBdd"
            name_selector = "a.item-module__name___IP-3e"
            price_selector = "div.item-module__finalPrice___zqAf5"
            original_price_selector = "div.item-module__oldPrice___b-kvC"
            link_selector = "a.item-module__images___1Ucb1"

            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, product_list_selector)
                )
            )
            container = driver.find_element(
                By.CSS_SELECTOR, product_list_selector
            )
            items = container.find_elements(
                By.CSS_SELECTOR, product_item_selector
            )
            LOGGER.info("Mega: found %d product elements on page %d.", len(items), page_index)


            for element in items:
                # -------------------------------------------------------------
                # Basic info: name & product URL
                # -------------------------------------------------------------
                try:
                    name = element.find_element(
                        By.CSS_SELECTOR, name_selector
                    ).text.strip()
                except Exception:
                    name = ""

                try:
                    link_element = element.find_element(
                        By.CSS_SELECTOR, link_selector
                    )
                    url = link_element.get_attribute("href")
                except Exception:
                    url = ""

                # -------------------------------------------------------------
                # Code & extra text in dnrInner
                # -------------------------------------------------------------
                code = ""
                note = ""

                try:
                    dnr_text = element.find_element(
                        By.CSS_SELECTOR,
                        "div[class^='item-module__dnrInner']",
                    ).text.strip()
                    if dnr_text:
                        # If it's like "DA53720045" -> treat as code
                        if re.fullmatch(r"[A-Za-z0-9]+", dnr_text):
                            code = dnr_text
                        else:
                            note = dnr_text
                except Exception:
                    pass

                # -------------------------------------------------------------
                # PRICES (Mega logic)
                # -------------------------------------------------------------
                # Final price
                try:
                    final_price_div = element.find_element(
                        By.CSS_SELECTOR,
                        "div.item-module__finalPrice___zqAf5",
                    )
                    final_price_text = final_price_div.get_attribute(
                        "innerText"
                    ).replace("\n", "").strip()
                except Exception:
                    final_price_text = ""

                # Old price
                try:
                    old_price_div = element.find_element(
                        By.CSS_SELECTOR,
                        "div.item-module__oldPrice___b-kvC",
                    )
                    old_price_text = old_price_div.get_attribute(
                        "innerText"
                    ).replace("\n", "").strip()
                except Exception:
                    old_price_text = ""

                # Promotion badge
                promo_source_text = ""
                try:
                    promo_badge = element.find_element(
                        By.CSS_SELECTOR,
                        "div[class^='item-module__discount']",
                    )
                    promo_source_text = promo_badge.get_attribute(
                        "innerText"
                    ).replace("\n", " ").strip()
                except Exception:
                    promo_source_text = ""

                final_price = extract_price_int(final_price_text)
                old_price = extract_price_int(old_price_text)
                promotion = extract_promotion_from_text(promo_source_text)


                # --------- LOGIC -----------
                if old_price > 0:
                    # Discount → final_price is the price after discount
                    price = old_price
                    price_after_promotion = final_price
                else:
                    # No discount → final_price is the original price
                    price = final_price
                    price_after_promotion = final_price

                # -------------------------------------------------------------
                # Parsing text: unit, packing, capacity, brand, etc.
                # -------------------------------------------------------------
                unit = extract_unit(name)
                packing = extract_packing_quantity(name)
                capacity = extract_capacity(name)
                brand = extract_brand(name)
                normalized_name = normalize_name(name)

                # Enforce allowed packings
                allowed_packings = {"1", "4", "6", "12", "20", "24"}
                if not packing:
                    packing = "1"
                elif packing not in allowed_packings:
                    packing = "1"

                # If no unit and price < 40,000 VND, assume a single can.
                if not unit and price and price < 40_000:
                    unit = "Lon"

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                product: Dict[str, Any] = {
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

                products.append(product)

            # 4) Try to go to the next page; if not, stop loop
            if not go_to_next_page(driver, wait):
                break

            page_index += 1

    finally:
        driver.quit()

    LOGGER.info("Mega crawl finished. Total products: %d", len(products))
    return products


if __name__ == "__main__":
    # Simple debug run: print 10 sample rows
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sample_products = crawl_mega(headless=False)
    print(f"Total products crawled from Mega: {len(sample_products)}")
    for row in sample_products[:10]:
        print(row)
