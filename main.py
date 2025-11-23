"""
Main entry point for running beer crawlers and exporting unified price data.

Included sources:
    - BachHoaXanh (bhx)
    - Mega Market (mega)
    - Lotte Mart (lotte)
    - Kingfood Mart (kingfood)
    - Co.op Online (coop)

Usage examples:
    # Crawl all sources, show Chrome window
    python main.py --sources all

    # Only crawl BHX + Co.op, headless
    python main.py --sources bhx coop --headless

    # Crawl Mega + Lotte, write to a custom file
    python main.py --sources mega lotte --output mega_lotte.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime
from typing import Any, Dict, List

from bhx_crawler import crawl_bhx
from mega_crawler import crawl_mega
from lotte_crawler import crawl_lotte
from kingfood_crawler import crawl_kingfood
from coop_crawler import crawl_coop

LOGGER = logging.getLogger(__name__)

# Unified CSV schema (must be consistent across all crawlers)
FIELDNAMES = [
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


def write_products_to_csv(
    products: List[Dict[str, Any]],
    output_path: str,
) -> None:
    """
    Write a list of product dictionaries to a CSV file.

    The CSV schema is defined by FIELDNAMES. Missing keys in each product
    dictionary are safely filled with an empty string.

    Parameters
    ----------
    products:
        List of product records, each represented as a dictionary.
    output_path:
        Path to the CSV file to be created or overwritten.
    """
    with open(output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()

        for item in products:
            # Ensure missing keys do not break the writer
            row = {field: item.get(field, "") for field in FIELDNAMES}
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the beer crawling pipeline.

    Returns
    -------
    argparse.Namespace
        Parsed arguments including sources, headless flag, and output path.
    """
    parser = argparse.ArgumentParser(
        description="Multi-source beer crawling CLI tool.",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["all"],
        help=(
            "List of sources to crawl. "
            "Allowed values: bhx, mega, lotte, kingfood, coop, all."
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browsers in headless mode.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output CSV path. "
            "Default: output/all_beer_prices_YYYYMMDD.csv"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """
    Run the multi-source beer crawling pipeline.

    Steps:
        1. Parse CLI arguments.
        2. Initialize logging.
        3. Resolve list of sources to crawl.
        4. Execute each crawler and aggregate products.
        5. Export combined results to a unified CSV file.
    """
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    LOGGER.info(
        "=== Starting multi-source beer crawling pipeline ===",
    )

    # Normalize and resolve sources
    srcs = [src.lower() for src in args.sources]
    if "all" in srcs:
        srcs = ["bhx", "mega", "lotte", "kingfood", "coop"]

    # Map source name -> crawler function
    crawler_map = {
        "bhx": crawl_bhx,
        "mega": crawl_mega,
        "lotte": crawl_lotte,
        "kingfood": crawl_kingfood,
        "coop": crawl_coop,
    }

    all_products: List[Dict[str, Any]] = []

    for src in srcs:
        func = crawler_map.get(src)
        if func is None:
            LOGGER.warning("Unknown source '%s'. Skipping.", src)
            continue

        LOGGER.info("Running crawler for source: %s", src)
        products = func(headless=args.headless)
        LOGGER.info("Source %s: %d products collected.", src, len(products))
        all_products.extend(products)

    LOGGER.info("Total combined products: %d", len(all_products))

    # Default output file path
    if not args.output:
        today = datetime.now().strftime("%Y%m%d")
        args.output = f"output/all_beer_prices_{today}.csv"

    write_products_to_csv(all_products, args.output)
    LOGGER.info("Exported combined CSV to: %s", args.output)

    LOGGER.info("=== Crawling pipeline completed successfully ===")


if __name__ == "__main__":
    main()