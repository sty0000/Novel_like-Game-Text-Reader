from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_API = "https://prts.wiki/api.php"
DEFAULT_EDIT_URL = "https://prts.wiki/index.php?title={title}&action=edit"


class CrawlError(RuntimeError):
    pass


class _FetchTransportError(CrawlError):
    pass


__all__ = ["CrawlError", "fetch_story_text", "main"]


def quote_title(title: str) -> str:
    return quote(title.replace(" ", "_"), safe="/_-%()[]{}:.,")


def build_edit_url(title: str) -> str:
    return DEFAULT_EDIT_URL.format(title=quote_title(title))


def normalize_title_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    title = query.get("title", [None])[0]
    if title:
        return unquote(title)

    path = parsed.path.rstrip("/")
    if "/wiki/" in path:
        return unquote(path.split("/wiki/", 1)[1])
    if "/w/" in path:
        return unquote(path.split("/w/", 1)[1])

    return None


def fetch_text(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (NovelLikeTextReader/1.0)"})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as error:
        raise _FetchTransportError(f"HTTP {error.code} while fetching {url}") from error
    except URLError as error:
        raise _FetchTransportError(f"Network error while fetching {url}: {error.reason}") from error
    except (TimeoutError, socket.timeout) as error:
        raise _FetchTransportError(f"Timeout while fetching {url}") from error
    except OSError as error:
        raise _FetchTransportError(f"I/O error while fetching {url}: {error}") from error


def extract_from_edit_page(html_text: str) -> str:
    match = re.search(
        r'<textarea[^>]*id=["\']wpTextbox1["\'][^>]*>(.*?)</textarea>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise CrawlError("未能在编辑页中找到 wpTextbox1 文本框")
    return html.unescape(match.group(1))


def extract_from_api(title: str, api_url: str = DEFAULT_API, timeout: int = 20) -> str:
    query = urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content",
            "titles": title,
            "redirects": "1",
            "format": "json",
            "formatversion": "2",
        }
    )
    payload = fetch_text(f"{api_url}?{query}", timeout=timeout)
    data = json.loads(payload)
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        raise CrawlError("API 返回为空")

    page = pages[0]
    if page.get("missing"):
        raise CrawlError(f"页面不存在: {title}")

    revisions = page.get("revisions") or []
    if not revisions:
        raise CrawlError(f"页面没有可用修订内容: {title}")

    revision = revisions[0]
    if "slots" in revision:
        return revision["slots"]["main"].get("content", "")

    return revision.get("content", "")


def resolve_story_title(source: str) -> Optional[str]:
    if source.startswith(("http://", "https://")):
        return normalize_title_from_url(source)
    return source.strip() or None


def fetch_story_text(source: str, timeout: int = 20, api_url: str = DEFAULT_API) -> str:
    title = resolve_story_title(source)
    if not title:
        raise CrawlError("未提供有效的剧情来源")

    try:
        return extract_from_api(title, api_url=api_url, timeout=timeout)
    except (_FetchTransportError, json.JSONDecodeError, KeyError, TypeError):
        html_text = fetch_text(build_edit_url(title), timeout=timeout)
        return extract_from_edit_page(html_text)


# Backward-compatible alias for other programs.
get_story_source = fetch_story_text


def write_output(text: str, output: Optional[str]) -> None:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="从 PRTS wiki 抓取单个剧情源码")
    parser.add_argument("source", help="页面标题或剧情 URL")
    parser.add_argument("-o", "--output", help="保存到文件")
    args = parser.parse_args()

    try:
        text = fetch_story_text(args.source)
        write_output(text, args.output)
        if args.output:
            print(f"已保存到 {args.output}", file=sys.stderr)
        return 0
    except CrawlError as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"错误: API 返回的不是有效 JSON: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
