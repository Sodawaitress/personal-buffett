#!/bin/sh
# Deploy to fly.io from ZFS volume
# Usage: sh deploy/fly_deploy.sh
set -e

STAGING=/tmp/pbc-deploy

rm -rf "$STAGING"
rsync -a \
  --exclude='._*' \
  --exclude='.git' \
  --exclude='/data/' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='notebooks' \
  --exclude='.DS_Store' \
  "$(dirname "$0")/../" "$STAGING/"

echo "✓ staged to $STAGING ($(du -sh "$STAGING" | cut -f1))"
cd "$STAGING"
fly deploy --ha=false
