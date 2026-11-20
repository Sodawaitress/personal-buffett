"""feedparser.parse(url) 自己发 HTTP、没有超时；这里先用 requests 带超时取回，再交给 feedparser。"""

import feedparser
import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PersonalBuffett/1.0; +https://personal-buffett.fly.dev)"}


def parse_feed(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout, headers=_HEADERS)
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠️ feed {url[:60]}: {e}")
        return feedparser.FeedParserDict(entries=[])
    return feedparser.parse(r.content)
