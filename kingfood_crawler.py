"""
Kingfood Mart beer products crawler.

- URL: https://kingfoodmart.com/bia
- Sử dụng undetected_chromedriver để tránh bị chặn bot.
- Dùng nút "Xem thêm sản phẩm" để load tất cả sản phẩm.
- Mỗi product là 1 thẻ:
    <a class="pt-2" href="/bia-co-con/...">...</a>

Schema (không dùng pack_type):
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
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Dict
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
)

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://kingfoodmart.com"
CATEGORY_URL = "https://kingfoodmart.com/bia"

# XPATH cho product (ổn định hơn CSS class)
PRODUCT_XPATH = "//a[contains(@href, '/bia-co-con/')]"
SEE_MORE_XPATH = "//button[.//span[contains(normalize-space(.), 'Xem thêm sản phẩm')]]"

# packing cho phép (giống BHX)
ALLOWED_PACKINGS = {"1", "4", "6", "12", "20", "24"}


class StealthChrome(uc.Chrome):
    """
    Wrapper để tắt __del__ lỗi (WinError 6) của undetected_chromedriver trên Windows.
    """

    def __del__(self):
        # Không gọi self.quit() ở đây, vì ta đã quit trong finally của crawl_kingfood
        pass


def _build_driver(headless: bool = False) -> StealthChrome:
    """
    Tạo UC Chrome driver.
    headless=True có thể hoạt động, nhưng để debug nên để False.
    """
    if headless:
        driver = StealthChrome(headless=True)
    else:
        driver = StealthChrome()
    return driver


def _click_until_no_more(driver: StealthChrome) -> None:
    """
    Click nút "Xem thêm sản phẩm" cho đến khi KHÔNG còn nút nữa.
    Không dùng fixed max_clicks, chỉ dừng khi:
        - Không tìm được button nữa
        - Hoặc button không click được (exception)
    """
    while True:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, SEE_MORE_XPATH))
            )
        except Exception:
            LOGGER.info("Không còn nút 'Xem thêm sản phẩm' nữa. Stop click.")
            break

        try:
            LOGGER.info("Click nút 'Xem thêm sản phẩm'")
            driver.execute_script("arguments[0].click();", btn)
            # Đợi DOM append thêm sản phẩm, 1–2s là đủ với Kingfood
            time.sleep(1.5)
        except Exception as exc:
            LOGGER.warning("Lỗi khi click 'Xem thêm sản phẩm': %s", exc)
            break


def crawl_kingfood(headless: bool = False) -> List[Dict[str, object]]:
    """
    Crawl dữ liệu bia từ Kingfood Mart.

    Returns
    -------
    List[Dict[str, object]]:
        Danh sách dict sản phẩm theo schema:
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
    LOGGER.info("Starting Kingfood Mart crawler...")
    driver = _build_driver(headless=headless)
    products: List[Dict[str, object]] = []

    try:
        LOGGER.info("Opening Kingfood URL: %s", CATEGORY_URL)
        driver.get(CATEGORY_URL)

        # Đợi trang load React/JS lần đầu
        time.sleep(8)

        # Đảm bảo có ít nhất 1 sản phẩm trước khi bắt đầu click load thêm
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, PRODUCT_XPATH))
            )
            LOGGER.info("Initial products loaded.")
        except Exception:
            LOGGER.warning("Không tìm thấy sản phẩm bia ban đầu trong timeout.")

        # Click "Xem thêm sản phẩm" cho đến khi hết nút
        _click_until_no_more(driver)

        # Sau khi load hết, lấy toàn bộ product
        elements = driver.find_elements(By.XPATH, PRODUCT_XPATH)
        LOGGER.info("Found %d Kingfood product items.", len(elements))

        crawl_date = datetime.now().strftime("%Y-%m-%d")

        for idx, element in enumerate(elements, start=1):
            try:
                # ------------------------
                # href, url, code
                # ------------------------
                href = element.get_attribute("href") or ""
                url = urljoin(BASE_URL, href) if href else ""

                code = ""
                if href:
                    try:
                        code = href.rstrip("/").split("/")[-1]
                    except Exception:
                        code = ""

                # ------------------------
                # name
                # ------------------------
                try:
                    name_el = element.find_element(By.CSS_SELECTOR, "h3[title]")
                    name = name_el.text.strip()
                except Exception:
                    name = ""

                # ------------------------
                # Giá sau khuyến mãi (giá đang hiển thị)
                # ------------------------
                price_after_text = ""
                try:
                    price_div = element.find_element(
                        By.XPATH,
                        ".//div[contains(@class,'flex') and contains(@class,'items-baseline')]/div[1]",
                    )
                    price_after_text = price_div.text.strip()
                except Exception:
                    price_after_text = ""

                price_after_int = extract_price_int(price_after_text)

                # ------------------------
                # Giá gốc (nếu có)
                # ------------------------
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

                # ------------------------
                # Promo text & note
                # ------------------------
                promo_text_parts = []

                try:
                    overlay_div = element.find_element(
                        By.XPATH,
                        ".//div[contains(@class,'absolute') and contains(text(),'%')]",
                    )
                    overlay_text = overlay_div.text.strip()
                    if overlay_text:
                        promo_text_parts.append(overlay_text)
                except Exception:
                    overlay_text = ""

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
                        ".//div[@class='mb-1' and contains(@style,'height: 16px')]",
                    )
                    note_text = note_container.text.strip()
                    if note_text:
                        promo_text_parts.append(note_text)
                        note = note_text
                except Exception:
                    note = ""

                promo_text_raw = " ".join(promo_text_parts).strip()
                promotion = extract_promotion_from_text(promo_text_raw)

                if (not promotion) and price and price_after_int and price > price_after_int:
                    try:
                        discount = (price - price_after_int) * 100.0 / float(price)
                        discount = round(discount, 2)
                        if abs(discount - int(discount)) < 1e-6:
                            promotion = f"{int(discount)}%"
                        else:
                            promotion = f"{discount}%"
                    except Exception:
                        pass

                # ------------------------
                # Text-based parsing from name
                # ------------------------
                unit = extract_unit(name) if name else ""
                packing = extract_packing_quantity(name) if name else ""
                capacity = extract_capacity(name) if name else ""
                brand = extract_brand(name) if name else ""
                normalized_name = normalize_name(name) if name else ""
                size = "" 

                if not packing:
                    packing = "1"
                elif packing not in ALLOWED_PACKINGS:
                    packing = "1"

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                product = {
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
                LOGGER.warning("Lỗi khi parse product index %d: %s", idx, exc)
                continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    LOGGER.info("Kingfood crawl finished. Total products: %d", len(products))
    return products


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = crawl_kingfood(headless=False)
    print(f"Crawled {len(result)} products from Kingfood.")
