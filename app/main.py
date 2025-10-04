from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .browser import BrowserSession
from .config import AppConfig, load_config
from .extract import extract_metadata
from .politeness import PolitenessManager, RobotsCache
from .search import KeywordReader, SearchClient
from .storage import StorageWriter


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {"args", "msg", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process"}:
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async web research collector")
    parser.add_argument("--config", type=Path, required=True, help="Path to YAML configuration file")
    parser.add_argument("--input", type=Path, help="Override keyword input file")
    parser.add_argument("--max-per-keyword", type=int, dest="max_per_keyword", help="Maximum results per keyword")
    parser.add_argument("--output", type=Path, help="Output file or directory")
    parser.add_argument("--output-format", choices=["jsonl", "csv"], help="Output format override")
    parser.add_argument("--provider", choices=["google", "bing"], help="Search provider override")
    parser.add_argument("--allowed-domains", nargs="*", help="Optional whitelist of domains")
    parser.add_argument("--blocked-domains", nargs="*", help="Optional blocklist of domains")
    parser.add_argument("--per-site-delay", type=float, help="Base delay between requests to the same domain")
    parser.add_argument("--global-rate", type=float, help="Maximum global queries per second")
    return parser


def configure_logging(config: AppConfig) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, config.logging.level.upper(), logging.INFO))


async def run(config: AppConfig) -> None:
    keywords = KeywordReader.read_keywords(config.search.input_file)
    if not keywords:
        logging.getLogger(__name__).warning("No keywords found", extra={"event": "keywords.empty"})
        return

    storage = StorageWriter(config.output)
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            async with SearchClient(config.api, config.search) as search_client:
                async with BrowserSession(config.browser, config.search.user_agent) as browser:
                    robots_cache = RobotsCache(config.search.user_agent, http_client)
                    politeness = PolitenessManager(config.search, robots_cache)
                    for keyword in keywords:
                        request_id = uuid.uuid4().hex
                        logging.getLogger(__name__).info(
                            "Processing keyword",
                            extra={"event": "keyword.start", "keyword": keyword, "request_id": request_id},
                        )
                        try:
                            results = await search_client.search(keyword)
                        except Exception as exc:  # noqa: BLE001
                            logging.getLogger(__name__).error(
                                "Search failed",
                                extra={"event": "keyword.search_failed", "keyword": keyword, "error": str(exc), "request_id": request_id},
                            )
                            continue

                        for result in results:
                            allowed, delay_used = await politeness.ensure_allowed(result.url)
                            if not allowed:
                                logging.getLogger(__name__).info(
                                    "Robots.txt disallows fetch",
                                    extra={
                                        "event": "robots.disallow",
                                        "keyword": keyword,
                                        "url": result.url,
                                        "request_id": request_id,
                                    },
                                )
                                continue
                            snapshot = await browser.fetch(result.url)
                            if not snapshot:
                                logging.getLogger(__name__).warning(
                                    "Failed to capture page",
                                    extra={
                                        "event": "browser.fetch_failed",
                                        "keyword": keyword,
                                        "url": result.url,
                                        "request_id": request_id,
                                    },
                                )
                                continue
                            metadata = extract_metadata(snapshot)
                            record = {
                                "request_id": request_id,
                                "keyword": keyword,
                                "search_title": result.title,
                                "search_snippet": result.snippet,
                                "original_url": snapshot.url,
                                **metadata,
                            }
                            await storage.write_record(keyword, record)
                            logging.getLogger(__name__).info(
                                "Stored result",
                                extra={
                                    "event": "storage.record",
                                    "keyword": keyword,
                                    "url": snapshot.final_url,
                                    "delay_used": delay_used,
                                    "request_id": request_id,
                                },
                            )
    finally:
        await storage.close()


def apply_cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    if args.provider:
        overrides.setdefault("api", {})["provider"] = args.provider
    if args.max_per_keyword is not None:
        overrides.setdefault("search", {})["max_results_per_keyword"] = args.max_per_keyword
    if args.input is not None:
        overrides.setdefault("search", {})["input_file"] = str(args.input)
    if args.allowed_domains is not None:
        overrides.setdefault("search", {})["allowed_domains"] = args.allowed_domains
    if args.blocked_domains is not None:
        overrides.setdefault("search", {})["blocked_domains"] = args.blocked_domains
    if args.per_site_delay is not None:
        overrides.setdefault("search", {})["per_site_delay"] = args.per_site_delay
    if args.global_rate is not None:
        overrides.setdefault("search", {})["global_rate_limit_qps"] = args.global_rate
    if args.output is not None:
        overrides.setdefault("output", {})["output_path"] = str(args.output)
    if args.output_format is not None:
        overrides.setdefault("output", {})["output_format"] = args.output_format
    return overrides


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    overrides = apply_cli_overrides(args)
    loaded = load_config(args.config, overrides)
    configure_logging(loaded.config)

    try:
        asyncio.run(run(loaded.config))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interrupted by user", extra={"event": "app.cancelled"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
