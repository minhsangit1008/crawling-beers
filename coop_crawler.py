"""
Co.op Online beer products crawler.

- URL: https://cooponline.vn/c/bia
- Khi mở trang sẽ hiện popup chọn địa chỉ:
    + Form: provinceCode, districtCode, wardCode, address
    + Sau đó danh sách siêu thị (class=css-ot6l9u)
  => Script sẽ auto chọn Hồ Chí Minh (nếu có), quận/huyện/phường đầu tiên,
     address = "1", chọn 1 siêu thị bất kỳ rồi mới crawl list bia.

- Mỗi product là 1 thẻ:
    <div class="product-card ..." data-content-region-name="itemProductResult">
        <a href="/bia-corona-extra-24-x-250ml--s250101070"> ... </a>
    </div>

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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


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

BASE_URL = "https://cooponline.vn"
CATEGORY_URL = "https://cooponline.vn/c/bia"

ITEM_SELECTOR = "div.product-card[data-content-region-name='itemProductResult']"

ALLOWED_PACKINGS = {"1", "4", "6", "12", "20", "24"}


def _build_driver(headless: bool = False):
    """
    Initialize Chrome WebDriver using a common helper.
    """
    return build_chrome_driver(headless=headless)


def _safe_click_element(driver: webdriver.Chrome, el, desc: str) -> bool:
    """
    Scroll to the center of the screen and click the element safely.
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", el
        )
        time.sleep(0.2)
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        LOGGER.info("Clicked: %s", desc)
        return True
    except Exception as exc:
        LOGGER.warning("Lỗi khi click %s: %s", desc, exc)
        return False


def _click_option_by_text(
    driver: webdriver.Chrome,
    option_text: str,
    timeout: int = 20,
) -> bool:
    wait = WebDriverWait(driver, timeout)
    xpath = (
        "//div[contains(@class,'css-6sgxfm')]"
        "[.//div[contains(@class,'css-1k26lhb') and normalize-space()=%s]]"
    ) % repr(option_text)

    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        return _safe_click_element(driver, el, f"option '{option_text}'")
    except TimeoutException:
        LOGGER.warning("Timeout khi tìm option '%s'", option_text)
        return False
    except Exception as exc:
        LOGGER.warning("Lỗi khi click option '%s': %s", option_text, exc)
        return False


def _handle_location_popup(driver: webdriver.Chrome, timeout: int = 40) -> None:
    LOGGER.info("Handling location popup (by index dropdown)...")
    wait = WebDriverWait(driver, timeout)

    # Chờ form hiện các ô chọn (css-6sgxfm)
    try:
        dropdown_xpath = (
            "//div[contains(@class,'css-6sgxfm')]"
            "[.//div[contains(@class,'css-1cxxswr')]"
            " and .//div[contains(@class,'css-1k26lhb')]]"
        )
        dropdowns = wait.until(
            EC.presence_of_all_elements_located((By.XPATH, dropdown_xpath))
        )
        LOGGER.info("Tìm thấy %d ô 'css-6sgxfm' trong popup.", len(dropdowns))
    except TimeoutException:
        LOGGER.warning("Address form not found (css-6sgxfm). Ignore popup.")
        return

    if len(dropdowns) < 3:
        LOGGER.warning(
            "Number of dropdowns < 3 (len=%d), DOM may be different. Ignore popup.",
            len(dropdowns),
        )
        return

    def open_and_select(idx: int, desc: str, option_text: str) -> None:
        try:
            # Re-find all dropdowns each time to avoid stale elements
            dropdowns_local = wait.until(
                EC.presence_of_all_elements_located((By.XPATH, dropdown_xpath))
            )
            if idx >= len(dropdowns_local):
                LOGGER.warning(
                    "Not enough dropdowns to select %s (idx=%d, len=%d)",
                    desc,
                    idx,
                    len(dropdowns_local),
                )
                return

            field_el = dropdowns_local[idx]
            _safe_click_element(driver, field_el, f"open dropdown {desc}")
            time.sleep(0.5)

            clicked = _click_option_by_text(driver, option_text, timeout=20)
            if not clicked:
                LOGGER.warning(
                    "Cannot select option '%s' cho %s.", option_text, desc
                )
            else:
                time.sleep(0.7)
        except Exception as exc:
            LOGGER.warning("Failed %s: %s", desc, exc)

    open_and_select(
        idx=0,
        desc="Province",
        option_text="Thành phố Hồ Chí Minh",
    )

    open_and_select(
        idx=1,
        desc="District",
        option_text="Huyện Bình Chánh",
    )

    open_and_select(
        idx=2,
        desc="Ward",
        option_text="Xã Bình Hưng",
    )

    try:
        try:
            addr_input = wait.until(
                EC.presence_of_element_located((By.ID, "address"))
            )
        except TimeoutException:
            addr_input = wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//input[@id='address' or @name='address' or "
                        "contains(@placeholder,'Địa chỉ') or "
                        "contains(@placeholder,'địa chỉ')]",
                    )
                )
            )
        _safe_click_element(driver, addr_input, "input address")
        addr_input.clear()
        addr_input.send_keys("1")
        LOGGER.info("Filled address = '1'.")
        time.sleep(0.5)
    except Exception as exc:
        LOGGER.warning("Failed: %s", exc)

    try:
        confirm_xpath = (
            "//button[contains(normalize-space(),'Xác nhận') "
            "or .//div[contains(normalize-space(),'Xác nhận')]]"
        )
        try:
            confirm_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, confirm_xpath))
            )
            _safe_click_element(driver, confirm_btn, "button 'Xác nhận'")
            time.sleep(2)
        except TimeoutException:
            LOGGER.info("Don't see 'Confirm' button, maybe form auto move to next step.")
    except Exception as exc:
        LOGGER.warning("Error processing 'Confirm' button': %s", exc)

    try:
        store_xpath = (
            "//span[contains(@class,'css-1vgbj23') and "
            "contains(normalize-space(),'Co.opXtra Tạ Quang Bửu')]"
            "/ancestor::div[contains(@class,'teko-row') and "
            "contains(@class,'css-1qrgscw')]"
        )
        store_el = WebDriverWait(driver, 25).until(
            EC.element_to_be_clickable((By.XPATH, store_xpath))
        )
        _safe_click_element(
            driver,
            store_el,
            "store 'Co.opXtra Tạ Quang Bửu'",
        )
        time.sleep(2)
    except TimeoutException:
        LOGGER.warning("Timeout'.")
    except Exception as exc:
        LOGGER.warning("Fail: %s", exc)

    try:
        buy_btn_xpath = (
            "//button[.//div[contains(@class,'button-text') and "
            "contains(normalize-space(),'Mua sắm ngay')]]"
        )
        buy_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, buy_btn_xpath))
        )
        _safe_click_element(driver, buy_btn, "button 'Mua sắm ngay'")
        time.sleep(3)
    except TimeoutException:
        LOGGER.warning("Timeout 'Mua sắm ngay'.")
    except Exception as exc:
        LOGGER.warning("Failed 'Mua sắm ngay': %s", exc)

    LOGGER.info("Done handling location popup.")



def _scroll_page(
    driver: webdriver.Chrome,
    max_clicks: int = 50,
    wait_seconds: int = 5,
) -> None:

    LOGGER.info(
        "Start scrolling and click 'View more products' (max %d times)...",
        max_clicks,
    )

    last_height = driver.execute_script("return document.body.scrollHeight;")
    click_count = 0

    while click_count < max_clicks:
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception as exc:
            LOGGER.warning("Lỗi khi scroll: %s", exc)
        time.sleep(wait_seconds)

        try:
            load_more_xpath = (
                "//a[contains(@class,'css-b0m1yo') and "
                ".//div[contains(@class,'button-text') and "
                "contains(normalize-space(),'Xem thêm sản phẩm')]]"
            )
            load_more = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, load_more_xpath))
            )
            driver.execute_script("arguments[0].click();", load_more)
            click_count += 1
            LOGGER.info(
                "Clicked 'Xem thêm sản phẩm' (%d/%d).",
                click_count,
                max_clicks,
            )
            time.sleep(wait_seconds)
        except TimeoutException:
            LOGGER.info("No more 'View more products' button. Stop.")
            break
        except Exception as exc:
            LOGGER.warning(
                "Error when clicking 'View more products' (time %d): %s",
                click_count + 1,
                exc,
            )
            break

        try:
            new_height = driver.execute_script("return document.body.scrollHeight;")
        except Exception:
            new_height = last_height

        if new_height == last_height:
            LOGGER.info(
                "Page height does not change after click, stop scrolling."
            )
            break

        last_height = new_height

    LOGGER.info(
        "Finish scrolling and click 'View more products'. Total number of clicks: %d",
        click_count,
    )

def crawl_coop(headless: bool = False) -> List[Dict[str, object]]:
    LOGGER.info("Starting Co.op Online crawler...")
    driver = _build_driver(headless=headless)
    products: List[Dict[str, object]] = []

    try:
        LOGGER.info("Opening Co.op URL: %s", CATEGORY_URL)
        driver.get(CATEGORY_URL)

        time.sleep(5)
        _handle_location_popup(driver, timeout=40)

        time.sleep(5)
        LOGGER.info("Bắt đầu scroll & click 'Xem thêm sản phẩm' để load toàn bộ sản phẩm...")
        _scroll_page(driver, max_clicks=50, wait_seconds=5)
        LOGGER.info("Hoàn thành load sản phẩm, bắt đầu lấy product-card.")



        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ITEM_SELECTOR))
            )
            LOGGER.info("Product cards loaded.")
        except Exception:
            LOGGER.warning("Không tìm thấy product-card trong timeout.")

        elements = driver.find_elements(By.CSS_SELECTOR, ITEM_SELECTOR)
        LOGGER.info("Found %d Co.op product items.", len(elements))

        crawl_date = datetime.now().strftime("%Y-%m-%d")

        for idx, card in enumerate(elements, start=1):
            try:
                # ------------------------
                # href, url, code
                # ------------------------
                try:
                    a_tag = card.find_element(By.CSS_SELECTOR, "a[href]")
                    href = a_tag.get_attribute("href") or ""
                except Exception:
                    href = ""

                url = href if href.startswith("http") else urljoin(BASE_URL, href)

                code = card.get_attribute("data-content-name") or ""
                if not code and href:
                    try:
                        code = href.rstrip("/").split("/")[-1]
                    except Exception:
                        code = ""

                # ------------------------
                # brand, name, unit
                # ------------------------
                try:
                    brand_el = card.find_element(
                        By.CSS_SELECTOR, "div.product-brand-name"
                    )
                    brand = brand_el.text.strip()
                except Exception:
                    brand = ""

                try:
                    name_el = card.find_element(By.CSS_SELECTOR, "h3[title]")
                    name = name_el.text.strip()
                except Exception:
                    name = ""

                unit = ""
                try:
                    # "Đơn vị tính: Thùng"
                    unit_div = card.find_element(By.CSS_SELECTOR, "div.css-1f5a6jh")
                    unit_text = unit_div.text.strip()
                    if ":" in unit_text:
                        unit = unit_text.split(":", 1)[1].strip()
                    else:
                        unit = unit_text
                except Exception:
                    pass

                if not unit and name:
                    unit = extract_unit(name)

                # ------------------------
                # Giá hiện tại & giá gốc
                # ------------------------
                price_after_text = ""
                try:
                    latest_price_div = card.find_element(
                        By.CSS_SELECTOR,
                        "div.att-product-detail-latest-price",
                    )
                    price_after_text = latest_price_div.text.strip()
                except Exception:
                    pass
                price_after_int = extract_price_int(price_after_text)

                price_original_text = ""
                try:
                    retail_price_div = card.find_element(
                        By.CSS_SELECTOR,
                        "div.att-product-detail-retail-price",
                    )
                    price_original_text = retail_price_div.text.strip()
                except Exception:
                    pass
                price_original_int = extract_price_int(price_original_text)

                price = price_original_int or price_after_int

                # ------------------------
                # Promo text & note
                # ------------------------
                promo_text_parts = []

                # "TIẾT KIỆM <xxx ₫>"
                try:
                    tiet_kiem_value_div = card.find_element(
                        By.XPATH,
                        ".//div[contains(@class,'css-zb7zul')]//div[contains(@class,'css-1rdv2qd')]",
                    )
                    tiet_kiem_value = tiet_kiem_value_div.text.strip()
                    if tiet_kiem_value:
                        promo_text_parts.append(f"Tiết kiệm {tiet_kiem_value}")
                except Exception:
                    pass

                # phần trăm -12% cạnh giá gốc
                try:
                    percent_div = card.find_element(
                        By.CSS_SELECTOR, "div.css-9n4x1v"
                    )
                    percent_text = percent_div.text.strip()
                    if percent_text:
                        promo_text_parts.append(percent_text)
                except Exception:
                    pass

                note = ""  # hiện chưa thấy note riêng trên Co.op (voucher, etc.)

                promo_text_raw = " ".join(promo_text_parts).strip()
                promotion = extract_promotion_from_text(promo_text_raw)

                # Nếu không crawl được promotion nhưng có chênh lệch giá,
                # tự tính % giảm từ price và price_after_promotion
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
                # Text-based parsing từ name
                # ------------------------
                packing = extract_packing_quantity(name) if name else ""
                capacity = extract_capacity(name) if name else ""

                if not brand and name:
                    brand = extract_brand(name)

                normalized_name = normalize_name(name) if name else ""
                size = ""  # chưa dùng

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
                    "source": "cooponline",
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
        driver.quit()

    LOGGER.info("Co.op crawl finished. Total products: %d", len(products))
    return products


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = crawl_coop(headless=False)
    print(f"Crawled {len(result)} products from Co.op Online.")
