from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

try:
    from playwright.async_api import Browser, BrowserContext, Error as PlaywrightError, Page, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - allows unit tests without playwright
    Browser = BrowserContext = Page = None  # type: ignore[assignment]
    PlaywrightError = Exception  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_AVAILABLE = False

from .config import BrowserSettings

logger = logging.getLogger(__name__)


@dataclass
class PageSnapshot:
    url: str
    final_url: str
    title: str
    status: Optional[int]
    content: str
    total_height: Optional[int]


class BrowserSession:
    def __init__(self, settings: BrowserSettings, user_agent: str):
        self.settings = settings
        self.user_agent = user_agent
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._semaphore = asyncio.Semaphore(3)

    async def __aenter__(self) -> "BrowserSession":
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is required. Install it via `pip install playwright` and run `playwright install`.")
        self._playwright = await async_playwright().start()
        browser_args = {"headless": self.settings.headless}
        if self.settings.proxy:
            browser_args["proxy"] = {"server": self.settings.proxy}
        self._browser = await self._playwright.chromium.launch(**browser_args)
        self._context = await self._browser.new_context(user_agent=self.user_agent)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch(self, url: str) -> Optional[PageSnapshot]:
        if not self._context:
            raise RuntimeError("BrowserSession must be used as an async context manager")
        async with self._semaphore:
            page: Page = await self._context.new_page()
            try:
                response = await page.goto(
                    url,
                    wait_until=self.settings.wait_until,
                    timeout=self.settings.timeout_ms,
                )
                await self._scroll_page(page)
                content = await page.content()
                total_height = await page.evaluate("() => document.body ? document.body.scrollHeight : null")
                snapshot = PageSnapshot(
                    url=url,
                    final_url=page.url,
                    title=await page.title(),
                    status=response.status if response else None,
                    content=content,
                    total_height=total_height,
                )
                return snapshot
            except PlaywrightError as exc:
                logger.warning("Browser navigation failed", extra={"url": url, "error": str(exc)})
                return None
            finally:
                await page.close()

    async def _scroll_page(self, page: Page) -> None:
        last_height = 0
        for step in range(self.settings.max_scroll_steps):
            current_height = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
            if current_height <= last_height:
                break
            await page.evaluate("(distance) => window.scrollBy(0, distance)", self.settings.scroll_step)
            await page.wait_for_timeout(500)
            last_height = current_height


__all__ = ["BrowserSession", "PageSnapshot"]
