from datetime import datetime
from string import Template

import pandas as pd


def read_template(file: str) -> Template:
    with open(file, "r") as f:
        content = f.read()
    return Template(content)


df = pd.read_csv("export.csv")
df = df.fillna(
    {
        "addon_icon": "",
        "average_rating": "",
        "number_reviews": "",
        "number_users": "",
        "repo_link": "",
        "repository_last_update": "",
        "repository_stars_count": "",
    }
)

header = (
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
    "<th>Repository Last Update</th>\n"
    "</tr>\n"
    "</thead>\n"
)

table_data = "<tbody>\n"
for index, row in df.iterrows():
    name = f"<a href='{row['url']}'>{row['addon_name']}</a></td>"
    repository_link = (
        f"<a href='{row['repository_link']}'>{row['repository_link']}</a>"
        if not pd.isnull(row["repository_link"])
        else ""
    )
    table_data += (
        "<tr>\n"
        "<td>"
        f"<img loading='lazy' width='30' src='{row['addon_icon']}' alt=''/>"
        "\n"
        f"{name}"
        "\n"
        f"<td>{row['number_users']}</td>"
        "\n"
        f"<td>{row['number_reviews']}</td>"
        "\n"
        f"<td>{row['average_rating']}</td>"
        "\n"
        f"<td>{row['addon_last_update']}</td>"
        "\n"
        f"<td>{row['addon_categories']}</td>"
        "\n"
        f"<td>{row['addon_summary']}</td>"
        "\n"
        f"<td>{row['addon_version']}</td>"
        "\n"
        f"<td>{row['addon_size']}</td>"
        "\n"
        f"<td>{row['addon_license']}</td>"
        "\n"
        f"<td>{repository_link}</td>"
        "\n"
        f"<td>{row['repository_stars_count']}</td>"
        "\n"
        f"<td>{row['repository_last_update']}</td>"
        "\n"
        "</tr>\n"
    )
table_data += "</tbody>\n"

date_update = datetime.today().strftime("%Y-%m-%d")

formatted_message = read_template("template.html").safe_substitute(
    {"date_update": date_update, "header": header, "table_data": table_data}
)
with open("docs/index.html", "w") as f:
    f.write(formatted_message)
