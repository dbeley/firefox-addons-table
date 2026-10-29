"""Fetch stars/last-update for the repositories linked from an add-on."""

import logging
import time

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from github import Github
from github.GithubException import GithubException, RateLimitExceededException
from gitlab import Gitlab
from gitlab.exceptions import GitlabError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Never let a single slow host stall the weekly run.
REQUEST_TIMEOUT = (10, 20)
# Cap the rate-limit nap: an unreachable reset time must not hang the job.
MAX_RATE_LIMIT_SLEEP = 900

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Shared session with retries, used for every plain HTTP call."""
    global _session
    if _session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": "firefox-addons-table"})
        _session = session
    return _session


def _parse_date(value: str | None) -> int | None:
    """Parse the leading ``YYYY-MM-DD`` of a timestamp into a POSIX timestamp."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        parsed = datetime.strptime(value[0:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(parsed.timestamp())


def _sleep_until_rate_limit_resets(g: Github) -> None:
    try:
        reset = g.get_rate_limit().core.reset
        sleep_time = reset.timestamp() - time.time() + 10
    except Exception as error:  # noqa: BLE001 - best effort, only slows us down
        logger.warning(f"Could not read the GitHub rate limit reset time: {error}")
        sleep_time = 60
    sleep_time = max(1, min(sleep_time, MAX_RATE_LIMIT_SLEEP))
    logger.warning(f"GitHub rate limit hit, sleeping for {sleep_time:.0f} seconds.")
    time.sleep(sleep_time)


def get_github_repository_data(g: Github, repository_name: str) -> dict[str, int]:
    """Return stars and last update for a GitHub repository.

    Every ``GithubException`` is handled: a bare 404, a 451 (repository blocked
    after a DMCA takedown) or a 403 must skip that add-on, not abort the run.
    """
    try:
        repo = g.get_repo(repository_name)
    except RateLimitExceededException:
        _sleep_until_rate_limit_resets(g)
        try:
            repo = g.get_repo(repository_name)
        except GithubException as error:
            logger.warning(
                f"Repository {repository_name} unavailable on Github: {error}"
            )
            return {}
    except GithubException as error:
        logger.warning(f"Repository {repository_name} unavailable on Github: {error}")
        return {}
    return {
        "repository_stars_count": repo.stargazers_count,
        "repository_last_update": int(repo.updated_at.timestamp()),
    }


def get_gitlab_repository_data(gl: Gitlab, repository_name: str) -> dict[str, int]:
    """Return stars and last update for a GitLab project.

    ``GitlabError`` is the base class: 404s, rate limits and auth failures all
    end up there and must not abort the run.
    """
    try:
        repo = gl.projects.get(repository_name)
        commits = repo.commits.list(per_page=1, get_all=False)
    except GitlabError as error:
        logger.warning(f"Repository {repository_name} unavailable on Gitlab: {error}")
        return {}
    result: dict[str, int] = {"repository_stars_count": repo.star_count}
    if commits:
        last_update = _parse_date(getattr(commits[0], "committed_date", None))
        if last_update is not None:
            result["repository_last_update"] = last_update
    return result


def get_gitlab_repository_data_with_webscraping(repository_url: str) -> dict[str, int]:
    """Scrape the star count on GitLab instances without a public API token."""
    try:
        response = get_session().get(repository_url, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(response.content, "lxml")
        star_element = soup.select("a.gl-button.star-count")
        if not star_element:
            raise ValueError("no star count element found")
        return {"repository_stars_count": int(star_element[0].text.strip())}
    except Exception as e:
        logger.warning(f"Couldn't scrape {repository_url}: {e}")
        return {}


def get_codeberg_repository_data(repository_name: str) -> dict[str, int]:
    """Return stars and last update from the Codeberg (Forgejo) API."""
    try:
        response = get_session().get(
            f"https://codeberg.org/api/v1/repos/{repository_name}",
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            logger.warning(
                f"Repository {repository_name} unavailable on Codeberg "
                f"(HTTP {response.status_code})."
            )
            return {}
        payload = response.json()
    except Exception as error:  # noqa: BLE001 - one bad host must not abort
        logger.warning(f"Couldn't query Codeberg for {repository_name}: {error}")
        return {}
    result: dict[str, int] = {"repository_stars_count": payload.get("stars_count")}
    last_update = _parse_date(payload.get("updated_at"))
    if last_update is not None:
        result["repository_last_update"] = last_update
    return result


def get_sourcehunt_repository_data_with_webscraping(
    repository_url: str,
) -> dict[str, int]:
    """Scrape the last commit date on sourcehut (no starring available)."""
    try:
        response = get_session().get(repository_url, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(response.content, "lxml")
        commit_list = soup.select("small.pull-right a span")
        if len(commit_list) >= 1:
            last_update = _parse_date(commit_list[0].get("title"))
            if last_update is not None:
                return {
                    # sourcehut doesn't support starring projects
                    "repository_stars_count": 0,
                    "repository_last_update": last_update,
                }
        return {}
    except Exception as e:
        logger.warning(f"Couldn't scrape {repository_url}: {e}")
        return {}
