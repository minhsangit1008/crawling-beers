"""
Crawl sản phẩm Bia từ Bách Hóa Xanh bằng API Category/AjaxProduct.

- CategoryId = 2282 (bia)
- Gọi API phân trang (PageIndex)
- Lưu kết quả ra CSV: bhx_beer_products.csv
"""

import csv
import math
import time
import logging
from typing import Any, Dict, List

import requests

# =========================
# CẤU HÌNH CƠ BẢN
# =========================
API_URL = "https://apibhx.tgdd.vn/Category/AjaxProduct"

# Header giả lập browser thật
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "vi,en-US;q=0.9,en;q=0.8",
    "customer-id": "",
    "deviceid": "2d9125a1-b026-41ef-a19b-a9b2e08294b6",
    "origin": "https://www.bachhoaxanh.com",
    "platform": "webnew",
    "priority": "u=1, i",
    "referer": "https://www.bachhoaxanh.com/bia",
    "referer-url": "https://www.bachhoaxanh.com/bia",
    "reversehost": "http://bhxapi.live",
    "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
    "xapikey": "bhx-api-core-2022",
    "content-type": "application/json;charset=UTF-8",
    # thêm cái này cho chắc, dù request gốc không có cũng không sao:
    "x-requested-with": "XMLHttpRequest",
}


# Payload gốc cho category Bia (CategoryId = 2282)
# provinceId / storeId lấy từ HAR, bạn có thể thay bằng location khác nếu muốn
BASE_PAYLOAD: Dict[str, Any] = {
    "provinceId": 1027,        # ID tỉnh (ví dụ Hồ Chí Minh / Hà Nội tuỳ HAR của bạn)
    "wardId": 0,
    "districtId": 0,
    "storeId": 2546,           # ID cửa hàng
    "CategoryId": 2282,        # BIA
    "SelectedBrandId": "",
    "PropertyIdList": "",
    "PageIndex": 1,
    "PageSize": 10,            # số sản phẩm / trang (HAR của bạn đang là 10)
    "SortStr": "",
    "PriorityProductIds": "",  # có thể để rỗng, không bắt buộc
    "PropertySelected": [],
    "LastShowProductId": 0,
}

OUTPUT_CSV = "bhx_beer_products.csv"

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# =========================
# HÀM GỌI API
# =========================
def fetch_page(page_index: int) -> Dict[str, Any]:
    """
    Gọi API cho 1 trang (PageIndex) và trả về JSON.
    """
    payload = BASE_PAYLOAD.copy()
    payload["PageIndex"] = page_index
    # Giữ LastShowProductId = 0 cho đơn giản, API vẫn trả dữ liệu bình thường

    logging.info(f"Gọi API page={page_index} ...")
    resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=20)
    print(resp.status_code, resp.text[:500])
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"API trả code != 0: {data}")

    return data


def extract_products(json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Lấy danh sách products từ JSON trả về của API.
    """
    return json_data.get("data", {}).get("products", [])


# =========================
# MAIN CRAWL
# =========================
def main() -> None:
    logging.info("=== BẮT ĐẦU CRAWL BIA BÁCH HÓA XANH ===")

    # 1. Gọi page 1 để lấy tổng số sản phẩm và 1 phần dữ liệu
    first_json = fetch_page(1)
    total = first_json.get("data", {}).get("total", 0)
    page_size = BASE_PAYLOAD["PageSize"]

    if total == 0:
        logging.error("API trả total = 0, kiểm tra lại payload / CategoryId / location.")
        return

    total_pages = math.ceil(total / page_size)
    logging.info(f"Tổng số sản phẩm: {total} | PageSize: {page_size} | Số trang: {total_pages}")

    all_products: List[Dict[str, Any]] = []
    all_products.extend(extract_products(first_json))

    # 2. Loop các trang tiếp theo
    for page in range(2, total_pages + 1):
        try:
            json_page = fetch_page(page)
            prods = extract_products(json_page)
            all_products.extend(prods)
            logging.info(f"Page {page}/{total_pages} | Lấy được {len(prods)} sản phẩm.")
            time.sleep(0.4)  # nghỉ nhẹ tránh spam
        except Exception as e:
            logging.error(f"Lỗi khi crawl page {page}: {e}")
            # tuỳ bạn, có thể break hoặc continue
            continue

    logging.info(f"Tổng số sản phẩm thu được: {len(all_products)}")

    # 3. Ghi ra CSV
    if not all_products:
        logging.error("Không có sản phẩm nào để ghi ra CSV.")
        return

    fields = [
        "id",
        "name",
        "fullName",
        "url",
        "avatar",
        "unit",
        "price",
        "sysPrice",
        "discountPercent",
        "promotionText",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(fields)

        for p in all_products:
            # productPrices có thể rỗng, nên cần check
            price = None
            sys_price = None
            discount_percent = None
            prices = p.get("productPrices") or []
            if prices:
                first_price = prices[0]
                price = first_price.get("price")
                sys_price = first_price.get("sysPrice")
                discount_percent = first_price.get("discountPercent")

            row = [
                p.get("id"),
                p.get("name"),
                p.get("fullName"),
                p.get("url"),
                p.get("avatar"),
                p.get("unit"),
                price,
                sys_price,
                discount_percent,
                p.get("promotionText"),
            ]
            writer.writerow(row)

    logging.info(f"ĐÃ GHI CSV THÀNH CÔNG → {OUTPUT_CSV}")
    logging.info("=== HOÀN TẤT CRAWL BIA BHX ===")


if __name__ == "__main__":
    main()
