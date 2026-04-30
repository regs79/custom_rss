from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

CACHE_DIR = Path(__file__).parent.parent / "cache"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; custom-rss/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


class BaseScraper:
    feed_title = "RSS Feed"
    feed_description = ""
    feed_language = "en"

    def __init__(self, url: str, cache_pages: bool = True):
        self.url = url
        self.cache_pages = cache_pages
        CACHE_DIR.mkdir(exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        key = hashlib.md5(url.encode()).hexdigest()
        return CACHE_DIR / f"{key}.html"

    def fetch(self, url: str, cache: bool | None = None) -> BeautifulSoup:
        use_cache = self.cache_pages if cache is None else cache
        if use_cache:
            path = self._cache_path(url)
            if path.exists():
                return BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

        resp = httpx.get(url, follow_redirects=True, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        if use_cache:
            self._cache_path(url).write_text(resp.text, encoding="utf-8")

        return BeautifulSoup(resp.text, "lxml")

    def get_items(self, soup: BeautifulSoup) -> list[dict]:
        """Return list of dicts with at minimum: url, title."""
        raise NotImplementedError

    def get_item_detail(self, url: str, item: dict) -> dict | None:
        """Parse a detail page. Return None to skip this item."""
        raise NotImplementedError

    def build_feed(self, output: str | None = None, limit: int | None = None) -> str:
        # Listing page is never cached so new reviews appear immediately
        soup = self.fetch(self.url, cache=False)
        items = self.get_items(soup)

        if limit:
            items = items[:limit]

        fg = FeedGenerator()
        fg.id(self.url)
        fg.title(self.feed_title)
        fg.subtitle(self.feed_description or self.feed_title)
        fg.link(href=self.url, rel="alternate")
        fg.language(self.feed_language)
        fg.author({"name": self.feed_title})

        for item in items:
            detail = self.get_item_detail(item["url"], item)
            if detail is None:
                continue

            fe = fg.add_entry()
            fe.id(item["url"])
            fe.title(detail.get("title") or item.get("title") or "Untitled")
            fe.link(href=item["url"])

            if detail.get("date"):
                fe.published(detail["date"])
                fe.updated(detail["date"])

            if detail.get("author"):
                fe.author({"name": detail["author"]})

            if detail.get("content"):
                fe.content(detail["content"], type="html")

            if detail.get("summary"):
                fe.summary(detail["summary"])

        xml = fg.atom_str(pretty=True).decode()
        if output:
            Path(output).write_text(xml, encoding="utf-8")
            print(f"Written to {output}")
        return xml
