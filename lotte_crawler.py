"""
Lotte Mart beer products crawler.

This module defines a function `crawl_lotte` that:
    - Opens Lotte Mart beer category page.
    - Scrolls trang để load hết sản phẩm (lazy-load).
    - Extracts normalized product information theo common schema:
        source, code, name, brand, normalized_name, unit,
        packing, size, capacity, price,
        price_after_promotion, promotion, url, note, crawl_date,
        product_key.

Author: minhsangitdev (adapted for Lotte by ChatGPT)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

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


def _build_driver(headless: bool = True):
    """
    Khởi tạo Chrome WebDriver dùng helper chung.
    """
    return build_chrome_driver(headless=headless)

def _scroll_full_page(driver: webdriver.Chrome, total_time: int = 60, interval: int = 5) -> None:
    """
    Scroll trang liên tục để trigger lazy-load.

    Cứ mỗi `interval` giây:
        - scroll xuống cuối trang
        - chờ nửa khoảng thời gian
        - scroll ngược lên một chút
        - chờ nửa khoảng thời gian còn lại

    Chạy tổng thời gian ~ `total_time` giây.
    """
    start = time.time()
    last_height = driver.execute_script("return document.body.scrollHeight")

    while time.time() - start < total_time:
        # Scroll xuống cuối
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(interval / 2)

        # Nhún lên một chút để trigger lazy-load nếu có
        driver.execute_script(
            "window.scrollBy(0, -Math.floor(window.innerHeight * 0.3));"
        )
        time.sleep(interval / 2)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            # Không load thêm nữa
            break
        last_height = new_height


def crawl_lotte(headless: bool = True) -> List[Dict[str, object]]:
    """
    Crawl dữ liệu bia từ trang Lotte Mart.

    Returns
    -------
    List[Dict[str, object]]
        Danh sách product dictionaries với schema chung:
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
    products: List[Dict[str, object]] = []

    try:
        LOGGER.info("Opening Lotte URL: %s", LOTTE_URL)
        driver.get(LOTTE_URL)

        # Chờ container list sản phẩm xuất hiện
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.proudct-list")
                )
            )
            LOGGER.info("Lotte product list container found.")
        except Exception:
            LOGGER.warning("Không tìm thấy container 'proudct-list' trong timeout.")

        # Scroll để load hết sản phẩm
        _scroll_full_page(driver, total_time=60, interval=5)

        # Lấy toàn bộ items sản phẩm
        item_selector = "div.proudct-list div.item[itemtype='https://schema.org/Product']"
        elements = driver.find_elements(By.CSS_SELECTOR, item_selector)
        LOGGER.info("Found %d Lotte product items.", len(elements))

        crawl_date = datetime.now().strftime("%Y-%m-%d")

        for idx, element in enumerate(elements, start=1):
            try:
                # ------------------------
                # Name & URL
                # ------------------------
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

                # ------------------------
                # Code (parse từ href)
                # Ví dụ: /vi-nsg/product/...-18935012413328-p10826
                # Lấy dãy số trước -p...
                # ------------------------
                code = ""
                if href:
                    try:
                        path = href.split("/")[-1]  # "thung-...-18935012413328-p10826"
                        before_p = path.split("-p", maxsplit=1)[0]
                        code = before_p.split("-")[-1].strip()
                    except Exception:
                        code = ""

                # ------------------------
                # Giá sau khuyến mãi (giá đang hiển thị)
                # ------------------------
                price_after_text = ""
                price_after_int = 0

                # TH1: div.field-price span[itemprop='price']
                try:
                    price_span = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-price span[itemprop='price']",
                    )
                    price_after_text = price_span.text.strip()
                except Exception:
                    # TH2: price nằm trực tiếp trong div.field-price[itemprop='price']
                    try:
                        price_div = element.find_element(
                            By.CSS_SELECTOR,
                            "div.field-price[itemprop='price']",
                        )
                        price_after_text = price_div.text.strip()
                    except Exception:
                        price_after_text = ""

                price_after_int = extract_price_int(price_after_text)

                # ------------------------
                # Giá gốc (price)
                # ------------------------
                price_original_text = ""
                try:
                    price_original_text = element.find_element(
                        By.CSS_SELECTOR,
                        "div.field-price-old",
                    ).text.strip()
                except Exception:
                    price_original_text = ""

                price_original_int = extract_price_int(price_original_text)
                # Nếu không có giá gốc thì dùng giá đang bán
                price = price_original_int or price_after_int

                # ------------------------
                # Khuyến mãi: % giảm + text "Mua X tặng Y"
                # ------------------------
                promo_text_raw_parts = []

                # % giảm
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

                # Text "Mua 1 tặng 1..." trong field-more
                note = ""
                try:
                    more_div = element.find_element(By.CSS_SELECTOR, "div.field-more")
                    more_txt = more_div.text.strip()
                    if more_txt:
                        promo_text_raw_parts.append(more_txt)
                        note = more_txt  # ghi chú điều kiện vào note
                except Exception:
                    note = ""

                promo_text_raw = " ".join(promo_text_raw_parts).strip()
                promotion = extract_promotion_from_text(promo_text_raw)

                # ------------------------
                # Nếu không crawl được promotion nhưng có chênh lệch giá,
                # tự tính % giảm từ price và price_after_promotion
                # ------------------------
                if (not promotion) and price and price_after_int and price > price_after_int:
                    try:
                        discount = (price - price_after_int) * 100.0 / float(price)
                        # Làm tròn 2 chữ số
                        discount = round(discount, 2)
                        # Nếu là số nguyên (10.0) thì chỉ để "10%"
                        if abs(discount - int(discount)) < 1e-6:
                            promotion = f"{int(discount)}%"
                        else:
                            promotion = f"{discount}%"
                    except Exception:
                        # Nếu có lỗi khi tính toán thì bỏ qua, giữ promotion = ""
                        pass

                # ------------------------
                # Text-based parsing: unit, packing, capacity, brand,
                # pack type, normalized name, product key.
                # ------------------------
                unit = extract_unit(name) if name else ""
                packing = extract_packing_quantity(name) if name else ""
                capacity = extract_capacity(name) if name else ""
                brand = extract_brand(name) if name else ""

                # Logic packing giống BHX:
                # Enforce packing allowed set: [1, 4, 6, 12, 20, 24],
                # any missing or unexpected value is forced to "1".
                allowed_packings = {"1", "4", "6", "12", "20", "24"}
                if not packing:
                    packing = "1"
                elif packing not in allowed_packings:
                    packing = "1"

                normalized_name = normalize_name(name) if name else ""
                size = ""  # giống BHX, tạm để trống

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                product = {
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
                    # Giá sau khuyến mãi: LUÔN là giá final (điều kiện mua bao nhiêu thì ghi ở note)
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
                    "Lỗi khi parse product index %d: %s", idx, exc
                )
                continue

    finally:
        driver.quit()

    LOGGER.info("Lotte crawl finished. Total products: %d", len(products))
    return products


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = crawl_lotte(headless=False)
    print(f"Crawled {len(result)} products from Lotte.")
