#!/bin/sh
# 紫薇动漫源 - 一键推送 + 自动清 jsDelivr 缓存
# 用法: sh push.sh   （需要环境变量 SOURCES）
set -e
cd "$(dirname "$0")"
REPO="ananly/Source"

git add -A
git -c user.name="ananly" -c user.email="ananly@users.noreply.github.com" \
    commit -m "update: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || echo "(无新变更)"

git -c credential.helper='!f() { echo "username=x-access-token"; echo "password=$SOURCES"; }; f' \
    push -u origin main

echo "== 清理 jsDelivr 缓存 =="
for f in spider.py anime.json anime-github.json anime-local.json anime-min.json README.md; do
    printf "   %-20s " "$f"
    curl -s --max-time 20 "https://purge.jsdelivr.net/gh/${REPO}@main/$f" >/dev/null && echo "purged" || echo "skip"
done

echo "完成: https://github.com/${REPO}"
echo "配置: https://cdn.jsdelivr.net/gh/${REPO}@main/anime-github.json"
