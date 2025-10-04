from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Dict, Optional, Tuple
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx

from .config import SearchSettings

logger = logging.getLogger(__name__)


class RobotsPolicy:
    def __init__(self, allowed: bool, crawl_delay: Optional[float]):
        self.allowed = allowed
        self.crawl_delay = crawl_delay


class RobotsCache:
    def __init__(self, user_agent: str, http_client: httpx.AsyncClient):
        self.user_agent = user_agent
        self._client = http_client
        self._cache: Dict[str, robotparser.RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def allowed(self, url: str) -> RobotsPolicy:
        parsed = urlparse(url)
        netloc = parsed.netloc
        if not netloc:
            return RobotsPolicy(True, None)
        async with self._lock:
            parser = self._cache.get(netloc)
            if not parser:
                parser = await self._load_parser(parsed.scheme or "http", netloc)
                self._cache[netloc] = parser
        path = parsed.path or "/"
        allowed = parser.can_fetch(self.user_agent, path)
        crawl_delay = parser.crawl_delay(self.user_agent)
        return RobotsPolicy(allowed, crawl_delay)

    async def _load_parser(self, scheme: str, netloc: str) -> robotparser.RobotFileParser:
        robots_url = urljoin(f"{scheme}://{netloc}", "/robots.txt")
        parser = robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            response = await self._client.get(robots_url, headers={"User-Agent": self.user_agent}, timeout=10.0)
            if response.status_code >= 400:
                parser.parse([])
            else:
                parser.parse(response.text.splitlines())
        except httpx.HTTPError as exc:
            logger.debug("Failed to fetch robots.txt", extra={"url": robots_url, "error": str(exc)})
            parser.parse([])
        return parser


class PolitenessManager:
    def __init__(self, settings: SearchSettings, robots_cache: RobotsCache):
        self.settings = settings
        self.robots_cache = robots_cache
        self._domain_timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def ensure_allowed(self, url: str) -> Tuple[bool, Optional[float]]:
        policy = await self.robots_cache.allowed(url)
        if not policy.allowed:
            return False, None
        delay = policy.crawl_delay if policy.crawl_delay is not None else self.settings.per_site_delay
        jitter = random.uniform(0, self.settings.jitter_seconds)
        delay = max(delay, 0.0) + jitter
        parsed = urlparse(url)
        domain = parsed.netloc
        await self._apply_delay(domain, delay)
        return True, delay

    async def _apply_delay(self, domain: str, delay: float) -> None:
        async with self._lock:
            now = time.monotonic()
            last = self._domain_timestamps.get(domain, 0.0)
            wait_time = last + delay - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.monotonic()
            self._domain_timestamps[domain] = now


__all__ = ["RobotsCache", "PolitenessManager", "RobotsPolicy"]
