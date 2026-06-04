# custom_rss — Developer Notes

## Architecture

- `serve.py` — FastAPI app. Register feeds in the `FEEDS` dict:
  ```python
  FEEDS = {
      "slug": (ScraperClass, url),
  }
  ```
- `adapters/base.py` — `BaseScraper` class:
  - `get_items(soup)` → `list[dict]` with at least `url`, `title`
  - `get_item_detail(url, item)` → `dict` with optional: `title`, `date`, `author`, `content`, `summary`
  - `build_feed()` → Atom XML string
- `adapters/pcgamer.py` — Uses `build_feed()` override (fetches RSS XML, not HTML)
- `adapters/highdefdigest.py` — Uses standard `get_items`/`get_item_detail` pattern

## Adding an adapter

1. Create `adapters/<name>.py`
2. Import `HEADERS` from `base` and subclass `BaseScraper`
3. Set `feed_title`, `feed_description`
4. Implement `get_items(soup)` and `get_item_detail(url, item)`
5. Register in `FEEDS` in `serve.py`

## Site-specific quirks discovered

### PC Gamer (pcgamer.com)
- **RSS feed URL**: `https://www.pcgamer.com/feeds/articletype/news/`
- **RSS link format**: `<link/>` followed by sibling text content (not inside the tag)
- **Article body selector**: `div.text-copy` (or `div.text-copy.bodyCopy`)
- **Article body class list** (decompose these):
  `copy-link`, `social`, `share`, `slice-container`, `newsletter`, `ad-unit`,
  `instagram-embed`, `popular`, `widget-area`, `author-bio`, `author__`,
  `widget-contentparsed-sidebar`, `widget-hero`, `widget-dynamic`, `popularBox`,
  `font-ui-heading`, `hawk-root`, `recirculation`, `article-river`, `articleRiver`,
  `kwizly-quiz`, `kwizly`, `vanilla-image-figure`, `image-full-width-wrapper`
- **Text content to check for** (decompose matching divs): `"You may like"`, `"Latest Videos"`, `"Watch full video"`
- **Script tags**: decompose entirely
- **Tracking attrs to strip**: `id` (Elk IDs), `data-analytics-id`, `data-before-rewrite-localise`, `data-hl-processed`, `data-mrf-recirculation`, `data-url`, `data-component-name`, `data-recirculation-type`, `data-nosnippet`, `data-block-type`, `data-render-type`, `data-skip`, `data-widget-type`, `data-google-interstitial`, `data-merchant-*`, `data-original-mos`, `data-pin-media`, `data-new-v2-image`, `data-placeholder-url`, `data-bordeaux-image-check`
- **Author**: extract from JSON-LD `application/ld+json` with `@type: NewsArticle`
- **Date**: parse from `pubDate` in RSS, fallback to JSON-LD `datePublished`
- **Title fallback**: JSON-LD → meta `og:title` → `<title>` tag (strip ` PC Gamer` suffix)

### High Def Digest (highdefdigest.com)
- **Listing page**: HTML, use BeautifulSoup lxml parser
- **Article body**: `div.review-detail:not(.row)` (not the minimal header variant)
- **Date parsing**: custom regex for "Month day, Year" format
- **Ratings**: Font Awesome icons, parse class names (`fa-solid`, `fa-star-half-stroke`)

## Atom feed — enclosure links

- feedgen strips custom `rel` attributes from `<link>` elements
- To add `<link rel="enclosure" href="..."/>` in Atom, add a plain link then post-process:
  ```python
  if detail.get("image"):
      fe.link(href=detail["image"], rel="enclosure")  # rel stripped by feedgen
  
  xml = fg.atom_str(pretty=True).decode()
  xml = re.sub(
      r'(<link href="(https://cdn\.mos\.cms\.futurecdn\.net/[^\"]+)"/?>)',
      r'<link rel="enclosure" href="\2"/>',
      xml,
  )
  ```
- Use `BeautifulSoup(resp.text, "lxml")` for HTML, `BeautifulSoup(resp.text, "xml")` for RSS

## Testing

```bash
python3 -c "
from adapters.<name> import <Name>Scraper
scraper = <Name>Scraper(url='...', cache_pages=False)
xml = scraper.build_feed(limit=2)
print(xml[:3000])
print(f'Entries: {xml.count(chr(60)+\"entry\")}')
"
```

Or run the server and hit the endpoint:
```bash
python serve.py --port 8001
curl http://localhost:8001/<slug>
```
