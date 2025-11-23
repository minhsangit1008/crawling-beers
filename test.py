import time
import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

LOGGER = logging.getLogger(__name__)
URL = "https://cooponline.vn/c/bia"


def build_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Khởi tạo Chrome WebDriver.
    Để debug popup nên để headless=False cho dễ quan sát.
    """
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def handle_location_popup(driver, timeout: int = 40) -> None:
    """
    Xử lý popup địa chỉ của Co.op Online.

    Bước 1: form địa chỉ
        - Chọn Tỉnh/Thành phố (id='provinceCode')
        - Chọn Quận/Huyện (id='districtCode')
        - Chọn Phường/Xã (id='wardCode')
        - Nhập địa chỉ cụ thể (id='address') = "1"
        - Click nút 'Xác nhận'

    Bước 2: chọn siêu thị
        - Click 1 phần tử bất kỳ có class 'css-ot6l9u' (chọn siêu thị bất kỳ)
    """

    LOGGER.info("Handling location popup...")

    # ----- Bước 1: form địa chỉ -----
    try:
        # Chờ select tỉnh/thành xuất hiện
        province_select_el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, "provinceCode"))
        )
        LOGGER.info("Found province select (provinceCode).")
    except Exception as exc:
        LOGGER.warning("Không tìm thấy form địa chỉ (provinceCode): %s", exc)
        return

    # Tỉnh/Thành phố
    try:
        province_sel = Select(province_select_el)
        selected = False

        # Ưu tiên chọn Hồ Chí Minh nếu có
        province_candidates = [
            "Thành Phố Hồ Chí Minh",
            "TP. Hồ Chí Minh",
            "TP Hồ Chí Minh",
            "Hồ Chí Minh",
        ]
        for text in province_candidates:
            try:
                province_sel.select_by_visible_text(text)
                LOGGER.info("Selected province: %s", text)
                selected = True
                break
            except Exception:
                continue

        # Nếu không tìm thấy đúng text, chọn option đầu tiên khác rỗng
        if not selected:
            for opt in province_sel.options:
                if opt.get_attribute("value"):
                    province_sel.select_by_value(opt.get_attribute("value"))
                    LOGGER.info(
                        "Selected province by first non-empty option: %s", opt.text
                    )
                    break
        time.sleep(1)
    except Exception as exc:
        LOGGER.warning("Lỗi khi chọn Tỉnh/Thành phố: %s", exc)

    # Quận/Huyện
    try:
        district_select_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "districtCode"))
        )
        district_sel = Select(district_select_el)
        for opt in district_sel.options:
            if opt.get_attribute("value"):
                district_sel.select_by_value(opt.get_attribute("value"))
                LOGGER.info("Selected district: %s", opt.text)
                break
        time.sleep(1)
    except Exception as exc:
        LOGGER.warning("Lỗi khi chọn Quận/Huyện: %s", exc)

    # Phường/Xã
    try:
        ward_select_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "wardCode"))
        )
        ward_sel = Select(ward_select_el)
        for opt in ward_sel.options:
            if opt.get_attribute("value"):
                ward_sel.select_by_value(opt.get_attribute("value"))
                LOGGER.info("Selected ward: %s", opt.text)
                break
        time.sleep(1)
    except Exception as exc:
        LOGGER.warning("Lỗi khi chọn Phường/Xã: %s", exc)

    # Địa chỉ cụ thể
    try:
        addr_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "address"))
        )
        addr_input.clear()
        addr_input.send_keys("1")
        LOGGER.info("Filled address = '1'.")
        time.sleep(0.5)
    except Exception as exc:
        LOGGER.warning("Lỗi khi nhập địa chỉ: %s", exc)

    # Nút "Xác nhận"
    try:
        confirm_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(normalize-space(.), 'Xác nhận')]")
            )
        )
        LOGGER.info("Click 'Xác nhận'.")
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(3)
    except Exception as exc:
        LOGGER.warning("Không bấm được nút 'Xác nhận': %s", exc)

    # ----- Bước 2: chọn siêu thị bất kỳ (class css-ot6l9u) -----
    try:
        # chờ danh sách siêu thị render
        store_el = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "css-ot6l9u"))
        )
        LOGGER.info("Click first store card (class=css-ot6l9u).")
        driver.execute_script("arguments[0].click();", store_el)
        time.sleep(3)
    except Exception as exc:
        LOGGER.warning("Không chọn được siêu thị (css-ot6l9u): %s", exc)

    LOGGER.info("Done handling location popup.")


def main():
    LOGGER.info("=== TEST COOP POPUP ===")
    driver = build_driver(headless=False)

    try:
        LOGGER.info("Opening URL: %s", URL)
        driver.get(URL)

        # cho popup hiện
        time.sleep(5)

        handle_location_popup(driver, timeout=40)

        LOGGER.info("Popup handled. Sleep 10s to observe page...")
        time.sleep(10)

    finally:
        driver.quit()
        LOGGER.info("Driver quit. Test done.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    main()
