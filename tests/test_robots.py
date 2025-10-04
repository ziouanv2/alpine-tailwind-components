from pathlib import Path

import httpx
import pytest

from app.config import SearchSettings
from app.politeness import PolitenessManager, RobotsCache


@pytest.mark.asyncio
async def test_robots_disallow():
    async def handler(request: httpx.Request) -> httpx.Response:
        text = "User-agent: *\nDisallow: /private\nCrawl-delay: 2"
        return httpx.Response(200, text=text)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        settings = SearchSettings(
            input_file=Path("dummy.txt"),
            per_site_delay=1.0,
            global_rate_limit_qps=0,
            jitter_seconds=0.0,
        )
        robots_cache = RobotsCache("test-agent", client)
        allowed = await robots_cache.allowed("https://example.com/private/data")
        assert not allowed.allowed
        assert allowed.crawl_delay == 2


@pytest.mark.asyncio
async def test_politeness_manager_respects_delay():
    async def handler(request: httpx.Request) -> httpx.Response:
        text = "User-agent: test-agent\nAllow: /"
        return httpx.Response(200, text=text)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        settings = SearchSettings(
            input_file=Path("dummy.txt"),
            per_site_delay=0.1,
            global_rate_limit_qps=0,
            jitter_seconds=0.0,
        )
        robots_cache = RobotsCache("test-agent", client)
        politeness = PolitenessManager(settings, robots_cache)
        allowed, delay = await politeness.ensure_allowed("https://example.org/page")
        assert allowed
        assert delay >= 0.1
