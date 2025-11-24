"""
Co.op Online beer products crawler.

- URL: https://cooponline.vn/c/bia
- When opening the page, a location popup is shown:
    + Form: provinceCode, districtCode, wardCode, address
    + Then a list of stores (class='css-ot6l9u')
  => The script will auto-select:
        - Ho Chi Minh City (if available),
        - the first district/ward,
        - address = "1",
        - any store in the list,
     then start crawling the beer list.

- Each product is a card:
    <div class="product-card ..." data-content-region-name="itemProductResult">
        <a href="/bia-corona-extra-24-x-250ml--s250101070"> ... </a>
    </div>

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
    - Run the Co.op crawler.
    - Export data to coop_beer_prices_YYYYMMDD.csv.
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
    make_unique_code,
)

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://cooponline.vn"
CATEGORY_URL = "https://cooponline.vn/c/bia"

ITEM_SELECTOR = "div.product-card[data-content-region-name='itemProductResult']"

ALLOWED_PACKINGS = {"1", "4", "6", "12", "20", "24"}


# ---------------------------------------------------------------------
# Driver helpers
# ---------------------------------------------------------------------
def _build_driver(headless: bool = False) -> webdriver.Chrome:
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


def _safe_click_element(
    driver: webdriver.Chrome,
    el: Any,
    desc: str,
) -> bool:
    """
    Scroll element into view and click it safely.

    Parameters
    ----------
    driver : webdriver.Chrome
    el : Any
        Web element to click.
    desc : str
        Description for logging.

    Returns
    -------
    bool
        True if click succeeded, False otherwise.
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            el,
        )
        time.sleep(0.2)

        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)

        LOGGER.info("Clicked: %s", desc)
        return True

    except Exception as exc:
        LOGGER.warning("Error clicking %s: %s", desc, exc)
        return False


def _click_option_by_text(
    driver: webdriver.Chrome,
    option_text: str,
    timeout: int = 20,
) -> bool:
    """
    Find and click an option within Co.op dropdowns by visible text.

    Parameters
    ----------
    driver : webdriver.Chrome
    option_text : str
        Visible label of the option.
    timeout : int
        Max wait time in seconds.

    Returns
    -------
    bool
        True if the option was clicked, False otherwise.
    """
    wait = WebDriverWait(driver, timeout)
    xpath = (
        "//div[contains(@class,'css-6sgxfm')]"
        "[.//div[contains(@class,'css-1k26lhb') "
        "and normalize-space()=%s]]"
    ) % repr(option_text)

    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        return _safe_click_element(driver, el, f"option '{option_text}'")

    except TimeoutException:
        LOGGER.warning("Timeout while locating option '%s'.", option_text)
        return False

    except Exception as exc:
        LOGGER.warning("Error clicking option '%s': %s", option_text, exc)
        return False


# ---------------------------------------------------------------------
# Popup handling (address + supermarket)
# ---------------------------------------------------------------------
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def handle_coop_address_popup(driver, timeout: int = 15) -> None:
    """
    Xử lý Popup 1: form chọn địa chỉ (Tỉnh/Thành, Quận/Huyện, Phường/Xã, Địa chỉ).

    - Chọn:
        + Thành phố Hồ Chí Minh
        + Huyện Bình Chánh
        + Xã Bình Hưng
        + Địa chỉ = "1"
    - Click nút "Xác nhận"
    """
    wait = WebDriverWait(driver, timeout)
    try:
        # Đợi popup hiện
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")
            )
        )
        LOGGER.info("Co.op: Popup chọn địa chỉ xuất hiện")

        # Chọn tỉnh/thành
        driver.find_element(By.ID, "provinceCode").click()
        time.sleep(0.8)
        driver.find_element(By.XPATH, "//div[text()='Thành phố Hồ Chí Minh']").click()
        time.sleep(1.2)

        # Chọn quận/huyện
        driver.find_element(By.ID, "districtCode").click()
        time.sleep(0.8)
        driver.find_element(By.XPATH, "//div[text()='Huyện Bình Chánh']").click()
        time.sleep(1.2)

        # Chọn phường/xã
        driver.find_element(By.ID, "wardCode").click()
        time.sleep(0.8)
        driver.find_element(By.XPATH, "//div[text()='Xã Bình Hưng']").click()
        time.sleep(0.5)

        # Nhập số nhà
        driver.find_element(By.ID, "address").send_keys("1")

        # Xác nhận
        driver.find_element(
            By.XPATH, "//button[contains(.,'Xác nhận')]"
        ).click()
        LOGGER.info("Co.op: Đã xác nhận địa chỉ")

        # Đợi popup đóng
        wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")
            )
        )
        LOGGER.info("Co.op: Popup địa chỉ đã đóng")
    except TimeoutException:
        LOGGER.info("Co.op: Không có popup địa chỉ (đã lưu trước đó)")


def handle_coop_supermarket_popup(driver, timeout: int = 20) -> None:
    """
    Xử lý Popup 2: chọn siêu thị + click "Mua sắm ngay".

    - Chọn siêu thị đầu tiên (class='css-ot6l9u')
    - Click nút "Mua sắm ngay" (button.css-18uoi51)
    """
    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")
            )
        )
        LOGGER.info("Co.op: Popup chọn siêu thị xuất hiện")

        # Chọn siêu thị đầu tiên
        first_store = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div.css-ot6l9u"))
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            first_store,
        )
        time.sleep(0.5)
        first_store.click()
        LOGGER.info("Co.op: Đã chọn siêu thị đầu tiên")

        # Click nút "Mua sắm ngay"
        buy_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.css-18uoi51"))
        )
        driver.execute_script("arguments[0].click();", buy_button)
        LOGGER.info("Co.op: ĐÃ CLICK THÀNH CÔNG 'Mua sắm ngay'")

        # Đợi popup đóng hoàn toàn
        wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")
            )
        )
        LOGGER.info("Co.op: Popup siêu thị đã đóng – HOÀN TẤT!")

    except TimeoutException:
        LOGGER.info("Co.op: Không có popup siêu thị (đã chọn trước đó)")
    except Exception as e:
        LOGGER.warning("Co.op: Lỗi khi xử lý popup siêu thị: %s", e)


# ---------------------------------------------------------------------
# Scrolling / pagination
# ---------------------------------------------------------------------
def _scroll_page(
    driver: webdriver.Chrome,
    max_clicks: int = 50,
    wait_seconds: int = 5,
) -> None:
    """
    Scroll page to the bottom and click 'View more products' repeatedly.

    Parameters
    ----------
    driver : webdriver.Chrome
    max_clicks : int
        Maximum times to attempt clicking the 'View more products' button.
    wait_seconds : int
        Sleep time between actions (seconds).
    """
    LOGGER.info(
        "Begin scrolling and clicking 'View more products' "
        "(max %d times)...",
        max_clicks,
    )

    last_height = driver.execute_script("return document.body.scrollHeight;")
    click_count = 0

    while click_count < max_clicks:
        try:
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
        except Exception as exc:
            LOGGER.warning("Error while scrolling: %s", exc)
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
            LOGGER.info("No more 'View more products' button. Stopping.")
            break

        except Exception as exc:
            LOGGER.warning(
                "Error clicking 'View more products' (attempt %d): %s",
                click_count + 1,
                exc,
            )
            break

        try:
            new_height = driver.execute_script(
                "return document.body.scrollHeight;"
            )
        except Exception:
            new_height = last_height

        if new_height == last_height:
            LOGGER.info("Page height did not change. Stop scrolling.")
            break

        last_height = new_height

    LOGGER.info(
        "Finished scrolling / clicking 'View more products'. "
        "Total clicks: %d",
        click_count,
    )


# ---------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------
def crawl_coop(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Crawl beer products from Co.op Online.

    Parameters
    ----------
    headless : bool
        Run browser in headless mode if True.

    Returns
    -------
    List[Dict[str, Any]]
        List of product dictionaries following the unified schema.
    """
    LOGGER.info("Starting Co.op Online crawler...")
    driver = _build_driver(headless=headless)
    products: List[Dict[str, Any]] = []

    try:
        LOGGER.info("Opening Co.op URL: %s", CATEGORY_URL)
        driver.get(CATEGORY_URL)

        # Xử lý popup địa chỉ
        time.sleep(5)
        handle_coop_address_popup(driver, timeout=15)

        # Xử lý popup chọn siêu thị + 'Mua sắm ngay'
        time.sleep(3)
        handle_coop_supermarket_popup(driver, timeout=20)


        time.sleep(5)
        LOGGER.info(
            "Start scrolling & clicking 'Xem thêm sản phẩm' "
            "to load all products..."
        )
        _scroll_page(driver, max_clicks=50, wait_seconds=5)
        LOGGER.info("Finished loading products. Start parsing product cards.")

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ITEM_SELECTOR))
            )
            LOGGER.info("Product cards are present in DOM.")
        except Exception:
            LOGGER.warning(
                "Could not find product-card elements within timeout."
            )

        elements = driver.find_elements(By.CSS_SELECTOR, ITEM_SELECTOR)
        time.sleep(10)
        LOGGER.info("Found %d Co.op product items.", len(elements))

        crawl_date = datetime.now().strftime("%Y-%m-%d")

        for idx, card in enumerate(elements, start=1):
            try:
                # ---------------------------------------------------------
                # href, url, code
                # ---------------------------------------------------------
                try:
                    a_tag = card.find_element(By.CSS_SELECTOR, "a[href]")
                    href = a_tag.get_attribute("href") or ""
                except Exception:
                    href = ""

                url = href if href.startswith("http") else urljoin(BASE_URL, href)

                # ---------------------------------------------------------
                # brand, name, unit
                # ---------------------------------------------------------

                try:
                    name_el = card.find_element(By.CSS_SELECTOR, "h3[title]")
                    name = name_el.text.strip()
                except Exception:
                    name = ""

                brand = extract_brand(name)

                unit = ""
                try:
                    # Example: "Đơn vị tính: Thùng"
                    unit_div = card.find_element(
                        By.CSS_SELECTOR,
                        "div.css-1f5a6jh",
                    )
                    unit_text = unit_div.text.strip()
                    if ":" in unit_text:
                        unit = unit_text.split(":", 1)[1].strip()
                    else:
                        unit = unit_text
                except Exception:
                    pass

                if not unit and name:
                    unit = extract_unit(name)

                # ---------------------------------------------------------
                # Prices: current & original
                # ---------------------------------------------------------
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

                # ---------------------------------------------------------
                # Promotion text & note
                # ---------------------------------------------------------
                promo_text_parts: List[str] = []

                # "TIẾT KIỆM <xxx ₫>"
                try:
                    tiet_kiem_value_div = card.find_element(
                        By.XPATH,
                        (
                            ".//div[contains(@class,'css-zb7zul')]"
                            "//div[contains(@class,'css-1rdv2qd')]"
                        ),
                    )
                    tiet_kiem_value = tiet_kiem_value_div.text.strip()
                    if tiet_kiem_value:
                        promo_text_parts.append(f"Tiết kiệm {tiet_kiem_value}")
                except Exception:
                    pass

                # Percentage badge, e.g. '-12%'
                try:
                    percent_div = card.find_element(
                        By.CSS_SELECTOR,
                        "div.css-9n4x1v",
                    )
                    percent_text = percent_div.text.strip()
                    if percent_text:
                        promo_text_parts.append(percent_text)
                except Exception:
                    pass

                note = ""  # No dedicated note observed on Co.op yet

                promo_text_raw = " ".join(promo_text_parts).strip()
                promotion = extract_promotion_from_text(promo_text_raw)

                # If no promotion parsed but price difference exists,
                # compute discount percentage.
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
                        pass

                # ---------------------------------------------------------
                # Text-based parsing from name
                # ---------------------------------------------------------
                packing = extract_packing_quantity(name) if name else ""
                capacity = extract_capacity(name) if name else ""

                if not brand and name:
                    brand = extract_brand(name)

                normalized_name = normalize_name(name) if name else ""
                size = ""  # Not used for now

                if not packing or packing not in ALLOWED_PACKINGS:
                    packing = "1"

                product_key = make_product_key(
                    brand=brand,
                    capacity=capacity,
                    packing=packing,
                )

                code = make_unique_code("coop", product_key, normalized_name)

                product: Dict[str, Any] = {
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
                LOGGER.warning(
                    "Error parsing Co.op product index %d: %s",
                    idx,
                    exc,
                )
                continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    LOGGER.info("Co.op crawl finished. Total products: %d", len(products))
    return products


# ---------------------------------------------------------------------
# Standalone execution (auto-export Co.op CSV)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = crawl_coop(headless=False)
    print(f"Crawled {len(result)} products from Co.op Online.")

    if not result:
        print("No products found, CSV will not be generated.")
    else:
        import csv

        today = datetime.now().strftime("%Y%m%d")
        output_path = f"coop_beer_prices_{today}.csv"

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=result[0].keys())
            writer.writeheader()
            writer.writerows(result)

        print(
            f"Co.op crawler finished → {len(result)} products "
            f"saved to {output_path}"
        )
