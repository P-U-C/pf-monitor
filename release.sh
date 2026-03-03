#!/usr/bin/env bash
# release.sh — Bump version, tag, and push
# Usage: ./release.sh 1.1.0

set -euo pipefail

NEW_VERSION="${1:-}"
if [[ -z "$NEW_VERSION" ]]; then
    echo "Usage: ./release.sh <version>"
    echo "Example: ./release.sh 1.1.0"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OLD_VERSION="$(cat VERSION | tr -d '[:space:]')"
TODAY="$(date -u +"%Y-%m-%d")"

echo "Releasing $OLD_VERSION -> $NEW_VERSION"

# Update VERSION
echo "$NEW_VERSION" > VERSION

# Prepend CHANGELOG entry
CHANGELOG_ENTRY="## [$NEW_VERSION] — $TODAY

### Changed
- (fill in changes)

---

"
# Insert after the first ---
awk -v entry="$CHANGELOG_ENTRY" '
    /^---$/ && !inserted { print; printf "%s", entry; inserted=1; next }
    { print }
' CHANGELOG.md > CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md

echo "Updated CHANGELOG.md — add your notes for [$NEW_VERSION] before committing"

# Commit + tag
git add VERSION CHANGELOG.md
git commit -m "chore: release v${NEW_VERSION}"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"

echo ""
echo "Done. Push with:"
echo "  git push origin main --tags"
