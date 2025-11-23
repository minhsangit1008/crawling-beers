"""
BachHoaXanh (BHX) beer products crawler.

This module defines a function `crawl_bhx` that:
    - Opens BHX beer category page.
    - Handles the 18+ age verification gate.
    - Scrolls the page multiple times to load all products.
    - Extracts normalized product information.
    - Returns a list of product dictionaries following
      a common schema.

Author: minhsangitdev
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from selenium.common.exceptions import TimeoutException, NoSuchElementException
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


def init_driver(headless: bool = False) -> WebDriver:
    """
    Initialize and return a Chrome WebDriver instance.

    Args:
        headless: If True, run Chrome in headless mode.

    Returns:
        Configured Chrome WebDriver.
    """
    # Dùng helper chung trong helpers.py
    return build_chrome_driver(headless=headless)



def handle_age_gate(driver: WebDriver, timeout: int = 10) -> None:
    """
    Bỏ qua popup xác nhận đủ 18 tuổi của BHX.

    - Điền đại một tên vào ô "Họ và tên".
    - Tick checkbox (nếu có).
    - Click nút "TÔI TRÊN 18 TUỔI".
    """
    try:
        wait = WebDriverWait(driver, timeout)

        # 1) Tìm ô nhập "Họ và tên"
        try:
            input_box = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[placeholder*='Họ và tên']")
                )
            )
        except TimeoutException:
            LOGGER.info("Không thấy popup 18+ trong thời gian chờ.")
            return

        # Điền tên bất kỳ
        try:
            input_box.clear()
            input_box.send_keys("Automated User")
        except Exception:
            LOGGER.warning("Không điền được ô tên trong popup 18+.")

        # 2) Tick checkbox "Không hiển thị lại nội dung này" (nếu có)
        try:
            checkbox = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            if not checkbox.is_selected():
                checkbox.click()
        except Exception:
            LOGGER.info("Không tìm thấy checkbox trong popup 18+ (bỏ qua).")

        time.sleep(0.5)

        # 3) Tìm và click nút có chữ 'trên' / 'tren'
        target_button: Optional[object] = None
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                label = btn.text.lower().strip()
                # chặt chẽ hơn một chút: ưu tiên 'trên 18'
                if "trên 18" in label or "tren 18" in label or "tôi trên 18" in label:
                    target_button = btn
                    break

            if target_button:
                target_button.click()
                LOGGER.info("Đã xác nhận popup 18+ (TÔI TRÊN 18 TUỔI).")
            else:
                LOGGER.warning("Không tìm thấy nút xác nhận 18+.")
        except Exception:
            LOGGER.warning("Không click được nút xác nhận 18+.")

    except Exception as exc:
        LOGGER.warning("Lỗi khi xử lý popup 18+: %s", exc)

def scroll_full_cycle(driver, total_time: int = 60, interval: int = 5) -> None:
    """
    Scroll up/down repeatedly to trigger lazy-loaded products.

    Every `interval` seconds:
        - scroll to bottom
        - wait half interval
        - bounce slightly up
        - wait half interval
    Runs for `total_time` seconds.
    """
    end_time = time.time() + total_time
    last_height = 0
    LOGGER.info(
        "Starting scroll cycles for %ds (interval %ds)...", total_time, interval
    )

    while time.time() < end_time:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(interval / 2)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")

        time.sleep(interval / 2)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height <= last_height:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        last_height = new_height

    LOGGER.info("Scrolling completed.")


def crawl_bhx(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Crawl beer products from BachHoaXanh and return a list of products.

    This function:
        1. Opens BHX beer category page.
        2. Handles the 18+ age verification gate (if present).
        3. Scrolls the page multiple times to load all products.
        4. Waits for the product container.
        5. Iterates all product items and extracts fields matching
           the common schema.

    Args:
        headless: If True, run the browser in headless mode.

    Returns:
        List of product dictionaries.
    """
    driver = init_driver(headless=headless)
    products: List[Dict[str, Any]] = []

    crawl_date = datetime.now().strftime("%Y-%m-%d")

    try:
        LOGGER.info("Opening BHX beer page: %s", URL_BHX_BEER)
        driver.get(URL_BHX_BEER)

        # Try to bypass age gate if it appears.
        handle_age_gate(driver)

        # Give the page some time to finish initial load
        LOGGER.info("Waiting 10 seconds for initial page load...")
        time.sleep(10)

        # Scroll to load all products (60s, every 5s)
        scroll_full_cycle(driver, total_time=60, interval=10)

        wait = WebDriverWait(driver, 90)

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

        product_selector = "div.this-item"
        items = container.find_elements(By.CSS_SELECTOR, product_selector)
        LOGGER.info("BHX: found %d product elements.", len(items))

        name_selector = "h3.product_name"
        price_selector = "div.product_price"

        for element in items:
            # -------------------------------------------------
            # Basic fields: name & URL
            # -------------------------------------------------
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

            # -------------------------------------------------
            # Product code:
            #   Case 1: "product-code" attribute on a div
            #   Case 2: id="product_<id>" on <a> tag
            # -------------------------------------------------
            code = ""

            try:
                code = element.find_element(
                    By.CSS_SELECTOR,
                    "div[product-code]",
                ).get_attribute("product-code").strip()
            except Exception:
                code = ""

            if not code:
                try:
                    anchor_tag = element.find_element(
                        By.CSS_SELECTOR,
                        "a[id^='product_']",
                    )
                    raw_id = anchor_tag.get_attribute("id")
                    code = raw_id.split("_", maxsplit=1)[-1].strip()
                except Exception:
                    code = ""

            # -------------------------------------------------
            # Current price (after promotion)
            # -------------------------------------------------
            try:
                price_after_text = element.find_element(
                    By.CSS_SELECTOR,
                    price_selector,
                ).text.strip()
            except Exception:
                price_after_text = ""

            # -------------------------------------------------
            # Original price & promotion text
            # -------------------------------------------------
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

            # -------------------------------------------------
            # Text-based parsing: unit, packing, capacity, brand,
            # normalized name, product key.
            # -------------------------------------------------
            unit = extract_unit(name)
            packing = extract_packing_quantity(name)
            capacity = extract_capacity(name)
            brand = extract_brand(name)
            normalized_name = normalize_name(name)

            # Enforce packing allowed set: [1, 4, 6, 12, 20, 24],
            # any missing or unexpected value is forced to "1".
            allowed_packings = {"1", "4", "6", "12", "20", "24"}
            if not packing:
                packing = "1"
            elif packing not in allowed_packings:
                packing = "1"

            # -------------------------------------------------
            # Price conversion
            # -------------------------------------------------
            price_after_int = extract_price_int(price_after_text)
            price_original_int = extract_price_int(price_original_text)

            price = price_original_int or price_after_int

            # If no unit and price < 40,000 VND, assume it is a single can.
            if not unit and price and price < 40_000:
                unit = "Lon"

            product_key = make_product_key(
                brand=brand,
                capacity=capacity,
                packing=packing,
            )

            # -------------------------------------------------
            # Build product record with common schema
            # -------------------------------------------------
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
        driver.quit()

    LOGGER.info("BHX crawl finished. Total products: %d", len(products))
    return products
