"""Tests for the HTML generation layer."""

import pandas as pd

from html_builder import build_table, sort_key_from_label


def test_sort_key_from_label_extracts_the_iso_date():
    assert sort_key_from_label("3 months ago (Sep 8, 2026)") == "2026-09-08"
    assert sort_key_from_label("a year ago (Feb 27, 2025)") == "2025-02-27"
    assert sort_key_from_label("") == ""
    assert sort_key_from_label("not a date") == ""


def test_build_table_escapes_and_orders_rows():
    dataframe = pd.DataFrame(
        [
            {
                "url": "https://addons.mozilla.org/fr/firefox/addon/x/?a=1&b=2",
                "addon_name": "Foo & Bar <script>",
                "addon_icon": "",
                "number_users": "12",
                "number_reviews": "3",
                "average_rating": "4.5",
                "addon_last_update": "2 months ago (Aug 1, 2026)",
                "addon_categories": "Other",
                "addon_summary": "A <b>summary</b>",
                "addon_version": "1.0",
                "addon_size": "1.00 MB",
                "addon_license": "MIT",
                "repository_link": "",
                "repository_stars_count": "",
            }
        ]
    )
    table = build_table(dataframe)
    assert "Foo &amp; Bar &lt;script&gt;" in table
    assert "A &lt;b&gt;summary&lt;/b&gt;" in table
    assert "data-order='2026-08-01'" in table
    # No empty icon tag and no empty link.
    assert "<img" not in table
    assert "<a href=''>" not in table
