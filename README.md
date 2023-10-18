# firefox-addons-table

Display available firefox add-ons in a easy-to-use and beautiful table.

## Usage

The data should be re-generated every monday.

If you want to manually create an export:

- Copy `.env.example` to `.env` and fill it with your own tokens.
- `./update-addons-list.sh`: will export the latest list of Firefox add-ons from the NUR (https://gitlab.com/rycee/nur-expressions/-/tree/master/pkgs/firefox-addons)
- `python table_export.py`: will create `export.csv` containing F-Droid apps data.
- `python template_export.py`: will create `docs/index.html` with `export.csv` and `template.html`.

## External data

- Github: number of stars, last repo update
- Gitlab (gitlab.com, invent.kde.org instances): number of stars, last repo update
- Other Gitlab instances: number of stars
- Codeberg: number of stars, last repo update
- SourceHunt: last repo update
