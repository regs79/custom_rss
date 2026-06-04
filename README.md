# custom_rss

Creates RSS feeds from websites that don't have one, stripping articles to just the content.

## Feeds

| Slug | Source | Description |
|------|--------|-------------|
| `/hdd-uhd` | High Def Digest | 4K UHD Blu-ray reviews |
| `/pcgamer-news` | PC Gamer | Latest news articles |

## Usage

```bash
python serve.py                    # runs on port 8000
python serve.py --port 9000        # custom port
```

Or with Docker:

```bash
docker compose up --build
# feeds available at http://localhost:9000/
```

## Adding a new adapter

1. Create `adapters/<name>.py` subclassing `BaseScraper`
2. Implement `get_items(soup)` and `get_item_detail(url, item)`
3. Register in `FEEDS` in `serve.py`
