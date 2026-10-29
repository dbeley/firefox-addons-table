"""Offline tests for the AMO parsing layer.

The fixtures are real AMO v5 API payloads. They are what protects the project
from the previous regression: the export used to scrape HTML, Mozilla changed
the page (and then put a bot challenge in front of it), and nothing noticed.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from amo import (
    AddonNotFound,
    fetch_addon,
    format_last_update,
    format_size,
    localised,
    parse_addon,
)
from table_export import collect_addons, split_repository_url

FIXTURES = Path(__file__).parent / "fixtures"

CATEGORY_NAMES = {
    "privacy-security": "Privacy & Security",
    "feeds-news-blogging": "Feeds, News & Blogging",
    "search-tools": "Search Tools",
    "social-communication": "Social & Communication",
}


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def localcdn() -> dict:
    return load_fixture("localcdn")


@pytest.fixture
def mal_sync() -> dict:
    return load_fixture("mal-sync")


def test_parse_addon_maps_every_displayed_column(localcdn):
    row = parse_addon(localcdn, CATEGORY_NAMES)

    assert row["addon_name"] == "LocalCDN"
    assert row["url"] == (
        "https://addons.mozilla.org/en-US/firefox/addon/"
        "localcdn-fork-of-decentraleyes/"
    )
    assert row["user"] == "nobody"
    assert row["user_link"].startswith("https://addons.mozilla.org/")
    assert row["number_users"] == 19132
    assert row["number_reviews"] == 262
    assert row["average_rating"] == 4.8
    assert row["addon_version"] == "2.6.86"
    assert row["addon_size"] == "27.93 MB"
    assert row["addon_license"] == "Mozilla Public License 2.0"
    assert row["repository_link"] == "https://www.localcdn.org"
    assert row["addon_categories"] == "Privacy & Security"
    assert row["addon_icon"].endswith("-64.png?modified=b2f5fc36")


def test_parse_addon_joins_multiple_categories(mal_sync):
    row = parse_addon(mal_sync, CATEGORY_NAMES)
    assert row["addon_categories"] == (
        "Feeds, News & Blogging, Search Tools, Social & Communication"
    )
    assert row["repository_link"] == "https://github.com/lolamtisch/MALSync"


def test_parse_addon_without_ratings_or_version():
    row = parse_addon({"slug": "brand-new", "name": {"en-US": "Brand New"}})
    assert row["average_rating"] is None
    assert row["number_reviews"] is None
    assert row["addon_version"] == ""
    assert row["addon_size"] == ""
    assert row["addon_last_update"] == ""
    assert row["addon_license"] == ""


def test_parse_addon_falls_back_to_support_url():
    addon = {
        "slug": "fallback",
        "name": {"en-US": "Fallback"},
        "support_url": {"url": {"en-US": "https://github.com/owner/name"}},
    }
    assert parse_addon(addon)["repository_link"] == "https://github.com/owner/name"


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (29289206, "27.93 MB"),
        (980480, "957.50 KB"),
        (512, "512 B"),
        (0, ""),
        (None, ""),
        ("nonsense", ""),
    ],
)
def test_format_size(size, expected):
    assert format_size(size) == expected


def test_format_last_update_matches_old_display():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    assert format_last_update("2026-09-08T22:09:55Z", now=now) == (
        "a month ago (Sep 8, 2026)"
    )
    assert format_last_update("2026-10-23T10:00:00Z", now=now) == (
        "6 days ago (Oct 23, 2026)"
    )
    assert format_last_update("2025-10-23T10:00:00Z", now=now) == (
        "a year ago (Oct 23, 2025)"
    )
    assert format_last_update("", now=now) == ""
    assert format_last_update(None, now=now) == ""


def test_localised_handles_strings_and_other_locales():
    assert localised("plain") == "plain"
    assert localised({"fr": "Bonjour"}) == "Bonjour"
    assert localised(None) == ""


def test_localised_uses_default_locale_when_english_is_null():
    # Real payload shape for add-ons whose default locale is not en-US.
    value = {"en-GB": "addy.io alias manager", "en-US": None, "_default": "en-GB"}
    assert localised(value) == "addy.io alias manager"


def test_parse_addon_falls_back_to_the_slug_when_unnamed():
    row = parse_addon({"slug": "no-name", "name": {"en-US": None}})
    assert row["addon_name"] == "no-name"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://github.com/gorhill/uBlock#ublock-origin",
            ("github.com", "gorhill/uBlock"),
        ),
        ("https://github.com/owner/name.git", ("github.com", "owner/name")),
        ("https://github.com/owner/name/tree/main/src", ("github.com", "owner/name")),
        ("https://gitlab.com/group/sub/project", ("gitlab.com", "group/sub/project")),
        (
            "https://gitlab.com/group/project/-/tree/master/pkgs",
            ("gitlab.com", "group/project"),
        ),
        ("https://codeberg.org/owner/name/", ("codeberg.org", "owner/name")),
        ("https://www.localcdn.org", ("localcdn.org", "")),
        ("", ("", "")),
    ],
)
def test_split_repository_url(url, expected):
    assert split_repository_url(url) == expected


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Minimal stand-in for requests.Session, serving add-on payloads by slug."""

    def __init__(self, addons: dict[str, dict | None], missing_status_code: int = 404):
        self.addons = addons
        self.missing_status_code = missing_status_code

    def get(self, url, params=None, timeout=None):
        if "categories" in url:
            return FakeResponse(
                [
                    {"slug": "other", "name": "Other"},
                    {"slug": "search-tools", "name": "Search Tools"},
                ]
            )
        slug = url.rstrip("/").split("/")[-1]
        payload = self.addons.get(slug)
        if payload is None:
            return FakeResponse({}, status_code=self.missing_status_code)
        return FakeResponse(payload)


def test_fetch_addon_raises_for_a_missing_slug():
    session = FakeSession({"gone": None})
    with pytest.raises(AddonNotFound):
        fetch_addon(session, "gone")


def test_fetch_addon_treats_disabled_addons_as_gone():
    """Disabled add-ons answer 401, not 404, and must be skipped."""
    session = FakeSession({"disabled": None}, missing_status_code=401)
    with pytest.raises(AddonNotFound):
        fetch_addon(session, "disabled")


def test_collect_addons_skips_removed_addons(localcdn, mal_sync):
    session = FakeSession(
        {
            "localcdn-fork-of-decentraleyes": localcdn,
            "mal-sync": mal_sync,
            "gone": None,
        }
    )
    rows = collect_addons(
        ["localcdn-fork-of-decentraleyes", "gone", "mal-sync"],
        session=session,
        apis={},
    )
    assert [row["addon_name"] for row in rows] == ["LocalCDN", "MAL-Sync"]


def test_collect_addons_survives_a_broken_item(localcdn):
    class ExplodingSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            if url.rstrip("/").endswith("explodes"):
                raise RuntimeError("connection reset")
            return super().get(url, params=params, timeout=timeout)

    session = ExplodingSession({"localcdn-fork-of-decentraleyes": localcdn})
    rows = collect_addons(
        ["explodes", "localcdn-fork-of-decentraleyes"], session=session, apis={}
    )
    assert len(rows) == 1


def test_collect_addons_aborts_when_everything_fails():
    session = FakeSession({slug: None for slug in [f"missing-{i}" for i in range(20)]})
    with pytest.raises(RuntimeError):
        collect_addons([f"missing-{i}" for i in range(20)], session=session, apis={})
