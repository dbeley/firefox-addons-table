#!/usr/bin/env bash
# Regenerate firefox-addons.txt from the NUR add-ons list.
set -euo pipefail

URL="https://gitlab.com/rycee/nur-expressions/-/raw/master/pkgs/firefox-addons/addons.json"
TARGET="firefox-addons.txt"
# The upstream list currently holds ~520 slugs; anything far below that means
# we downloaded an error page instead of the JSON and must not overwrite a
# good list with garbage.
MINIMUM_SLUGS=100

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

curl --fail --silent --show-error --location \
  --retry 3 --retry-delay 5 --max-time 120 \
  "$URL" -o "$tmp_file"

mapfile -t slugs < <(jq -r '.[] | .slug // empty' "$tmp_file" | sort -u)

if [ "${#slugs[@]}" -lt "$MINIMUM_SLUGS" ]; then
  echo "Only ${#slugs[@]} slugs found (expected at least $MINIMUM_SLUGS), aborting." >&2
  exit 1
fi

printf '%s\n' "${slugs[@]}" > "$TARGET"
echo "Wrote ${#slugs[@]} slugs to $TARGET."
