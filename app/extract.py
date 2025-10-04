from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from bs4 import BeautifulSoup

from .browser import PageSnapshot


def extract_metadata(snapshot: PageSnapshot) -> Dict[str, Optional[str]]:
    soup = BeautifulSoup(snapshot.content, "html.parser")

    # Remove script/style elements when computing visible text
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text_content = soup.get_text(separator=" ", strip=True)
    words = [word for word in text_content.split() if word]

    description_tag = soup.find("meta", attrs={"name": "description"})
    description = description_tag.get("content") if description_tag else None

    h1_tag = soup.find("h1")
    h1_text = h1_tag.get_text(strip=True) if h1_tag else None

    metadata = {
        "title": snapshot.title,
        "final_url": snapshot.final_url,
        "http_status": snapshot.status,
        "meta_description": description,
        "h1": h1_text,
        "word_count": len(words),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "total_height": snapshot.total_height,
    }
    return metadata


__all__ = ["extract_metadata"]
