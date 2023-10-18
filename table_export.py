import logging
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

import pandas as pd
from github import Github
from gitlab import Gitlab

from utils import (
    get_codeberg_repository_data,
    get_github_repository_data,
    get_gitlab_repository_data,
    get_gitlab_repository_data_with_webscraping,
    get_sourcehunt_repository_data_with_webscraping,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s :: %(message)s")
logger = logging.getLogger(__name__)

REPOSITORY_APIS = {
    "github.com": Github(os.environ.get("GITHUB_TOKEN")),
    "gitlab.com": Gitlab(private_token=os.environ.get("GILAB_TOKEN")),
    "invent.kde.org": Gitlab(
        url="https://invent.kde.org", private_token=os.environ.get("GILAB_KDE_TOKEN")
    ),
}


def _extract_repository_name(repository: str, repository_domain: str) -> str:
    repository_name = (
        repository.split("://")[-1].split(f"{repository_domain}/")[-1].strip("/")
    )
    if repository_name.count("/") > 1:
        repository_name = (
            repository_name.split("/")[0] + "/" + repository_name.split("/")[1]
        )
    return repository_name


def _get_repository_stats(repository: str, repository_domain: str) -> dict[str, int]:
    if not repository:
        return {}
    repository_name = _extract_repository_name(repository, repository_domain)
    match repository_domain:
        case "github.com":
            return get_github_repository_data(
                REPOSITORY_APIS["github.com"], repository_name
            )
        case "codeberg.org":
            return get_codeberg_repository_data(repository_name)
        case "gitlab.com":
            return get_gitlab_repository_data(
                REPOSITORY_APIS["gitlab.com"], repository_name
            )
        case "invent.kde.org":
            return get_gitlab_repository_data(
                REPOSITORY_APIS["invent.kde.org"], repository_name
            )
        case "gitlab.gnome.org" | "source.puri.sm" | "gitlab.manjaro.org":
            return get_gitlab_repository_data_with_webscraping(repository)
        case "sr.ht" | "git.sr.ht":
            return get_sourcehunt_repository_data_with_webscraping(repository)
    return {}


with open("firefox-addons.txt", "r") as f:
    addons = [line.strip() for line in f.readlines()]

list_data = []
for index, addon_id in enumerate(addons, 1):
    url = f"https://addons.mozilla.org/en-US/firefox/addon/{addon_id}/"
    soup = BeautifulSoup(requests.get(url).content, "lxml")
    if soup.select("div.Card-header-text") and soup.select("div.Card-header-text")[
        0
    ].text.startswith("Oops"):
        logger.warning(f"{addon_id} is not available anymore, skipping.")
        continue
    user = soup.select("h1.AddonTitle a")[0].text
    user_link = "https://addons.mozilla.org" + soup.select("h1.AddonTitle a")[0]["href"]
    soup.select("h1.AddonTitle span")[0].extract()
    addon_name = soup.select("h1.AddonTitle")[0].text
    print(addon_name)
    addon_icon = (
        soup.select("img.Addon-icon-image")[0]["src"].split(",")[0]
        if soup.select("img.Addon-icon-image")
        else ""
    )
    number_users = (
        soup.select("div.AddonMeta-overallRating dl")[0]
        .find("dd")
        .text.replace(",", "")
    )
    number_reviews = (
        soup.select("div.AddonMeta-overallRating dl")[1]
        .find("dd")
        .text.replace(",", "")
    )
    average_rating_element = (
        soup.select("div.AddonMeta-overallRating dl")[2]
        .find("dd")
        .text.replace(",", "")
    )
    average_rating = (
        average_rating_element.split(" ")[1]
        if not average_rating_element.startswith("There are no ratings")
        else None
    )

    addon_summary = soup.select("p.Addon-summary")[0].text
    addon_version = soup.select("dd.AddonMoreInfo-version")[0].text
    addon_size = soup.select("dd.AddonMoreInfo-filesize")[0].text
    addon_last_update = soup.select("dd.AddonMoreInfo-last-updated")[0].text
    addon_license = soup.select("dd.AddonMoreInfo-license")[0].text

    repo_link = (
        soup.select("a.AddonMoreInfo-homepage-link")[0]["href"]
        if soup.select("a.AddonMoreInfo-homepage-link")
        else ""
    )
    repo_domain = None
    repo_stats = {}
    if repo_link:
        repo_link = unquote("http" + repo_link.split("http")[-1])
        repo_domain = repo_link.split("://")[1].split("/")[0]
        repo_stats = _get_repository_stats(repo_link, repo_domain)

    list_data.append(
        {
            "url": url,
            "addon_name": addon_name,
            "addon_icon": addon_icon,
            "user": user,
            "user_link": user_link,
            "number_users": number_users,
            "number_reviews": number_reviews,
            "average_rating": average_rating,
            "repository_link": repo_link,
            "repository_domain": repo_domain,
            "addon_summary": addon_summary,
            "addon_version": addon_version,
            "addon_size": addon_size,
            "addon_last_update": addon_last_update,
            "addon_license": addon_license,
            **repo_stats,
        }
    )

df = pd.DataFrame.from_records(list_data)
df = df.sort_values(by=["addon_name"])
df = df.astype(
    {
        "average_rating": "Float64",
    }
)
df.to_csv("export.csv", index=False)
