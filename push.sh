#!/bin/sh
# 紫薇动漫源 - 一键推送（自动更新 SHA 锁版链接 + 清缓存）
# 用法: sh push.sh   （需要环境变量 SOURCES）
set -e
cd "$(dirname "$0")"
REPO="ananly/Source"
GC='!f() { echo "username=x-access-token"; echo "password=$SOURCES"; }; f'

# 1) 提交源码变更
git add -A
git -c user.name="ananly" -c user.email="ananly@users.noreply.github.com" \
    commit -m "update: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || echo "(无新变更)"
git -c credential.helper="$GC" push -u origin main

SHA=$(git rev-parse --short HEAD)

# 2) 用当前 SHA 生成配置（不可变地址，永不命中旧缓存）
python3 - "$SHA" <<'PY'
import json, sys
sha = sys.argv[1]
api = f"https://cdn.jsdelivr.net/gh/ananly/Source@{sha}/spider.py"
raw = "https://raw.githubusercontent.com/ananly/Source/main/spider.py"
for f, a in [("anime-github.json", api), ("anime.json", raw)]:
    d = json.load(open(f, encoding="utf-8"))
    d["sites"][0]["api"] = a
    d["sites"][0]["name"] = "紫薇动漫"
    json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("api =>", api)
PY

# 3) 提交配置并推送
git add -A
git -c user.name="ananly" -c user.email="ananly@users.noreply.github.com" \
    commit -m "config: 锁定 $SHA" 2>/dev/null || true
git -c credential.helper="$GC" push -u origin main

# 4) 清 jsDelivr 缓存
for f in spider.py anime.json anime-github.json README.md; do
    curl -s --max-time 15 "https://purge.jsdelivr.net/gh/${REPO}@main/$f" >/dev/null 2>&1 || true
done

echo "完成 SHA=$SHA"
echo "配置(CDN):  https://cdn.jsdelivr.net/gh/${REPO}@main/anime-github.json"
echo "配置(raw):  https://raw.githubusercontent.com/${REPO}/main/anime.json"
