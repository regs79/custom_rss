#!/usr/bin/env python3
"""Serve RSS feeds over HTTP so FreshRSS can subscribe to them.

Usage:
    python serve.py             # runs on port 8000
    python serve.py --port 9000
"""

import argparse

import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response

from adapters.highdefdigest import HighDefDigestScraper

app = FastAPI()

FEEDS = {
    "hdd-uhd": (
        HighDefDigestScraper,
        "https://ultrahd.highdefdigest.com/reviews.html",
    ),
}


def _make_handler(cls, url):
    def handler():
        scraper = cls(url=url)
        xml = scraper.build_feed()
        return Response(content=xml, media_type="application/atom+xml")
    return handler


for slug, (cls, url) in FEEDS.items():
    app.get(f"/{slug}")(_make_handler(cls, url))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
