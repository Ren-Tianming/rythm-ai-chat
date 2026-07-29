#!/bin/sh
set -eu

curl --fail --silent --show-error \
  --resolve chat.rhythmusic.site:443:127.0.0.1 \
  https://chat.rhythmusic.site/api/v1/health/ready
