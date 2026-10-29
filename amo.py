"""Mozilla Add-ons (AMO) data access.

The project used to scrape addons.mozilla.org HTML pages. Mozilla now protects
those pages with a bot challenge ("Client Challenge"), so every scrape returned
a JavaScript interstitial instead of the add-on page and the export crashed on
the first selector lookup.

This module talks to the public AMO v5 JSON API instead. It exposes the same
information the table needs (users, ratings, version, size, license, homepage,
categories) in a stable, machine-readable form.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

AMO_API_URL = "https://addons.mozilla.org/api/v5"
ADDON_PAGE_URL = "https://addons.mozilla.org/en-US/firefox/addon"
DEFAULT_LOCALE = "en-US"

# (connect, read) timeouts: the AMO API is normally fast, but a hung request
# must never stall the whole weekly run.
REQUEST_TIMEOUT = (10, 30)

_MEGABYTE = 1024 * 1024
_KILOBYTE = 1024


class AddonNotFound(Exception):
    """The add-on is not publicly available on addons.mozilla.org.

    Either the slug does not exist (HTTP 404) or the add-on was disabled by its
    developer or by Mozilla, which the API reports as HTTP 401 with
    ``is_disabled_by_developer`` / ``is_disabled_by_mozilla``.
    """


def build_session() -> requests.Session:
    """Return a session with retries and an explicit timeout policy."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def localised(value: Any, locale: str = DEFAULT_LOCALE) -> str:
    """Return a translated field, which the API sends as either str or dict.

    Translated fields look like ``{"en-US": "…"}`` but not always: an add-on
    whose default locale is British English comes back as
    ``{"en-GB": "…", "en-US": None, "_default": "en-GB"}``, so a naive
    ``value["en-US"]`` yields ``None``.
    """
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""

    candidates = [locale]
    default_locale = value.get("_default")
    if isinstance(default_locale, str):
        candidates.append(default_locale)
    candidates.extend(key for key in value if key.startswith("en"))
    candidates.extend(value.keys())

    for key in candidates:
        if key == "_default":
            continue
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return ""


def get_category_names(
    session: requests.Session, locale: str = DEFAULT_LOCALE
) -> dict[str, str]:
    """Map AMO category slugs ("privacy-security") to display names."""
    response = session.get(
        f"{AMO_API_URL}/addons/categories/",
        params={"lang": locale, "page_size": 100},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    categories = payload["results"] if isinstance(payload, dict) else payload
    return {
        category["slug"]: localised(category.get("name"), locale)
        for category in categories
        if category.get("slug")
    }


def fetch_addon(
    session: requests.Session, slug: str, locale: str = DEFAULT_LOCALE
) -> dict[str, Any]:
    """Fetch one add-on from the AMO API."""
    response = session.get(
        f"{AMO_API_URL}/addons/addon/{slug}/",
        params={"lang": locale},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code in (401, 403, 404):
        # Hidden add-ons (disabled by the developer or by Mozilla) answer 401
        # rather than 404: they are simply not public anymore, skip them.
        raise AddonNotFound(slug)
    response.raise_for_status()
    return response.json()


def format_size(size_in_bytes: Any) -> str:
    """Format a file size the way addons.mozilla.org does (``21.98 MB``)."""
    try:
        size = float(size_in_bytes)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    if size >= _MEGABYTE:
        return f"{size / _MEGABYTE:.2f} MB"
    if size >= _KILOBYTE:
        return f"{size / _KILOBYTE:.2f} KB"
    return f"{size:.0f} B"


def _relative_days(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = days // 7
        return "a week ago" if weeks == 1 else f"{weeks} weeks ago"
    if days < 365:
        months = days // 30
        return "a month ago" if months == 1 else f"{months} months ago"
    years = days // 365
    return "a year ago" if years == 1 else f"{years} years ago"


def format_last_update(value: Any, now: datetime | None = None) -> str:
    """Render the API timestamp like the old page did: ``3 months ago (Sep 8, 2026)``."""
    if not isinstance(value, str) or not value:
        return ""
    try:
        updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    reference = now or datetime.now(timezone.utc)
    days = (reference.date() - updated.date()).days
    return f"{_relative_days(days)} ({updated:%b} {updated.day}, {updated.year})"


def parse_addon(
    addon: dict[str, Any],
    category_names: dict[str, str] | None = None,
    locale: str = DEFAULT_LOCALE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Convert an AMO API payload into one CSV row.

    The returned keys must stay in sync with the ones ``html_builder.py`` reads.
    """
    category_names = category_names or {}
    slug = addon.get("slug", "")
    version = addon.get("current_version") or {}
    ratings = addon.get("ratings") or {}
    license_info = version.get("license") or {}
    file_info = version.get("file") or {}

    authors = addon.get("authors") or [{}]
    primary_author = authors[0] if authors else {}

    repository_link = localised((addon.get("homepage") or {}).get("url"), locale)
    if not repository_link:
        repository_link = localised((addon.get("support_url") or {}).get("url"), locale)

    average_rating = ratings.get("average")
    if not ratings.get("count") or average_rating is None:
        average_rating = None
    else:
        average_rating = round(float(average_rating), 1)

    categories = [
        category_names.get(category, category)
        for category in addon.get("categories") or []
    ]

    return {
        "url": f"{ADDON_PAGE_URL}/{slug}/",
        # A few add-ons have no usable translated name: fall back to the slug
        # so the row stays identifiable instead of sorting as an empty string.
        "addon_name": localised(addon.get("name"), locale) or slug,
        "addon_icon": addon.get("icon_url") or (addon.get("icons") or {}).get("64", ""),
        "user": primary_author.get("name", ""),
        "user_link": primary_author.get("url", ""),
        "number_users": addon.get("average_daily_users"),
        "number_reviews": ratings.get("count"),
        "average_rating": average_rating,
        "repository_link": repository_link,
        "repository_domain": "",
        "addon_summary": localised(addon.get("summary"), locale),
        "addon_version": version.get("version", ""),
        "addon_size": format_size(file_info.get("size")),
        "addon_last_update": format_last_update(addon.get("last_updated"), now=now),
        "addon_license": localised(license_info.get("name"), locale),
        "addon_categories": ", ".join(categories),
        # Filled in later from the repository host APIs.
        "repository_stars_count": None,
        "repository_last_update": None,
    }
