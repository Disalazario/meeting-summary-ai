"""GraphQL клиент к Wiki.js. Не имеет состояния, только сетевые вызовы.

Используется в wiki_sync для регулярной выгрузки страниц.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class WikiPageMeta:
    id: int
    title: str
    path: str
    locale: str
    is_published: bool
    updated_at: Optional[datetime]


@dataclass
class WikiPageContent:
    id: int
    title: str
    path: str
    locale: str
    content_type: str
    content: str
    updated_at: Optional[datetime]


def is_configured() -> bool:
    return bool(settings.WIKI_BASE_URL and settings.WIKI_API_TOKEN)


def _endpoint() -> str:
    return settings.WIKI_BASE_URL.rstrip("/") + "/graphql"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.WIKI_API_TOKEN}"}


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Wiki.js отдаёт ISO 8601 с Z; fromisoformat понимает "+00:00".
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


_LIST_QUERY = """{
  pages {
    list(orderBy: ID, orderByDirection: DESC) {
      id title path locale isPublished updatedAt
    }
  }
}"""


_SINGLE_QUERY = """query($id: Int!) {
  pages {
    single(id: $id) {
      id title path locale contentType content updatedAt
    }
  }
}"""


def list_pages(timeout: float = 30.0) -> list[WikiPageMeta]:
    """Получить список всех страниц Wiki.js (только опубликованные)."""
    if not is_configured():
        raise RuntimeError("Wiki.js не настроен — нет WIKI_BASE_URL / WIKI_API_TOKEN")
    with httpx.Client(timeout=timeout) as c:
        r = c.post(_endpoint(), json={"query": _LIST_QUERY}, headers=_headers())
        r.raise_for_status()
        data = r.json()
    if "errors" in data:
        raise RuntimeError(f"Wiki.js GraphQL errors: {data['errors']}")
    raw = data.get("data", {}).get("pages", {}).get("list", []) or []
    out = []
    for p in raw:
        if not p.get("isPublished"):
            continue
        out.append(WikiPageMeta(
            id=int(p["id"]),
            title=p.get("title") or "",
            path=p.get("path") or "",
            locale=p.get("locale") or "ru",
            is_published=bool(p.get("isPublished")),
            updated_at=_parse_dt(p.get("updatedAt")),
        ))
    logger.info(f"Wiki.js: {len(out)} опубликованных страниц")
    return out


def get_page(page_id: int, timeout: float = 30.0) -> Optional[WikiPageContent]:
    """Получить содержимое страницы по wiki_id."""
    if not is_configured():
        raise RuntimeError("Wiki.js не настроен")
    with httpx.Client(timeout=timeout) as c:
        r = c.post(
            _endpoint(),
            json={"query": _SINGLE_QUERY, "variables": {"id": int(page_id)}},
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
    if "errors" in data:
        logger.warning(f"Wiki.js get_page({page_id}) errors: {data['errors']}")
        return None
    p = data.get("data", {}).get("pages", {}).get("single")
    if not p:
        return None
    return WikiPageContent(
        id=int(p["id"]),
        title=p.get("title") or "",
        path=p.get("path") or "",
        locale=p.get("locale") or "ru",
        content_type=p.get("contentType") or "markdown",
        content=p.get("content") or "",
        updated_at=_parse_dt(p.get("updatedAt")),
    )
