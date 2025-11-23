# test.py – PHIÊN BẢN HOÀN CHỈNH & CHẠY NGON
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
LOGGER = logging.getLogger(__name__)

def handle_address_popup(driver):
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")))
        LOGGER.info("Popup 1: Chọn địa chỉ")

        driver.find_element(By.ID, "provinceCode").click()
        time.sleep(0.8)
        driver.find_element(By.XPATH, "//div[text()='Thành phố Hồ Chí Minh']").click()
        time.sleep(1)

        driver.find_element(By.ID, "districtCode").click()
        time.sleep(0.8)
        driver.find_element(By.XPATH, "//div[text()='Huyện Bình Chánh']").click()
        time.sleep(1)

        driver.find_element(By.ID, "wardCode").click()
        time.sleep(0.8)
        driver.find_element(By.XPATH, "//div[text()='Xã Bình Hưng']").click()
        time.sleep(0.5)

        driver.find_element(By.ID, "address").send_keys("1")
        driver.find_element(By.XPATH, "//button[contains(.,'Xác nhận')]").click()
        LOGGER.info("Đã xác nhận địa chỉ")
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")))
    except TimeoutException:
        LOGGER.info("Không có Popup 1 (đã lưu địa chỉ)")

def handle_supermarket_popup(driver):
    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")))
        LOGGER.info("Popup 2: Chọn siêu thị")

        # === GIỮ NGUYÊN CÁCH BẠN ĐÃ CHỌN THÀNH CÔNG ===
        first_store = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div.css-ot6l9u"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_store)
        time.sleep(0.5)
        first_store.click()
        LOGGER.info("Đã chọn siêu thị đầu tiên (Co.opXtra Tạ Quang Bửu)")

        # === CHỈ SỬA PHẦN NÀY: Click đúng nút "Mua sắm ngay" mới ===
        buy_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.css-18uoi51"))
            # hoặc: (By.XPATH, "//button[contains(@class,'css-18uoi51') and .//div[contains(text(),'Mua sắm ngay')]]")
        )
        driver.execute_script("arguments[0].click();", buy_button)   # Force click cho chắc
        LOGGER.info("ĐÃ CLICK THÀNH CÔNG 'Mua sắm ngay' (class css-18uoi51)")

        # Đợi popup đóng
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.teko-modal.teko-modal-show")))
        LOGGER.info("Popup 2 đã đóng – HOÀN TẤT!")

    except TimeoutException:
        LOGGER.info("Không có Popup 2 (đã chọn siêu thị trước đó)")

def main():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://cooponline.vn/c/bia")
        LOGGER.info("Mở trang Co.op Online - Bia")
        time.sleep(4)

        handle_address_popup(driver)
        handle_supermarket_popup(driver)

        LOGGER.info("HOÀN TẤT! Giữ cửa sổ 10 giây để bạn thấy danh sách bia...")
        time.sleep(10)

    finally:
        driver.quit()
        LOGGER.info("Đã đóng trình duyệt")

if __name__ == "__main__":
    main()