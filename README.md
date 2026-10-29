# firefox-addons-table

Display available firefox add-ons in a easy-to-use and beautiful table.

Live page: <https://dbeley.github.io/firefox-addons-table/> (served from `docs/`).

## Usage

The data is regenerated every Monday by the `refresh-data` GitHub Actions
workflow, which commits the new `docs/index.html` back to `main`.

To create an export manually:

- Copy `.env.example` to `.env` and fill it with your own tokens (all optional,
  but they raise the API rate limits).
- `./update-addons-list.sh`: will export the latest list of Firefox add-ons from the NUR (https://gitlab.com/rycee/nur-expressions/-/tree/master/pkgs/firefox-addons)
- `python table_export.py`: will create `export.csv` containing the add-ons data.
  Use `--limit 5` to try it on a few add-ons only.
- `python html_builder.py`: will create `docs/index.html` with `export.csv` and `template.html`.

With Nix: `nix-shell --run 'python table_export.py'` (add `direnv allow` to load
`.env` automatically). Tests: `python -m pytest`.

## Data source

Add-on data comes from the public [AMO JSON API](https://addons.mozilla.org/api/v5/)
(`https://addons.mozilla.org/api/v5/addons/addon/<slug>/`).

The addons.mozilla.org pages themselves must not be scraped: they now serve a
bot challenge ("Client Challenge") instead of the add-on markup, which is what
broke the export in July 2025.

## External data

- Github: number of stars, last repo update
- Gitlab (gitlab.com, invent.kde.org instances): number of stars, last repo update
- Other Gitlab instances: number of stars
- Codeberg: number of stars, last repo update
- SourceHunt: last repo update
