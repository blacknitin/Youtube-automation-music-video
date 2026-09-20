#!/usr/bin/env bash
# Push SongForge to github.com/blacknitin/Youtube-automation-music-video
# Snapshot-proof: re-creates .git if dropped; commits current tree on top of remote main.
# Usage: GH_TOKEN=github_pat_xxx bash scripts/github_push.sh ["commit message"]
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GH_TOKEN:?export GH_TOKEN=<fine-grained PAT with Contents: Read & Write>}"
MSG="${1:-Sync from sandbox $(date -u +'%Y-%m-%d %H:%M UTC')}"
REPO="blacknitin/Youtube-automation-music-video"

if [ ! -d .git ]; then
  git init -q
  git config user.name blacknitin
  git config user.email "102011029+blacknitin@users.noreply.github.com"
fi
export GIT_TERMINAL_PROMPT=0
git remote remove origin 2>/dev/null || true
git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git"
git fetch -q origin main 2>/dev/null || true

git add -A
tree=$(git write-tree)
parent=""
git rev-parse -q --verify FETCH_HEAD >/dev/null 2>&1 && parent="-p FETCH_HEAD"
commit=$(git commit-tree "$tree" $parent -m "$MSG")
git update-ref refs/heads/main "$commit"
git push -q -u origin main
git remote remove origin
echo "pushed $(git rev-parse --short main) -> https://github.com/${REPO}"
