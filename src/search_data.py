"""
Web search data module — Exa-style search passthrough
Also supports DuckDuckGo HTML search as a free fallback.
"""
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException

# Exa API key (optional — enables premium search)
EXA_API_KEY = None
_env_key = os.environ.get("EXA_API_KEY")
if _env_key:
    EXA_API_KEY = _env_key

_DDG_HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AgentServices/2.0)",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _fetch_json(url, headers=None, timeout=10, data=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "AgentServices/2.0"})
    if data:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise HTTPException(status_code=429, detail="Rate limited by upstream. Retry shortly.")
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Search error: {str(e)}")


def _fetch_text(url, *, method="GET", data=None, headers=None, timeout=15):
    h = {"User-Agent": "AgentServices/2.0"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise HTTPException(status_code=429, detail="Rate limited by upstream. Retry shortly.")
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Search error: {str(e)}")


def _resolve_ddg_href(href: str) -> str:
    href = html.unescape(href)
    if href.startswith("//duckduckgo.com/l/?uddg="):
        href = urllib.parse.parse_qs(urllib.parse.urlparse("https:" + href).query).get("uddg", [href])[0]
    return href


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _parse_ddg_html_results(raw: str, num_results: int):
    """Parse DuckDuckGo HTML SERP into structured search hits."""
    results = []
    bodies = re.findall(
        r'<div class="links_main links_deep result__body">(.*?)</div>\s*</div>\s*</div>',
        raw,
        re.S,
    )
    for body in bodies:
        title_match = re.search(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', body, re.S)
        if not title_match:
            continue
        url = _resolve_ddg_href(title_match.group(1))
        title = _strip_html(title_match.group(2))
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.S)
        snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
        if not url.startswith(("http://", "https://")) or not title:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= num_results:
            break
    return results


def _duckduckgo_instant_answer(query: str, num_results: int):
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })
    data = _fetch_json(f"https://api.duckduckgo.com/?{params}")

    results = []
    if data.get("AbstractText"):
        results.append({
            "title": data.get("Heading", ""),
            "url": data.get("AbstractURL", ""),
            "snippet": data.get("AbstractText", ""),
            "source": data.get("AbstractSource", ""),
        })
    for topic in data.get("RelatedTopics", [])[:num_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            text = topic.get("Text", "")
            title = text.split(" - ")[0] if " - " in text else text[:80]
            results.append({
                "title": title,
                "url": topic.get("FirstURL", ""),
                "snippet": text,
            })
    return results[:num_results]


def _duckduckgo_html_search(query: str, num_results: int):
    payload = {"q": query, "b": "", "kl": ""}
    raw = _fetch_text(
        "https://html.duckduckgo.com/html/",
        method="POST",
        data=payload,
        headers=_DDG_HTML_HEADERS,
    )
    return _parse_ddg_html_results(raw, num_results)


def web_search(query: str, num_results: int = 5):
    """
    Web search using Exa API if key available, otherwise DuckDuckGo.
    Returns structured search results with title, URL, and snippet.
    """
    limit = min(max(int(num_results), 1), 10)

    if EXA_API_KEY:
        results = _fetch_json(
            "https://api.exa.ai/search",
            headers={
                "x-api-key": EXA_API_KEY,
                "Content-Type": "application/json",
            },
            data={
                "query": query,
                "num_results": limit,
                "type": "auto",
            },
        )
        hits = []
        for r in results.get("results", []):
            hits.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("text", "")[:300] if r.get("text") else "",
                "author": r.get("author"),
                "published_date": r.get("published_date"),
            })
        if not hits:
            raise HTTPException(status_code=502, detail="Search returned no results from upstream.")
        return {
            "query": query,
            "engine": "exa",
            "results": hits,
            "count": len(hits),
            "timestamp": int(time.time()),
        }

    results = _duckduckgo_instant_answer(query, limit)
    engine = "duckduckgo"
    if not results:
        results = _duckduckgo_html_search(query, limit)
        engine = "duckduckgo_html"
    if not results:
        raise HTTPException(status_code=502, detail="Search returned no results from upstream.")

    return {
        "query": query,
        "engine": engine,
        "results": results,
        "count": len(results),
        "timestamp": int(time.time()),
    }
