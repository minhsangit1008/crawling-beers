# crawling-beers

Crawler utilities for beer products.

## Modules
- `bhx_crawler.py`: crawler for BachHoaXanh with `crawl_bhx()` returning normalized dictionaries.
- `helpers.py`: shared parsing helpers (capacity, unit, packing, brand, promotion, product key).

## Quick start
```python
from bhx_crawler import crawl_bhx
import csv

records = crawl_bhx(headless=True)
with open("bhx_beer_products_full.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)
```
