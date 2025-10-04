from pathlib import Path

import httpx
import pytest

from app.search import APISettings, SearchClient, SearchSettings


@pytest.mark.asyncio
async def test_search_paginates_and_deduplicates():
    responses = {
        1: {
            "items": [
                {"link": f"https://example.com/{i}", "title": f"Result {i}", "snippet": "Snippet"}
                for i in range(1, 11)
            ]
        },
        11: {
            "items": [
                {"link": "https://example.com/5", "title": "Duplicate", "snippet": "dup"},
                {"link": "https://example.com/11", "title": "Result 11", "snippet": "Snippet"},
            ]
        },
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("start", "1"))
        payload = responses.get(start, {"items": []})
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        api_settings = APISettings(provider="google", google_api_key="x", google_cx="y")
        search_settings = SearchSettings(
            input_file=Path("dummy.txt"),
            max_results_per_keyword=12,
            per_site_delay=0,
            global_rate_limit_qps=0,
        )
        search_client = SearchClient(api_settings, search_settings, http_client=client)
        results = await search_client.search("test keyword")
        urls = [result.url for result in results]
        assert "https://example.com/5" in urls
        assert urls.count("https://example.com/5") == 1
        assert len(results) == 11
