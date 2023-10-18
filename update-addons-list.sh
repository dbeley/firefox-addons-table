#!/usr/bin/env bash
curl "https://gitlab.com/rycee/nur-expressions/-/raw/master/pkgs/firefox-addons/addons.json" | jq -r '.[].slug' > firefox-addons.txt
