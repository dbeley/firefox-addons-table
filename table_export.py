"""Build export.csv from the list of Firefox add-ons.

Data comes from the AMO JSON API (see ``amo.py``) instead of HTML scraping, and
the repository statistics (stars, last update) come from the host APIs.

Run with ``python table_export.py`` after generating ``firefox-addons.txt``.
Environment variables:
    GITHUB_TOKEN     - optional, raises the GitHub API rate limit (60 req/h without)
    GITLAB_TOKEN     - optional, same for gitlab.com
    GITLAB_KDE_TOKEN - optional, same for invent.kde.org
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from github import Auth, Github
from gitlab import Gitlab

from amo import (
    AddonNotFound,
    build_session,
    fetch_addon,
    get_category_names,
    parse_addon,
)
from utils import (
    get_codeberg_repository_data,
    get_github_repository_data,
    get_gitlab_repository_data,
    get_gitlab_repository_data_with_webscraping,
    get_sourcehunt_repository_data_with_webscraping,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s :: %(message)s")
logger = logging.getLogger(__name__)

# Path segments that point inside a repository rather than at its root.
_REPOSITORY_VIEW_SEGMENTS = {
    "archive",
    "blob",
    "commits",
    "issues",
    "pulls",
    "raw",
    "releases",
    "src",
    "tree",
    "wiki",
}


def github_client(token: str | None) -> Github:
    """Return an authenticated client when a token is available, else anonymous."""
    if token:
        return Github(auth=Auth.Token(token))
    return Github()


def build_repository_apis() -> dict[str, object]:
    """Create the authenticated clients used for repository statistics."""
    return {
        "github.com": github_client(os.environ.get("GITHUB_TOKEN")),
        "gitlab.com": Gitlab(private_token=os.environ.get("GITLAB_TOKEN") or None),
        "invent.kde.org": Gitlab(
            url="https://invent.kde.org",
            private_token=os.environ.get("GITLAB_KDE_TOKEN") or None,
        ),
    }


def split_repository_url(repository_url: str) -> tuple[str, str]:
    """Return ``(host, "owner/name")`` for a repository URL.

    Handles fragments, query strings, ``.git`` suffixes, links straight to a
    file inside the repository, and GitLab subgroups. Anything that does not
    look like a repository root returns an empty name, which disables the
    statistics lookup instead of hitting an API with a bogus path.
    """
    if not repository_url:
        return "", ""
    if "://" not in repository_url:
        repository_url = f"https://{repository_url}"
    parsed = urlparse(repository_url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/").removesuffix(".git")
    path = path.split("/-/")[0]
    segments = [segment for segment in path.split("/") if segment]
    while segments and segments[-1] in _REPOSITORY_VIEW_SEGMENTS:
        segments.pop()
    # GitHub and Codeberg have a single namespace level, GitLab allows subgroups.
    if host in {"github.com", "codeberg.org"}:
        segments = segments[:2]
    if len(segments) < 2:
        return host, ""
    return host, "/".join(segments)


def get_repository_stats(
    repository_domain: str, repository_name: str, apis: dict[str, object]
) -> dict[str, int]:
    """Dispatch to the right host API. Unknown hosts return an empty dict."""
    match repository_domain:
        case "github.com":
            return get_github_repository_data(apis["github.com"], repository_name)
        case "codeberg.org":
            return get_codeberg_repository_data(repository_name)
        case "gitlab.com":
            return get_gitlab_repository_data(apis["gitlab.com"], repository_name)
        case "invent.kde.org":
            return get_gitlab_repository_data(apis["invent.kde.org"], repository_name)
        case "gitlab.gnome.org" | "source.puri.sm" | "gitlab.manjaro.org":
            return get_gitlab_repository_data_with_webscraping(
                f"https://{repository_domain}/{repository_name}"
            )
        case "sr.ht" | "git.sr.ht":
            return get_sourcehunt_repository_data_with_webscraping(
                f"https://{repository_domain}/{repository_name}"
            )
    return {}


def load_addon_slugs(path: str) -> list[str]:
    """Read the list of slugs, ignoring blank lines and comments."""
    with open(path, "r", encoding="utf-8") as handle:
        return [
            line.strip()
            for line in handle
            if line.strip() and not line.strip().startswith("#")
        ]


def collect_addons(
    slugs: list[str],
    session=None,
    apis: dict[str, object] | None = None,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Fetch every add-on and return the rows of the CSV.

    One broken add-on must not abort the whole run: each item is isolated, and
    the run only fails when the failure ratio gets high enough to mean the API
    itself changed (which is how the previous regression went unnoticed for a
    year).
    """
    session = session or build_session()
    apis = apis if apis is not None else build_repository_apis()
    category_names = get_category_names(session)

    rows: list[dict[str, object]] = []
    failures = 0
    max_failures = max(10, int(0.01 * len(slugs)))

    for index, slug in enumerate(slugs, 1):
        try:
            addon = fetch_addon(session, slug)
            row = parse_addon(addon, category_names, now=now)
            domain, repository_name = split_repository_url(row["repository_link"])
            row["repository_domain"] = domain or None
            if repository_name:
                try:
                    row.update(get_repository_stats(domain, repository_name, apis))
                except Exception as error:  # noqa: BLE001 - stats are optional data
                    logger.warning(
                        f"Could not fetch stats for {repository_name}: {error}"
                    )
            rows.append(row)
            logger.info(f"[{index}/{len(slugs)}] {row['addon_name']}")
        except AddonNotFound:
            logger.warning(f"{slug} is not available anymore, skipping.")
        except Exception as error:  # noqa: BLE001 - isolate the failing item
            failures += 1
            logger.warning(f"Could not process {slug}: {error}")
            if failures > max_failures:
                raise RuntimeError(
                    f"Aborting: {failures} add-ons failed, the AMO API contract "
                    "probably changed."
                ) from error

    if not rows:
        raise RuntimeError(
            "No add-on could be exported, refusing to write an empty table."
        )
    return rows


def write_export(
    rows: list[dict[str, object]], output: str = "export.csv"
) -> pd.DataFrame:
    """Write the rows to CSV, keeping the columns the HTML builder expects."""
    dataframe = pd.DataFrame.from_records(rows)
    dataframe = dataframe.sort_values(by=["addon_name"])
    dataframe = dataframe.astype({"average_rating": "Float64"})
    dataframe.to_csv(output, index=False)
    return dataframe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slugs",
        default="firefox-addons.txt",
        help="file containing one add-on slug per line",
    )
    parser.add_argument("--output", default="export.csv", help="path of the CSV")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="only process the first N add-ons (debugging/smoke tests)",
    )
    args = parser.parse_args(argv)

    slugs = load_addon_slugs(args.slugs)
    if args.limit > 0:
        slugs = slugs[: args.limit]
    if not slugs:
        logger.error(f"No add-on slug found in {args.slugs}.")
        return 1

    rows = collect_addons(slugs)
    dataframe = write_export(rows, args.output)
    logger.info(f"Wrote {len(dataframe)} add-ons to {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
