#!/usr/bin/env python3
"""Generate an RSS feed from a scraper adapter.

Usage:
    python main.py --output feed.xml
    python main.py --output feed.xml --limit 10 --no-cache
"""

import argparse
from adapters.highdefdigest import HighDefDigestScraper

SCRAPERS = {
    "highdefdigest-uhd": (
        HighDefDigestScraper,
        "https://ultrahd.highdefdigest.com/reviews.html",
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RSS feed from web scraper")
    parser.add_argument(
        "--scraper",
        default="highdefdigest-uhd",
        choices=list(SCRAPERS),
        help="Which scraper to use (default: highdefdigest-uhd)",
    )
    parser.add_argument("--output", default="feed.xml", help="Output file path")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of items to include (default: all from first page)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching of detail pages (re-fetches everything)",
    )
    args = parser.parse_args()

    cls, url = SCRAPERS[args.scraper]
    scraper = cls(url=url, cache_pages=not args.no_cache)

    print(f"Building feed: {args.scraper}")
    scraper.build_feed(output=args.output, limit=args.limit)


if __name__ == "__main__":
    main()
