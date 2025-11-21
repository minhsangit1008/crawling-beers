import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# ===============================
# CẤU HÌNH CƠ BẢN
# ===============================
HAR_FILE = "www.bachhoaxanh.com.har"   # Đổi lại nếu file HAR của bạn tên khác
OUTPUT_FILE = "bhx_bia_api.txt"        # File txt xuất ra
CATEGORY_ID_BIA = 2282                 # CategoryId của Bia trên BHX
KEYWORD_URL = "Category/AjaxProduct"   # Endpoint chính dùng để load sản phẩm


# ===============================
# HÀM HỖ TRỢ
# ===============================
def load_har(path: str) -> Dict[str, Any]:
    """Đọc file HAR (JSON) và trả về dict."""
    har_path = Path(path)
    if not har_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file HAR: {har_path.resolve()}")
    with har_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Thử parse JSON, lỗi thì trả về None."""
    try:
        return json.loads(text)
    except Exception:
        return None


def is_beer_request(entry: Dict[str, Any]) -> bool:
    """
    Xác định đây có phải là request API Bia hay không:
    - URL chứa 'Category/AjaxProduct'
    - payload (postData) có CategoryId = 2282
    """
    req = entry.get("request", {})
    url = req.get("url", "")
    if KEYWORD_URL not in url:
        return False

    post_data = req.get("postData", {})
    text = post_data.get("text", "")
    if not text:
        return False

    # Thử parse JSON
    data_json = try_parse_json(text)
    if isinstance(data_json, dict):
        if data_json.get("CategoryId") == CATEGORY_ID_BIA:
            return True

    # Trường hợp payload không phải JSON thuần (form-data, urlencoded),
    # fallback check chuỗi thô
    if '"CategoryId":2282' in text or "CategoryId=2282" in text:
        return True

    return False


def extract_beer_entries(har: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Lọc ra tất cả entries liên quan tới API Bia."""
    entries = har.get("log", {}).get("entries", [])
    beer_entries = [e for e in entries if is_beer_request(e)]
    return beer_entries


def normalize_headers(headers: List[Dict[str, str]]) -> Dict[str, str]:
    """Convert list [{'name': 'X', 'value': 'Y'}] -> dict {name: value}."""
    result = {}
    for h in headers:
        name = h.get("name")
        value = h.get("value")
        if name is not None and value is not None:
            result[name] = value
    return result


def build_export_object(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Tạo ra 1 object gọn gàng chứa đầy đủ thông tin cần export."""
    req = entry.get("request", {})
    res = entry.get("response", {})

    request_headers = normalize_headers(req.get("headers", []))
    response_headers = normalize_headers(res.get("headers", []))

    post_data = req.get("postData", {})
    request_body_text = post_data.get("text")

    response_content = res.get("content", {})
    response_body_text = response_content.get("text")

    export_obj = {
        "url": req.get("url"),
        "method": req.get("method"),
        "request_headers": request_headers,
        "request_body": request_body_text,
        "response_status": res.get("status"),
        "response_status_text": res.get("statusText"),
        "response_headers": response_headers,
        "response_body": response_body_text,
    }
    return export_obj


def save_to_txt(beer_entries: List[Dict[str, Any]], output_path: str) -> None:
    """Ghi toàn bộ thông tin API bia ra file txt (mỗi request là một block JSON)."""
    out_path = Path(output_path)
    with out_path.open("w", encoding="utf-8") as f:
        for idx, entry in enumerate(beer_entries, start=1):
            export_obj = build_export_object(entry)
            f.write(f"===== BIA REQUEST #{idx} =====\n")
            f.write(json.dumps(export_obj, ensure_ascii=False, indent=2))
            f.write("\n\n----------------------------------------\n\n")
    print(f"Đã ghi {len(beer_entries)} request bia vào file: {out_path.resolve()}")


# ===============================
# MAIN
# ===============================
def main():
    print(f"Đang đọc file HAR: {HAR_FILE} ...")
    har = load_har(HAR_FILE)

    print("Đang tìm các request API Bia trong HAR...")
    beer_entries = extract_beer_entries(har)

    print(f"Tìm được {len(beer_entries)} request liên quan đến CategoryId={CATEGORY_ID_BIA}")
    if not beer_entries:
        print("⚠ Không tìm được request nào cho Bia. Kiểm tra lại CATEGORY_ID_BIA hoặc HAR.")
        return

    print(f"Đang export ra file TXT: {OUTPUT_FILE} ...")
    save_to_txt(beer_entries, OUTPUT_FILE)


if __name__ == "__main__":
    main()
