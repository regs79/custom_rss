from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper


def _https(url: str) -> str:
    return "https://" + url[7:] if url.startswith("http://") else url


def _stars_to_fraction(stars_div: Tag) -> str:
    """Convert a div.stars element to 'X/5' string."""
    count = 0.0
    for el in stars_div.find_all("i", class_="rating-star"):
        classes = set(el.get("class", []))
        if "fa-star-half-stroke" in classes:
            count += 0.5
        elif "fa-solid" in classes:
            count += 1.0
    formatted = int(count) if count == int(count) else count
    return f"{formatted}/5"


def _parse_review_date(text: str) -> datetime | None:
    match = re.search(r"(\w+\s+\d+(?:st|nd|rd|th)?,\s*\d{4})", text)
    if not match:
        return None
    clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", match.group(1))
    try:
        return datetime.strptime(clean, "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class HighDefDigestScraper(BaseScraper):
    feed_title = "High Def Digest - 4K UHD Reviews"
    feed_description = "The most comprehensive reviews of 4K UHD discs online."

    def get_items(self, soup: BeautifulSoup) -> list[dict]:
        seen = set()
        items = []
        for card in soup.select("ul.review-card-container li span.review-card a.flex-column"):
            url = card.get("href", "")
            if not url or url in seen:
                continue
            seen.add(url)

            title_el = card.select_one("span.review-title")
            img_el = card.select_one("img")
            items.append({
                "url": url,
                "title": title_el.get_text(strip=True) if title_el else "",
                "image": _https(img_el["src"]) if img_el and img_el.get("src") else "",
            })
        return items

    def get_item_detail(self, url: str, item: dict) -> dict | None:
        soup = self.fetch(url)

        # The page has two div.review-detail: the first (.row) is a minimal header
        # widget; the second (no .row class) contains the full review content.
        review_div = soup.select_one("div.review-detail:not(.row)")
        if not review_div:
            # Not yet reviewed — just a release details page
            return None

        title_el = review_div.select_one("h1.review-title")
        title = title_el.get_text(strip=True) if title_el else item.get("title", "")

        date_el = review_div.select_one("span.review-date")
        date = _parse_review_date(date_el.get_text()) if date_el else None

        author_el = review_div.select_one("a.username")
        author = author_el.get_text(strip=True) if author_el else None

        # Summary: first non-empty sibling after the "Overview -" span
        summary = ""
        overview_span = review_div.select_one("span.overview-text")
        if overview_span:
            for sib in overview_span.next_siblings:
                if hasattr(sib, "get_text"):
                    text = sib.get_text(strip=True)
                    if text:
                        summary = text
                        break

        content = self._build_content(review_div, item.get("image", ""))

        return {
            "title": title,
            "date": date,
            "author": author,
            "summary": summary,
            "content": content,
        }

    def _build_content(self, review_div: Tag, listing_image: str) -> str:
        parts: list[str] = ["<div>"]

        # Cover image: prefer the larger one from the first story section
        cover_img = review_div.select_one("div.story-line-section div.image-section img")
        cover_src = _https(cover_img["src"]) if cover_img and cover_img.get("src") else listing_image
        if cover_src:
            parts.append(f'<p><img src="{cover_src}" alt="Cover" /></p>')

        # Overall ratings card
        overall_card = review_div.select_one("div.overall-card")
        if overall_card:
            overall_stars = overall_card.select_one("div.overall-stars div.stars")
            if overall_stars:
                parts.append(f"<p><strong>Overall: {_stars_to_fraction(overall_stars)}</strong></p>")

            breakdown = overall_card.select("div.overall-section")
            if breakdown:
                rows = []
                for section in breakdown:
                    label_el = section.find("span")
                    stars_div = section.select_one("div.stars")
                    if label_el and stars_div:
                        label = label_el.get_text(strip=True).title()
                        rows.append(f"<tr><td><strong>{label}</strong></td><td>{_stars_to_fraction(stars_div)}</td></tr>")
                if rows:
                    parts.append("<table>" + "".join(rows) + "</table>")

        # Tech specs
        tech = review_div.select_one("div.tech-details-card")
        if tech:
            parts.append("<h3>Tech Specs</h3>")
            for spec in tech.select("div.spec"):
                spans = spec.find_all("span")
                if len(spans) >= 2:
                    label = spans[0].get_text(strip=True)
                    value = spans[1].get_text(strip=True)
                    if label and value:
                        parts.append(f"<p><strong>{label}</strong> {value}</p>")

        parts.append("<hr />")

        # Review sections (Storyline, Video, Audio, Special Features)
        for section in review_div.select("div.story-line-section"):
            h3 = section.find("h3")
            if h3:
                parts.append(f"<h3>{h3.get_text(strip=True)}</h3>")

            ranking_stars = section.select_one("div.ranking-section div.stars")
            if ranking_stars:
                parts.append(f"<p><em>Ranking: {_stars_to_fraction(ranking_stars)}</em></p>")

            review_text = section.select_one("div.review-movie")
            if review_text:
                parts.append(str(review_text))

        parts.append("<hr />")

        parts.append("</div>")
        return "\n".join(parts)
