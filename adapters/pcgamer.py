from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from .base import BaseScraper, HEADERS

FEED_URL = "https://www.pcgamer.com/feeds/articletype/news/"


def _parse_iso_date(text: str) -> datetime | None:
    """Parse an ISO 8601 date string."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class PcgamerScraper(BaseScraper):
    feed_title = "PC Gamer - News"
    feed_description = "All the latest news from the PC Gamer team"

    def _fetch_feed_xml(self) -> BeautifulSoup:
        """Fetch the RSS feed XML."""
        resp = httpx.get(self.url, follow_redirects=True, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "xml")

    @staticmethod
    def _get_link_text(item) -> str:
        """Extract link from PC Gamer's quirky RSS feed.

        The feed has <link/> with the URL as sibling text content
        rather than inside the tag: <link/>https://..."
        """
        link_el = item.find("link")
        if link_el:
            # Try text inside the tag first
            text = link_el.get_text(strip=True)
            if text and text.startswith("http"):
                return text
            # Try sibling text content
            next_el = link_el.find_next_sibling(string=True)
            if next_el and next_el.strip().startswith("http"):
                return next_el.strip()
        return ""

    def get_items(self, soup: BeautifulSoup) -> list[dict]:
        """Parse RSS feed XML and return article list."""
        items = []
        seen = set()
        for item in soup.find_all("item"):
            link = self._get_link_text(item)
            title_el = item.find("title")
            date_el = item.find("pubdate") or item.find("pubDate")
            author_el = item.find("dc:creator")
            enclosure_el = item.find("enclosure")

            if not link or link in seen:
                continue
            seen.add(link)

            items.append({
                "url": link,
                "title": title_el.get_text(strip=True) if title_el else "",
                "date_str": date_el.get_text(strip=True) if date_el else None,
                "author": author_el.get_text(strip=True) if author_el else None,
                "image": enclosure_el.get("url") if enclosure_el else "",
            })
        return items

    def get_item_detail(self, url: str, item: dict) -> dict | None:
        """Fetch an article page and extract the full content."""
        resp = httpx.get(url, follow_redirects=True, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract article body from div.text-copy.bodyCopy
        body = soup.find("body")
        if not body:
            return None

        content_div = body.find("div", class_="text-copy")
        if not content_div:
            return None

        # Collect elements to decompose (share links, ads, nav, recirculation)
        to_decompose: list[Tag] = []
        noise_classes = [
            "copy-link", "social", "share", "slice-container",
            "newsletter", "ad-unit", "instagram-embed",
            "popular", "widget-area", "author-bio",
            "author__", "widget-contentparsed-sidebar",
            "widget-hero", "widget-dynamic", "popularBox",
            "font-ui-heading",
            "hawk-root", "recirculation",
            "article-river", "articleRiver",
            "kwizly-quiz", "kwizly",
            "vanilla-image-figure", "image-full-width-wrapper",
        ]
        noise_text = ["You may like", "Latest Videos", "Watch full video"]

        for tag_name in ["p", "img", "blockquote", "h2", "h3", "h4", "ul", "ol", "li", "a", "em", "strong", "span", "div", "aside"]:
            for el in content_div.find_all(tag_name):
                if el is None:
                    continue
                classes = el.get("class") or []
                cls_str = " ".join(classes).lower()
                text = el.get_text(strip=True)
                if any(k in cls_str for k in noise_classes):
                    to_decompose.append(el)
                elif any(x in text for x in noise_text):
                    to_decompose.append(el)

        for el in to_decompose:
            el.decompose()

        # Decompose script tags entirely
        for script in content_div.find_all("script"):
            script.decompose()

        # Strip tracking data from remaining elements
        _DATA_ATTRS = (
            "id", "data-analytics-id", "data-before-rewrite-localise",
            "data-hl-processed", "data-mrf-recirculation", "data-url",
            "data-component-name", "data-recirculation-type",
            "data-nosnippet", "data-block-type", "data-render-type",
            "data-skip", "data-widget-type",
            "data-google-interstitial", "data-merchant-id",
            "data-merchant-name", "data-merchant-network",
            "data-merchant-url", "data-original-mos",
            "data-pin-media", "data-new-v2-image",
            "data-placeholder-url", "data-bordeaux-image-check",
        )
        for el in content_div.find_all(True):
            if isinstance(el, Tag):
                for attr in _DATA_ATTRS:
                    el.attrs.pop(attr, None)

        # Remove empty anchor tags
        for anchor in content_div.find_all("a"):
            if not anchor.get("href") and not anchor.get_text(strip=True):
                anchor.decompose()

        content_html = str(content_div)

        # Extract author from JSON-LD structured data
        author = item.get("author")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                    article_author = data.get("author", {})
                    if isinstance(article_author, dict) and article_author.get("name"):
                        author = article_author["name"]
                        break
                    elif isinstance(article_author, list):
                        for a in article_author:
                            if isinstance(a, dict) and a.get("name"):
                                author = a["name"]
                                break
                        else:
                            continue
                        break
            except (json.JSONDecodeError, AttributeError):
                continue

        # Extract date from JSON-LD
        date = _parse_iso_date(item.get("date_str"))
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                    pub_date = _parse_iso_date(data.get("datePublished"))
                    if pub_date and not date:
                        date = pub_date
                    break
            except (json.JSONDecodeError, AttributeError):
                continue

        # Extract hero image from page
        hero_img = soup.find("img", class_="hero-image")
        image_url = hero_img.get("src", "") if hero_img else ""

        # Fallback: extract image from meta tags if not in RSS or no hero image
        if not image_url:
            image_url = item.get("image", "")
            if not image_url:
                for meta in soup.find_all("meta"):
                    if meta.get("property") == "og:image":
                        image_url = meta.get("content", "")
                        break

        return {
            "title": item.get("title", "") or self._extract_title(soup),
            "date": date,
            "author": author,
            "content": content_html,
            "image": image_url,
        }

    def build_feed(self, output: str | None = None, limit: int | None = None) -> str:
        """Override to fetch the RSS feed XML instead of an HTML page."""
        soup = self._fetch_feed_xml()
        items = self.get_items(soup)

        if limit:
            items = items[:limit]

        from feedgen.feed import FeedGenerator

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

            if detail.get("image"):
                fe.link(href=detail["image"], rel="enclosure")

        xml = fg.atom_str(pretty=True).decode()

        # feedgen strips custom rel attributes; restore enclosure rel for CDN image links
        xml = re.sub(
            r'(<link href="(https://cdn\.mos\.cms\.futurecdn\.net/[^\"]+)"/?>)',
            r'<link rel="enclosure" href="\2"/>',
            xml,
        )
        if output:
            Path(output).write_text(xml, encoding="utf-8")
            print(f"Written to {output}")
        return xml

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Fallback title extraction from page meta/structured data."""
        # Try JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                    return data.get("name", data.get("headline", ""))
            except (json.JSONDecodeError, AttributeError):
                continue

        # Try meta tags
        for meta in soup.find_all("meta"):
            prop = meta.get("property") or meta.get("name", "")
            if prop in ("og:title", "twitter:title"):
                return meta.get("content", "")

        # Fallback: title tag
        title_tag = soup.find("title")
        if title_tag:
            text = title_tag.get_text(strip=True)
            # Strip site name suffix
            text = re.sub(r"\s*[|-]\s*PC\s*Gamer\s*$", "", text)
            return text

        return "Untitled"
