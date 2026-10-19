#coding=utf-8
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox / 影视仓  Python源 —— 专属动漫
聚合多个 MacCMS 动漫资源站的动漫分类，原生卡片体验
特点：纯动漫内容 / 新番更新快 / 无网页验证 / m3u8 直链播放
"""

import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object


class Spider(BaseSpider):
    def getName(self):
        return "专属动漫"

    def init(self, extend=""):
        self.ua = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/134.0.0.0 Mobile Safari/537.36")
        self.headers = {"User-Agent": self.ua, "Referer": "https://www.baidu.com/"}
        self.cache = {}
        self.sess = requests.Session()
        self.sess.headers.update(self.headers)
        self.sess.verify = False

        # 资源站（中文站名 + 主备双域名自动切换）
        # (中文站名, [主域名, 备域名...], 日韩动漫tid, 国产动漫tid, 欧美动漫tid, 动漫电影tid)
        # 站点排序 = 线路优先级（用户实测：量子/360/暴风/最大/ikun 无广告，索尼/如意/速播有广告）
        # 无广告站排前面；有广告站兜底
        self.sites = [
            ("量子资源", ["https://cj.lziapi.com"], 30, 29, 31, ""),     # 1080x452 无广告✅
            ("360资源", ["https://360zy.com", "https://www.360zy.tv"], 40, 38, 39, ""),
            ("暴风资源", ["https://bfzyapi.com"], 41, 40, 42, ""),
            ("最大资源", ["https://api.zuidapi.com"], 30, 29, 31, 63),
            ("ikun资源", ["https://ikunzyapi.com"], 37, 35, 36, ""),     # 真1080P 无广告✅
            ("速播资源", ["https://subozy.com"], 25, 24, 26, 13),        # 有水印⚠️
            ("索尼资源", ["https://suoniapi.com"], 30, 29, 31, ""),      # 开屏广告⚠️
            ("如意资源", ["https://cj.rycjapi.com"], 30, 29, 31, ""),    # 片前广告⚠️
        ]
        self.timeout = 4
        self._api_ok = {}  # 站名 -> 当前可用的 api 基址（会话内缓存）

    def _api_of(self, name):
        """返回该站当前可用的 api 基址；主域名失败自动换备用（并发探测，会话缓存）"""
        if name in self._api_ok:
            return self._api_ok[name]
        site = next((s for s in self.sites if s[0] == name), None)
        if not site:
            return ""
        api = site[1][0] + "/api.php/provide/vod"
        self._api_ok[name] = api
        return api

    def _warm_apis(self):
        """并发探测全部站点可用 API（只跑一次，结果缓存）"""
        if self.cache.get("apis_warmed"):
            return
        def probe(site):
            name, bases = site[0], site[1]
            for base in bases:
                api = base + "/api.php/provide/vod"
                try:
                    r = self.sess.get(api, params={"ac": "list"}, timeout=3)
                    if r.status_code == 200 and r.text.strip().startswith("{"):
                        return name, api
                except Exception:
                    continue
            return name, bases[0] + "/api.php/provide/vod"
        try:
            results = self._parallel(probe, [(s,) for s in self.sites], budget=4.0)
            for res in results:
                if res:
                    self._api_ok[res[0]] = res[1]
        except Exception:
            pass
        self.cache["apis_warmed"] = True

    # ---------- 基础 ----------
    def _fetch(self, api, params, retry_alt=True):
        try:
            r = self.sess.get(api, params=params, timeout=self.timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        # 主域名失败 → 找该站备用域名重试
        if retry_alt:
            base = api.split("/api.php")[0]
            site = next((s for s in self.sites if base in s[1]), None)
            if site:
                for b in site[1]:
                    alt = b + "/api.php/provide/vod"
                    if alt == api:
                        continue
                    try:
                        r = self.sess.get(alt, params=params, timeout=self.timeout)
                        if r.status_code == 200:
                            self._api_ok[site[0]] = alt  # 记住可用域名
                            return r.json()
                    except Exception:
                        continue
        return {}

    def _parallel(self, fn, args_list, budget=2.2):
        """并发执行，总预算 budget 秒；到点未完成的返回 None 占位"""
        out = [None] * len(args_list)
        ex = None
        try:
            from concurrent.futures import wait as _wait, ThreadPoolExecutor as _TPE
            ex = _TPE(max_workers=min(8, len(args_list)))
            futs = {ex.submit(fn, *a): i for i, a in enumerate(args_list)}
            done, pending = _wait(futs, timeout=budget)
            for f in done:
                try:
                    out[futs[f]] = f.result()
                except Exception:
                    out[futs[f]] = None
            # 未完成的再给 0.6s 短等待，仍超时则放弃
            if pending:
                done2, _ = _wait(pending, timeout=0.6)
                for f in done2:
                    try:
                        out[futs[f]] = f.result()
                    except Exception:
                        out[futs[f]] = None
        except Exception:
            pass
        finally:
            if ex is not None:
                try:
                    ex.shutdown(wait=False)
                except Exception:
                    pass
        return out

    @staticmethod
    def _norm(s):
        return re.sub(r'[\s\u3000()（）\[\]【】:：·]+', '', s or '')

    @staticmethod
    def _clean_query(q):
        """去掉尾部年份/季数，资源站一般按主名收录"""
        q = (q or "").strip()
        q = re.sub(r'[\s\-_]*(19|20)\d{2}\s*$', '', q)
        q = re.sub(r'[\s\-_]*第[一二三四五六七八九十\d]+季\s*$', '', q)
        q = re.sub(r'[\s\-_]*(S\d{1,2}|Season\s*\d+)\s*$', '', q, flags=re.I)
        return q.strip() or (q or "")

    # ---------- 首页分类 ----------
    def homeContent(self, filter):
        classes = [
            {"type_id": "today", "type_name": "📅 今日追番"},
            {"type_id": "hot", "type_name": "👑 热播榜"},
            {"type_id": "new", "type_name": "🔥 最新收录"},
            {"type_id": "cn", "type_name": "🇨🇳 国产动漫"},
            {"type_id": "jp", "type_name": "🌸 樱花动漫"},
            {"type_id": "us", "type_name": "🇺🇸 欧美动漫"},
            {"type_id": "movie", "type_name": "🎬 动漫剧场"},
        ]
        return {"class": classes, "filters": {}, "list": []}

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        self._warm_apis()
        jobs = []
        if tid == "today":
            # 今日追番：8 站 × 日漫/国漫 × 24h。并发足够快，全量拉取
            for name, bases, t_jp, t_cn, t_us, t_mv in self.sites[:6]:
                api = self._api_of(name)
                if t_jp:
                    jobs.append((name, api, {"ac": "detail", "t": t_jp, "h": 24, "pg": page}))
                if t_cn and t_cn != t_jp:
                    jobs.append((name, api, {"ac": "detail", "t": t_cn, "h": 24, "pg": page}))
        else:
            idx_map = {"jp": 2, "cn": 3, "us": 4, "movie": 5}
            idx = idx_map.get(tid)
            if idx is not None:
                for name, bases, *tids in self.sites[:6]:
                    t = tids[idx - 2]
                    if t:
                        jobs.append((name, self._api_of(name), {"ac": "detail", "t": t, "pg": page}))
            elif tid == "new":
                for name, bases, *_ in self.sites[:6]:
                    jobs.append((name, self._api_of(name), {"ac": "detail", "pg": page, "h": 24}))
            elif tid == "hot":
                for name, bases, *_ in self.sites[:5]:
                    jobs.append((name, self._api_of(name), {"ac": "detail", "pg": page}))

        def one(name, api, params):
            d = self._fetch(api, params)
            return name, d.get("list") or []

        results = self._parallel(one, jobs)
        merged, seen = [], {}
        for res in results:
            if not res:
                continue
            name, lst = res
            if not isinstance(lst, list):
                continue
            for it in lst:
                if not isinstance(it, dict):
                    continue
                tn = it.get("type_name") or ""
                # 今日更新：严格只留动漫；其他分类本来已是动漫分类不用过滤
                if tid == "today":
                    if not any(w in tn for w in ("动漫", "动画")):
                        continue
                elif tid in ("new", "hot"):
                    if not any(w in tn for w in ("动漫", "动画")):
                        continue
                vn = it.get("vod_name") or ""
                key = self._norm(vn)
                if not key:
                    continue
                eps = 0
                try:
                    eps = len((it.get("vod_play_url") or "").split("$$$")[0].split("#"))
                except Exception:
                    pass
                old = seen.get(key)
                if old is None:
                    it = dict(it)
                    it["_src"] = name
                    it["_eps"] = eps
                    seen[key] = it
                    merged.append(it)
                else:
                    # 同名取集数多的
                    if eps > old.get("_eps", 0):
                        it = dict(it)
                        it["_src"] = name
                        it["_eps"] = eps
                        merged[merged.index(old)] = it
                        seen[key] = it
        # 按更新时间排（有 vod_time 就用）
        def sort_key(x):
            return x.get("vod_time") or x.get("vod_pubdate") or ""
        merged.sort(key=sort_key, reverse=True)
        # 输出标准字段
        out = []
        name_map = self.cache.setdefault("names", {})
        for it in merged[:40]:
            _vid = (it.get("_src") or "") + "|" + str(it.get("vod_id", ""))
            name_map[_vid] = it.get("vod_name") or ""
            out.append({
                "vod_id": _vid,
                "vod_name": it.get("vod_name", ""),
                "vod_pic": it.get("vod_pic", ""),
                "vod_remarks": it.get("vod_remarks", ""),
            })
        # 空结果兜底：放宽超时重试一次（网络抖动时不至于白屏）
        if not out:
            self.timeout = 6
            def one2(name, api, params):
                dd = self._fetch(api, params, retry_alt=False)
                return name, dd.get("list") or []
            res2 = self._parallel(one2, jobs, budget=3.0)
            for res in res2:
                if not res:
                    continue
                name, lst2 = res
                if not isinstance(lst2, list):
                    continue
                for it in lst2:
                    if not isinstance(it, dict):
                        continue
                    tn = it.get("type_name") or ""
                    if tid in ("today", "new", "hot") and not any(w in tn for w in ("动漫", "动画")):
                        continue
                    out.append({
                        "vod_id": name + "|" + str(it.get("vod_id", "")),
                        "vod_name": it.get("vod_name", ""),
                        "vod_pic": it.get("vod_pic", ""),
                        "vod_remarks": it.get("vod_remarks", ""),
                    })
                    if len(out) >= 40:
                        break
                if len(out) >= 40:
                    break
            self.timeout = 4
        pagecount = 99 if tid != "movie" else 50
        return {"page": page, "pagecount": pagecount, "limit": len(out), "total": pagecount * 40, "list": out}

    # ---------- 详情 ----------
    # 线路质量分（用户实测：无广告站优先，分越低越靠前）
    SITE_RANK = {"量子资源": 0, "360资源": 1, "暴风资源": 2, "最大资源": 3,
                 "ikun资源": 4, "速播资源": 8, "索尼资源": 9, "如意资源": 10}
    CODE2CN = {"lzm3u8": "量子·高清✅", "liangzi": "量子✅", "bfzym3u8": "暴风✅",
               "zuidam3u8": "最大✅", "subm3u8": "速播⚠️", "subyun": "速播云⚠️",
               "jsm3u8": "极速⚠️", "jsyun": "极速云⚠️",
               "360zy": "360✅", "mym3u8": "猫眼", "ikm3u8": "ikun✅1080",
               "snm3u8": "索尼1080⚠️", "rym3u8": "如意⚠️", "ruyi": "如意备⚠️"}

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, list) else ids
        ck = "detail:" + str(raw)
        if ck in self.cache:
            return self.cache[ck]
        src, _, vid = str(raw).partition("|")
        # 拿到番名后跨站聚合：用番名查所有站，合并线路
        first_api = self._api_of(src)
        # 列表阶段已记住番名 → 跨站查询与来源站详情并行发起，省一半时间
        cached_name = (self.cache.get("names") or {}).get(str(raw), "")
        name_clean_pre = self._clean_query(cached_name) if cached_name else ""
        agg_pool = None
        if name_clean_pre:
            try:
                from concurrent.futures import ThreadPoolExecutor
                agg_pool = ThreadPoolExecutor(max_workers=1)
                pre_futs = []
                pre_jobs = []
                for name, bases, *_ in self.sites:
                    if name == src or self.SITE_RANK.get(name, 50) > 5:
                        continue
                    pre_jobs.append((name, self._api_of(name), {"ac": "detail", "wd": name_clean_pre}))
                agg_fut = agg_pool.submit(self._parallel, lambda n, a, p: (n, (self._fetch(a, p).get("list") or [])), pre_jobs, 1.6)
            except Exception:
                agg_pool, agg_fut = None, None
        else:
            agg_fut = None

        # 重试 2 次（用户反馈详情偶发失败，资源站偶发抽风）
        d = {}
        name_hint = ""
        for attempt in range(2):
            d = self._fetch(first_api, {"ac": "detail", "ids": vid})
            if d.get("list"):
                break
            time.sleep(0.5)
        lst = d.get("list") or []
        if not lst:
            # 来源站抽风 → 按名称去其它站兜底
            nm = ""
            try:
                sc0 = self.searchContent(cached_name or vid, "", "1")
                for c in (sc0.get("list") or []):
                    if c.get("vod_id") != raw:
                        nm = (c.get("vod_id") or "")
                        break
            except Exception:
                nm = ""
            if nm:
                nsrc, _, nvid = nm.partition("|")
                d2 = self._fetch(self._api_of(nsrc), {"ac": "detail", "ids": nvid})
                l2 = d2.get("list") or []
                if l2:
                    lst = l2
                    src = nsrc
        if not lst:
            return {"list": []}
        it = lst[0]
        name_hint = it.get("vod_name") or ""
        name_clean = self._clean_query(name_hint)

        # ---- 跨站聚合：用番名查其他站，合并同番线路（无广告站优先）----
        agg_lines = []   # [(站rank, 站名, 线路中文名, 播放串)]
        seen_keys = set()
        def collect(site_name, play_from, play_url):
            for pf, pu in zip(play_from.split("$$$"), play_url.split("$$$")):
                pf = pf.strip()
                cn = self.CODE2CN.get(pf, pf or "线路")
                key = self._norm(pu)[:80]
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                agg_lines.append((self.SITE_RANK.get(site_name, 50), site_name, cn, pu))
        collect(src, it.get("vod_play_from", ""), it.get("vod_play_url", ""))
        if name_hint:
            from urllib.parse import quote as _q
            other_jobs = []
            # 只查无广告站（量子/360/暴风/最大/ikun），且不重复查来源站
            for name, bases, *_ in self.sites:
                if name == src or self.SITE_RANK.get(name, 50) > 5:
                    continue
                other_jobs.append((name, self._api_of(name), {"ac": "detail", "wd": name_clean}))
            def one(name, api, params):
                dd = self._fetch(api, params)
                return name, dd.get("list") or []
            if agg_fut is not None:
                try:
                    pre_res = agg_fut.result(timeout=0.6)
                except Exception:
                    pre_res = None
                results_agg = pre_res if pre_res else self._parallel(one, other_jobs, budget=1.0)
            else:
                results_agg = self._parallel(one, other_jobs, budget=1.2)
            for res in results_agg:
                if not res:
                    continue
                oname, olst = res
                t_clean = self._norm(name_clean)
                t_full = self._norm(name_hint)
                for ot in olst:
                    on = self._norm(ot.get("vod_name") or "")
                    if not (on == t_full or on == t_clean or on.startswith(t_clean)):
                        continue
                    # 集数容差 80%（略少也收，给用户多一条备选）；明显不符（剧场版/解说）丢弃
                    src_eps = len((it.get("vod_play_url") or "").split("$$$")[0].split("#"))
                    ot_eps = len((ot.get("vod_play_url") or "").split("$$$")[0].split("#"))
                    if src_eps <= 3 or ot_eps >= src_eps * 0.8:
                        collect(oname, ot.get("vod_play_from", ""), ot.get("vod_play_url", ""))
                    break
        # 按线路质量排序（无广告站靠前），重写线路名避免重复
        agg_lines.sort(key=lambda x: x[0])
        name_count = {}
        final_from, final_url = [], []
        for rank, site_name, cn, pu in agg_lines:
            name_count[cn] = name_count.get(cn, 0) + 1
            label = cn if name_count[cn] == 1 else "%s·%d" % (cn, name_count[cn])
            final_from.append(label)
            final_url.append(pu)

        result = {"list": [{
            "vod_id": raw,
            "vod_name": it.get("vod_name", ""),
            "vod_pic": it.get("vod_pic", ""),
            "type_name": it.get("type_name", ""),
            "vod_year": it.get("vod_year", ""),
            "vod_area": it.get("vod_area", ""),
            "vod_remarks": it.get("vod_remarks", ""),
            "vod_actor": it.get("vod_actor", ""),
            "vod_director": it.get("vod_director", ""),
            "vod_content": re.sub(r'<[^>]+>', '', it.get("vod_content") or "暂无简介").strip(),
            "vod_play_from": "$$$".join(final_from),
            "vod_play_url": "$$$".join(final_url),
        }]}
        self.cache[ck] = result
        return result

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        self._warm_apis()
        q = self._clean_query(key)
        jobs = [(name, self._api_of(name), {"ac": "detail", "wd": q}) for name, bases, *_ in self.sites]

        def one(name, api, params):
            d = self._fetch(api, params)
            return name, d.get("list") or []

        results = self._parallel(one, jobs)
        merged, seen = [], set()
        for res in results:
            if not res:
                continue
            name, lst = res
            for it in lst:
                tn = it.get("type_name") or ""
                if not any(w in tn for w in ("动漫", "动画")):
                    continue
                vid = str(it.get("vod_id", ""))
                k = name + "|" + vid
                if k in seen:
                    continue
                seen.add(k)
                self.cache.setdefault("names", {})[name + "|" + vid] = it.get("vod_name", "")
                merged.append({
                    "vod_id": name + "|" + vid,
                    "vod_name": it.get("vod_name", ""),
                    "vod_pic": it.get("vod_pic", ""),
                    "vod_remarks": it.get("vod_remarks", ""),
                })
        # 按线路质量排序：无广告站(量子/360/暴风/最大/ikun)的结果排前面
        prefer = ["量子资源", "360资源", "暴风资源", "最大资源", "ikun资源",
                  "速播资源", "索尼资源", "如意资源"]
        merged.sort(key=lambda x: prefer.index(x["vod_id"].split("|")[0])
                    if x["vod_id"].split("|")[0] in prefer else 99)
        return {"list": merged[:40], "page": 1, "pagecount": 1, "total": len(merged)}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        # m3u8/mp4 直链：parse=0 交给播放器，带 UA+Referer 头（部分 CDN 校验）
        if id and (".m3u8" in id.lower() or ".mp4" in id.lower()):
            return {"parse": 0, "url": id, "jx": 0,
                    "header": {"User-Agent": self.ua, "Referer": "https://www.baidu.com/"}}
        return {"parse": 1, "url": id, "jx": 0,
                "header": {"User-Agent": self.ua}}
