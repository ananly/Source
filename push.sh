#!/bin/sh
# 推送专属动漫源到 ananly/Source
# 用法: sh push.sh   （GITHUB_TOKEN 由环境变量提供）
set -e
cd "$(dirname "$0")"
git add -A
git -c user.name="ananly" -c user.email="ananly@users.noreply.github.com" \
    commit -m "update: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || echo "(无新变更)"
git -c credential.helper='!f() { echo "username=x-access-token"; echo "password=$GITHUB_TOKEN"; }; f' \
    push -u origin main
echo "推送完成: https://github.com/ananly/Source"
