#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
failed=0
while IFS=$'\t' read -r limit file; do
  [[ -z "$limit" || "$limit" == \#* ]] && continue
  [[ "$limit" =~ ^[1-9][0-9]*$ && -n "$file" ]] || {
    echo 'Invalid .harness/ratchets.tsv row (expected: limit<TAB>path)' >&2; exit 1;
  }
  [[ -f "$file" ]] || { echo "Ratchet path missing: $file" >&2; exit 1; }
  lines=$(awk 'END { print NR }' "$file")
  if (( lines > limit )); then
    echo "$file: $lines lines exceeds ratchet $limit" >&2
    failed=1
  fi
done < .harness/ratchets.tsv
exit "$failed"
