"""Render docs/index.html from export.csv and template.html."""

import re
from datetime import datetime
from html import escape
from string import Template

import pandas as pd

HEADER = (
    "<thead>\n"
    "<tr>\n"
    "<th>Name</th>\n"
    "<th>Number Users</th>\n"
    "<th>Number Reviews</th>\n"
    "<th>Average Rating</th>\n"
    "<th>Last Update</th>\n"
    "<th>Categories</th>\n"
    "<th>Summary</th>\n"
    "<th>Version</th>\n"
    "<th>Size</th>\n"
    "<th>License</th>\n"
    "<th>Homepage</th>\n"
    "<th>Repository Stars Count</th>\n"
    "</tr>\n"
    "</thead>\n"
)

_DATE_IN_LABEL = re.compile(r"\(([A-Z][a-z]{2}) (\d{1,2}), (\d{4})\)")


def read_template(file: str) -> Template:
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    return Template(content)


def load_export(file: str = "export.csv") -> pd.DataFrame:
    """Read the CSV as strings so no value is reformatted or turned into NaN."""
    return pd.read_csv(file, dtype=str, keep_default_na=False)


def sort_key_from_label(label: str) -> str:
    """Extract the ISO date of a "3 months ago (Sep 8, 2026)" label.

    Used as ``data-order`` so the Last Update column sorts chronologically
    instead of alphabetically ("a year ago" < "2 months ago").
    """
    match = _DATE_IN_LABEL.search(label or "")
    if not match:
        return ""
    try:
        parsed = datetime.strptime(" ".join(match.groups()), "%b %d %Y")
    except ValueError:
        return ""
    return parsed.strftime("%Y-%m-%d")


def build_table(dataframe: pd.DataFrame) -> str:
    rows = ["<tbody>"]
    for _, row in dataframe.iterrows():
        icon = (
            f"<img loading='lazy' width='30' src='{escape(row['addon_icon'])}' alt=''/>\n"
            if row["addon_icon"]
            else ""
        )
        name = f"<a href='{escape(row['url'])}'>{escape(row['addon_name'])}</a></td>"
        repository_link = (
            f"<a href='{escape(row['repository_link'])}'>"
            f"{escape(row['repository_link'])}</a>"
            if row["repository_link"]
            else ""
        )
        last_update = escape(row["addon_last_update"])
        order = sort_key_from_label(row["addon_last_update"])
        last_update_cell = (
            f"<td data-order='{order}'>{last_update}</td>"
            if order
            else f"<td>{last_update}</td>"
        )
        rows.append(
            "<tr>\n"
            f"<td>{icon}{name}\n"
            f"<td>{escape(row['number_users'])}</td>\n"
            f"<td>{escape(row['number_reviews'])}</td>\n"
            f"<td>{escape(row['average_rating'])}</td>\n"
            f"{last_update_cell}\n"
            f"<td>{escape(row['addon_categories'])}</td>\n"
            f"<td>{escape(row['addon_summary'])}</td>\n"
            f"<td>{escape(row['addon_version'])}</td>\n"
            f"<td>{escape(row['addon_size'])}</td>\n"
            f"<td>{escape(row['addon_license'])}</td>\n"
            f"<td>{repository_link}</td>\n"
            f"<td>{escape(row['repository_stars_count'])}</td>\n"
            "</tr>"
        )
    rows.append("</tbody>")
    return "\n".join(rows) + "\n"


def main() -> None:
    dataframe = load_export("export.csv")
    formatted_message = read_template("template.html").safe_substitute(
        {
            "date_update": datetime.today().strftime("%Y-%m-%d"),
            "header": HEADER,
            "table_data": build_table(dataframe),
        }
    )
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(formatted_message)


if __name__ == "__main__":
    main()
