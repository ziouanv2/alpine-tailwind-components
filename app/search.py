from __future__ import annotations

import asyncio
import csv
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import APISettings, SearchSettings

logger = logging.getLogger(__name__)


class SearchError(RuntimeError):
    """Raised when the search API fails."""


@dataclass
class SearchResult:
    keyword: str
    title: str
    url: str
    snippet: Optional[str]


class AsyncRateLimiter:
    def __init__(self, qps: float):
        self.min_interval = 1.0 / qps if qps > 0 else 0.0
        self._lock = asyncio.Lock()
        self._last_time = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            if self.min_interval <= 0:
                return
            now = time.monotonic()
            wait_time = self.min_interval - (now - self._last_time)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_time = time.monotonic()


class KeywordReader:
    @staticmethod
    def read_keywords(path: Path) -> List[str]:
        if not path.exists():
            raise FileNotFoundError(f"Keyword file not found: {path}")

        keywords: List[str] = []
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    for cell in row:
                        cell = cell.strip()
                        if cell:
                            keywords.append(cell)
        else:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    keyword = line.strip()
                    if keyword:
                        keywords.append(keyword)

        deduped = []
        seen: Set[str] = set()
        for keyword in keywords:
            normalized = keyword.lower()
            if normalized not in seen:
                deduped.append(keyword)
                seen.add(normalized)
        return deduped


class SearchClient:
    def __init__(
        self,
        api_settings: APISettings,
        search_settings: SearchSettings,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_settings = api_settings
        self.search_settings = search_settings
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        self._rate_limiter = AsyncRateLimiter(search_settings.global_rate_limit_qps)

    async def __aenter__(self) -> "SearchClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._client.aclose()

    async def search(self, keyword: str) -> List[SearchResult]:
        if self.api_settings.provider == "google":
            return await self._search_google(keyword)
        raise NotImplementedError("Only Google Custom Search is implemented in this example")

    async def _search_google(self, keyword: str) -> List[SearchResult]:
        max_results = self.search_settings.max_results_per_keyword
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        pages = math.ceil(max_results / 10)

        for page in range(pages):
            start_index = page * 10 + 1
            if len(results) >= max_results:
                break
            await self._rate_limiter.acquire()
            logger.debug("Fetching search results", extra={"keyword": keyword, "start": start_index})
            response_data = await self._call_with_retry(
                url="https://www.googleapis.com/customsearch/v1",
                params={
                    "key": self.api_settings.google_api_key,
                    "cx": self.api_settings.google_cx,
                    "q": keyword,
                    "start": start_index,
                },
            )
            items = response_data.get("items", [])
            if not items:
                break
            for item in items:
                link = item.get("link")
                if not link or link in seen_urls:
                    continue
                if not self._is_domain_allowed(link):
                    continue
                seen_urls.add(link)
                result = SearchResult(
                    keyword=keyword,
                    title=item.get("title", ""),
                    url=link,
                    snippet=item.get("snippet"),
                )
                results.append(result)
                if len(results) >= max_results:
                    break
        return results

    async def _call_with_retry(self, url: str, params: Dict[str, str]) -> Dict[str, Any]:
        async for attempt in AsyncRetrying(
            wait=wait_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(5),
            reraise=True,
            retry=retry_if_exception_type((httpx.HTTPError, SearchError)),
        ):
            with attempt:
                response = await self._client.get(url, params=params, headers={"User-Agent": self.search_settings.user_agent})
                if response.status_code == 200:
                    return response.json()
                if response.status_code in {429, 500, 502, 503, 504}:
                    logger.warning(
                        "Search API rate limited or server error",
                        extra={"status": response.status_code, "body": response.text[:200]},
                    )
                    raise SearchError(f"Search API error {response.status_code}")
                response.raise_for_status()
        raise SearchError("Failed to fetch search results after retries")

    def _is_domain_allowed(self, url: str) -> bool:
        allowed = self.search_settings.allowed_domains
        blocked = self.search_settings.blocked_domains or []
        if not allowed and not blocked:
            return True
        hostname = urlparse(url).hostname or ""
        hostname = hostname.lower()
        if blocked and any(hostname.endswith(domain.lower()) for domain in blocked):
            return False
        if allowed:
            return any(hostname.endswith(domain.lower()) for domain in allowed)
        return True


__all__ = ["KeywordReader", "SearchClient", "SearchResult", "SearchError", "AsyncRateLimiter"]
