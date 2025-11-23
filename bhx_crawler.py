"""
BachHoaXanh (BHX) beer products crawler.

This module defines a function `crawl_bhx` that:
    - Opens BHX beer category page.
    - Handles the 18+ age verification gate.
    - Scrolls the page multiple times to load all products.
    - Extracts normalized product information.
    - Returns a list of product dictionaries following
      a common schema.

If this module is executed directly, it will:
    - Run the BHX crawler.
    - Export data to bhx_beer_prices_YYYYMMDD.csv.

Author: minhsangitdev
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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

URL_BHX_BEER = "https://www.bachhoaxanh.com/bia"

LOGGER = logging.getLogger(__name__)

ALLOWED_PACKINGS = {"1", "4", "6", "12", "20", "24"}


# ---------------------------------------------------------------------
# Driver & scrolling helpers
# ---------------------------------------------------------------------
def init_driver(headless: bool = False) -> WebDriver:
    """
    Initialize and return a Chrome WebDriver instance.

    Parameters
    ----------
    headless : bool
        If True, run Chrome in headless mode.

    Returns
    -------
    WebDriver
        Configured Chrome WebDriver.
    """
    return build_chrome_driver(headless=headless)


def handle_age_gate(driver: WebDriver, timeout: int = 10) -> None:
    """
    Bypass BHX 18+ age verification popup if present.

    Steps
    -----
    1. Fill a dummy name into the "Họ và tên" input.
    2. Tick the "Do not show again" checkbox if it exists.
    3. Click the "TÔI TRÊN 18 TUỔI" (I'm over 18) button.

    Parameters
    ----------
    driver : WebDriver
    timeout : int
        Maximum wait time for the popup elements.
    """
    try:
        wait = WebDriverWait(driver, timeout)

        # 1) Find the "Họ và tên" input box
        try:
            input_box = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[placeholder*='Họ và tên']")
                )
            )
        except TimeoutException:
            LOGGER.info(
                "18+ popup not detected within timeout. Continue normally."
            )
            return

        # Fill any placeholder name
        try:
            input_box.clear()
            input_box.send_keys("Automated User")
        except Exception:
            LOGGER.warning(
                "Could not fill name field in 18+ popup (continue anyway)."
            )

        # 2) Checkbox "Không hiển thị lại nội dung này" (if present)
        try:
            checkbox = driver.find_element(
                By.CSS_SELECTOR,
                "input[type='checkbox']",
            )
            if not checkbox.is_selected():
                checkbox.click()
        except Exception:
            LOGGER.info(
                "Checkbox in 18+ popup not found (skip ticking checkbox)."
            )

        time.sleep(0.5)

        # 3) Find and click button with text containing "trên 18"
        target_button: Optional[Any] = None
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                label = btn.text.lower().strip()
                if (
                    "trên 18" in label
                    or "tren 18" in label
                    or "tôi trên 18" in label
                ):
                    target_button = btn
                    break

            if target_button:
                target_button.click()
                LOGGER.info("18+ popup: clicked 'TÔI TRÊN 18 TUỔI' button.")
            else:
                LOGGER.warning(
                    "18+ popup: confirmation button not found by text."
                )
        except Exception:
            LOGGER.warning(
                "18+ popup: error while clicking confirmation button."
            )

    except Exception as exc:
        LOGGER.warning("Error while handling 18+ popup: %s", exc)


# def scroll_full_cycle(
#     driver: WebDriver,
#     total_time: int = 60,
#     interval: int = 5,
# ) -> None:
#     """
#     Scroll up/down repeatedly to trigger lazy-loaded products.

#     Every `interval` seconds:
#         - Scroll to the bottom.
#         - Wait half of the interval.
#         - Scroll back up to the middle of the page.
#         - Wait the remaining half of the interval.

#     The function runs for approximately `total_time` seconds.

#     Parameters
#     ----------
#     driver : WebDriver
#     total_time : int
#         Total duration (in seconds) to keep scrolling.
#     interval : int
#         Delay between scroll movements (seconds).
#     """
#     end_time = time.time() + total_time
#     last_height = 0
#     LOGGER.info(
#         "Starting scroll cycles for %ds (interval %ds)...",
#         total_time,
#         interval,
#     )

#     while time.time() < end_time:
#         # Scroll to the bottom
#         driver.execute_script(
#             "window.scrollTo(0, document.body.scrollHeight);"
#         )
#         time.sleep(interval / 2)

#         # Scroll back to around the middle
#         driver.execute_script(
#             "window.scrollTo(0, document.body.scrollHeight / 2);"
#         )
#         time.sleep(interval / 2)

#         new_height = driver.execute_script(
#             "return document.body.scrollHeight"
#         )
#         if new_height <= last_height:
#             # Nudge a bit, in case lazy-load is triggered around 60% height
#             driver.execute_script(
#                 "window.scrollTo(0, document.body.scrollHeight * 0.6);"
#             )
#         last_height = new_height

#     LOGGER.info("Scrolling completed.")
def scroll_up_down_loop(driver, loops: int = 10, steps_per_scroll: int = 10, delay: float = 1.5):
    """
    Scroll từ từ xuống cuối trang rồi nhảy về giữa trang, lặp lại 'loops' lần.
    """
    LOGGER.info(f"Starting scroll loop: {loops} loops, each with {steps_per_scroll} steps...")

    for loop in range(1, loops + 1):
        LOGGER.info(f"--- Loop {loop}/{loops}: scrolling DOWN ---")

        # Scroll từ từ xuống cuối trang
        for step in range(1, steps_per_scroll + 1):
            driver.execute_script(
                f"window.scrollTo(0, document.body.scrollHeight * {step/steps_per_scroll});"
            )
            time.sleep(delay)

        LOGGER.info(f"--- Loop {loop}/{loops}: jump to MIDDLE ---")

        # Nhảy ngay về giữa trang, không scroll từ từ
        time.sleep(5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
        time.sleep(delay)

    LOGGER.info("Completed full up-down-middle scrolling loops.")




# ---------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------
def crawl_bhx(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Crawl beer products from BachHoaXanh.

    Steps
    -----
    1. Open BHX beer category page.
    2. Handle the 18+ age verification gate (if present).
    3. Scroll the page multiple times to load all products.
    4. Wait for the product container to appear.
    5. Iterate product items and extract fields matching the
       unified schema.

    Parameters
    ----------
    headless : bool
        Run browser in headless mode if True.

    Returns
    -------
    List[Dict[str, Any]]
        List of product dictionaries.
    """
    driver = init_driver(headless=headless)
    products: List[Dict[str, Any]] = []
    crawl_date = datetime.now().strftime("%Y-%m-%d")

    try:
        LOGGER.info("Opening BHX beer page: %s", URL_BHX_BEER)
        driver.get(URL_BHX_BEER)

        # Try to bypass age gate if it appears
        handle_age_gate(driver)

        # Allow some time for initial page load
        LOGGER.info("Waiting 5 seconds for initial BHX page load...")
        time.sleep(5)

        # Scroll to load all products
        # scroll_full_cycle(driver, total_time=60, interval=10)
        scroll_up_down_loop(driver, loops=10, steps_per_scroll=10, delay=1.5)




        wait = WebDriverWait(driver, 90)

        # Main container that holds product items
        container_selector = "div.-mt-1.-mx-1.flex.flex-wrap.content-stretch.px-0"
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, container_selector)
            )
        )
        container = driver.find_element(By.CSS_SELECTOR, container_selector)

        product_selector = "div.this-item"
        items = container.find_elements(By.CSS_SELECTOR, product_selector)
        LOGGER.info("BHX: found %d product elements.", len(items))

        name_selector = "h3.product_name"
        price_selector = "div.product_price"

        for element in items:
            # ---------------------------------------------------------
            # Basic fields: name & URL
            # ---------------------------------------------------------
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

            # ---------------------------------------------------------
            # Product code:
            #   Case 1: "product-code" attribute on a div
            #   Case 2: id="product_<id>" on <a> tag
            # ---------------------------------------------------------
            code = ""

            try:
                code = (
                    element.find_element(
                        By.CSS_SELECTOR,
                        "div[product-code]",
                    )
                    .get_attribute("product-code")
                    .strip()
                )
            except Exception:
                code = ""

            if not code:
                try:
                    anchor_tag = element.find_element(
                        By.CSS_SELECTOR,
                        "a[id^='product_']",
                    )
                    raw_id = anchor_tag.get_attribute("id") or ""
                    code = raw_id.split("_", maxsplit=1)[-1].strip()
                except Exception:
                    code = ""

            # ---------------------------------------------------------
            # Current price (after promotion)
            # ---------------------------------------------------------
            try:
                price_after_text = element.find_element(
                    By.CSS_SELECTOR,
                    price_selector,
                ).text.strip()
            except Exception:
                price_after_text = ""

            # ---------------------------------------------------------
            # Original price & promotion text block
            # ---------------------------------------------------------
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

            promotion = extract_promotion_from_text(promotion_text_raw)

            # ---------------------------------------------------------
            # Text-based parsing: unit, packing, capacity, brand,
            # normalized name, product key.
            # ---------------------------------------------------------
            unit = extract_unit(name)
            packing = extract_packing_quantity(name)
            capacity = extract_capacity(name)
            brand = extract_brand(name)
            normalized_name = normalize_name(name)

            # Enforce allowed packing set
            if not packing or packing not in ALLOWED_PACKINGS:
                packing = "1"

            # ---------------------------------------------------------
            # Price conversion
            # ---------------------------------------------------------
            price_after_int = extract_price_int(price_after_text)
            price_original_int = extract_price_int(price_original_text)
            price = price_original_int or price_after_int

            # If no promotion parsed but there is a price difference,
            # optionally compute a discount percentage.
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
                    # If calculation fails, keep promotion as empty.
                    pass

            # If no unit and price < 40,000 VND, assume a single can
            if not unit and price and price < 40_000:
                unit = "Lon"

            product_key = make_product_key(
                brand=brand,
                capacity=capacity,
                packing=packing,
            )

            # ---------------------------------------------------------
            # Build product record with common schema
            # ---------------------------------------------------------
            product: Dict[str, Any] = {
                "source": "bachhoaxanh",
                "code": code,
                "name": name,
                "brand": brand,
                "normalized_name": normalized_name,
                "unit": unit,
                "packing": packing,
                "size": "",
                "capacity": capacity,
                "price": price,
                "price_after_promotion": price_after_int,
                "promotion": promotion,
                "url": url,
                "note": "",
                "crawl_date": crawl_date,
                "product_key": product_key,
            }

            products.append(product)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    LOGGER.info("BHX crawl finished. Total products: %d", len(products))
    return products


# ---------------------------------------------------------------------
# Standalone execution (auto-export BHX CSV)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = crawl_bhx(headless=False)
    print(f"Crawled {len(result)} products from BachHoaXanh.")

    if not result:
        print("No products found, CSV will not be generated.")
    else:
        import csv

        today = datetime.now().strftime("%Y%m%d")
        output_path = f"bhx_beer_prices_{today}.csv"

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=result[0].keys())
            writer.writeheader()
            writer.writerows(result)

        print(
            f"BHX crawler finished → {len(result)} products "
            f"saved to {output_path}"
        )