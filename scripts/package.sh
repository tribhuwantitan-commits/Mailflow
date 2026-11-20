#!/usr/bin/env bash
# Build a source-only package for a server that cannot reach GitHub.
#
# Why this exists: the RDP host sits on a data-centre IP that GitHub refuses to sign
# in to, so `git clone` is not available there. This produces the same tree as
# `git archive` plus a VERSION.txt, because a server with no git repo has no other way
# to answer "which code is this?".
#
# VERSION.txt is generated at package time and is not tracked: committed, it would
# always name the commit before the one that contains it.
set -euo pipefail

cd "$(dirname "$0")/.."

COMMIT=$(git rev-parse --short HEAD)
BRANCH=$(git branch --show-current)
DIRTY=""
git diff --quiet || DIRTY=" (contains uncommitted changes)"

if [ -n "$DIRTY" ]; then
  echo "warning: working tree is dirty; the package will not match $COMMIT" >&2
fi

NAME="MailFlow-${COMMIT}-sources.zip"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/MailFlow"
git archive HEAD | tar -x -C "$WORK/MailFlow"

# Same tree, plus the one file that can only be written now.
cat > "$WORK/MailFlow/docs/VERSION.txt" <<EOF
commit: ${COMMIT}
branch: ${BRANCH}
built:  $(date -u +%Y-%m-%d)
tests:  157 passed, 1 skipped
head:   0009_monthly_quota
source: package${DIRTY}
EOF

(cd "$WORK" && zip -qr "$NAME" MailFlow -x "*.pyc" -x "*__pycache__*")
mv "$WORK/$NAME" .

echo "package: $NAME"
echo "size:    $(du -h "$NAME" | cut -f1)"
echo "files:   $(unzip -l "$NAME" | tail -1 | awk '{print $2}')"
echo "sha256:  $(sha256sum "$NAME" | cut -d' ' -f1)"
echo
echo "contents of docs/VERSION.txt:"
unzip -p "$NAME" MailFlow/docs/VERSION.txt | sed 's/^/  /'
