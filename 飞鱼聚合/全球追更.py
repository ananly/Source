#!/usr/bin/python
# -*- coding: utf-8 -*-
import json, re, requests
try:
    from pyquery import PyQuery as pq
except Exception:
    pq = None
from urllib.parse import quote
try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object

class Spider(BaseSpider):
    def getName(self): return "全球追更"
    def init(self, extend=""):
        self.key = "2894d9a1baf7812b451de03c801b0281"
        self.ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        self.headers = {"User-Agent": self.ua}
        # 连接复用：同一进程内反复查不同剧时省掉 TLS 握手
        try:
            self.sess = requests.Session()
            self.sess.headers.update(self.headers)
        except Exception:
            self.sess = None
        self.img = "https://images.tmdb.org/t/p/w500"
        self.apis = ["https://api.tmdb.org/3"]
        self.platforms = [{"id":"domestic","name":"国内聚合","network":"2007|1419|1330|1605|1631"},{"id":"netflix","name":"Netflix","network":"213"},{"id":"hbo","name":"HBO Max","network":"49"},{"id":"disney","name":"Disney+","network":"2739"},{"id":"appletv","name":"Apple TV+","network":"2552"},{"id":"amazon","name":"Amazon Prime","network":"1024"},{"id":"hulu","name":"Hulu","network":"453"},{"id":"paramount","name":"Paramount+","network":"4330"}]
        self.cache = {}
        # 多个公开苹果CMS资源站：按剧名搜真实可播放剧集链接（TMDB 本身无视频）
        # 排序按响应速度从快到慢：subo(0.3s) < 量子(0.6s) < 360(0.9s) < 极速(1.0s) < 暴风(1.1s) < 金鹰(1.2s) < zuida(2.9s) < 非凡(3.9s)
        self.rh_apis = [
            "https://subozy.com/api.php/provide/vod",        # subo 0.26s
            "https://cj.lziapi.com/api.php/provide/vod",     # 量子 0.44s
            "https://360zy.com/api.php/provide/vod",         # 360 0.62s
            "https://www.jinyingzy.com/api.php/provide/vod", # 金鹰 0.59s
            "https://bfzyapi.com/api.php/provide/vod",       # 暴风 0.67s
            "https://haohuazy.com/api.php/provide/vod",      # 豪花 0.82s
            "https://hhzyapi.com/api.php/provide/vod",       # 豪华 0.80s
        ]
        self.rh_names = ["subo资源", "量子资源", "360资源", "金鹰资源",
                         "暴风资源", "豪花资源", "豪华资源", "subo采集"]
        # 备用站：主力都没结果时才查（慢站不拖累日常速度）
        self.rh_backup = [
            "https://api.zuidapi.com/api.php/provide/vod",
            "https://api.maoyanapi.top/api.php/provide/vod",
            "https://huyazy.net/api.php/provide/vod",
            "https://p2100.net/api.php/provide/vod",
            "https://subocaiji.com/api.php/provide/vod",
            "https://ikunzyapi.com/api.php/provide/vod",
            "https://www.hongniuzy2.com/api.php/provide/vod",
            "https://www.zuidazy.com/api.php/provide/vod",
            "https://jszyapi.com/api.php/provide/vod",
            "https://www.mdzyapi.com/api.php/provide/vod",
            "https://lovedan.net/api.php/provide/vod",
        ]
        self.rh_backup_names = ["最大资源", "猫眼资源", "虎牙资源", "品汇资源",
                                "subo采集②", "ikun资源", "红牛资源", "最大备用", "极速资源②", "摩都资源", "lovedan资源"]
        self.rh_map = dict(zip(self.rh_apis, self.rh_names))
        self.rh_map.update(dict(zip(self.rh_backup, self.rh_backup_names)))
        # 真 4K 站：搜索走 /index.php/ajax/suggest 两段式，仅用于电影补充
        self.rh_4k = ["https://suoniapi.com", "https://api.niuniuzy.me", "https://cj.yayazy.net"]
        self.rh_4k_map = {"https://suoniapi.com": "4K·索尼",
                          "https://api.niuniuzy.me": "4K·牛牛",
                          "https://cj.yayazy.net": "4K·丫丫"}
        self.rh_timeout = 1.8  # 单站超时：快站够用，慢站被自动跳过，不拖慢整体

    @staticmethod
    def _norm(s):
        """归一化剧名：去空白/括号/冒号等干扰字符"""
        return re.sub(r'[\s\u3000()（）\[\]【】:：]+', '', s or '')

    def _is_main_match(self, vn, target):
        """判断 vn 是否是 target 的正片。规则：
        1) 黑名单直接排除（剧场版/电影解说/预告/花絮/抢先）
        2) 精确相等算正片
        3) 包含时 target 前不能是汉字（排除"八零狂飙"），
           尾巴必须是白名单（动画版/重制版/年番/第N季/S0N/数字年份等）
        """
        if not target or not vn:
            return False
        if any(w in vn for w in ("剧场版", "电影版", "电影解说", "解说", "预告", "花絮", "抢先")):
            return False
        if vn == target:
            return True
        i = vn.find(target)
        if i < 0:
            return False
        if i > 0:
            prev = vn[i - 1]
            if "\u4e00" <= prev <= "\u9fff":
                return False
        tail = vn[i + len(target):]
        if not tail:
            return True
        for s in ("第", "季", "S", "s", "全", "年番", "动画版", "重制版", "完整版",
                  "合集", "合集篇", "4K", "高清版", "·", "-", "_", " "):
            if tail.startswith(s):
                return True
        # 尾巴以数字/字母开头（如 2020、1、II）也允许
        if not ("\u4e00" <= tail[0] <= "\u9fff"):
            return True
        return False

    def _pick_items(self, lst, target, anime, lang=""):
        """返回资源站条目中所有匹配正片的条目（含各季），排除预告/解说/电影解说/2D动画/动态漫。
        关键规则：
        1) 先做类型过滤（预告/解说/动漫/真人）
        2) 按原始语言匹配地区分类（zh→国产/中国，ja→日本/日韩，ko→韩国，en→欧美/美国）
        3) 3D 优先：条目 class 含 "2D动画"/"动态漫" 时，若有其他非 2D 条目则丢弃 2D 版
        4) 精确匹配优先，无精确匹配用智能包含匹配
        5) 全集/年番 与 分季 的取舍：若最大条目集数 >= 其余条目总和的 1.5 倍，
           视为"全集合集"只用它（避免把 395 集全季 + 41 集重制版重复合并成 436 集）
        返回 [(季号或0, 条目), ...]
        """
        # 第一步：类型过滤
        clean = []
        for it in lst:
            cls = (it.get("type_name") or "") + "/" + (it.get("vod_class") or "")
            if any(x in cls for x in ("预告", "解说", "花絮", "抢先", "电影解说")):
                continue
            is_ani_item = any(x in cls for x in ("动漫", "动画", "漫剧"))
            if anime and not is_ani_item:
                continue
            if not anime and is_ani_item:
                continue
            pu = it.get("vod_play_url") or ""
            if not pu or "$" not in pu:
                continue
            clean.append(it)
        # 第二步：精确匹配优先，无精确匹配才用智能包含匹配
        exact = [it for it in clean if self._norm(it.get("vod_name")) == target]
        pool = exact if exact else [it for it in clean if self._is_main_match(self._norm(it.get("vod_name")), target)]
        # 第二步半：按原始语言优先匹配地区分类（国产3D国漫 vs 日韩2D）
        if lang and pool:
            region_map = {"zh": ("国产", "中国", "大陆", "内地"),
                          "ja": ("日本", "日韩"),
                          "ko": ("韩国", "韩剧"),
                          "en": ("欧美", "美国", "美剧")}
            keys = region_map.get(lang)
            if keys:
                preferred = [it for it in pool
                             if any(k in ((it.get("type_name") or "") + (it.get("vod_class") or "")) for k in keys)]
                if preferred:
                    pool = preferred
        # 第三步：3D 优先——剔除 2D动画/动态漫（仅当还有非 2D 版本时）
        non2d = [it for it in pool
                 if not any(w in ((it.get("vod_class") or "") + (it.get("vod_name") or ""))
                            for w in ("2D动画", "2d动画", "动态漫"))]
        if non2d:
            pool = non2d
        # 第三步半：若池中有 4K 版本（type_name 含 4K 或播放串带 4K$），优先只取 4K
        fourk = [it for it in pool
                 if ("4k" in (it.get("type_name") or "").lower())
                 or ("4k$" in (it.get("vod_play_url") or "").lower())]
        if fourk:
            pool = fourk
        # 第四步：全集/年番 与 分季 的取舍
        if len(pool) > 1:
            sized = sorted(pool, key=lambda it: len((it.get("vod_play_url") or "").split("#")), reverse=True)
            top_eps = len((sized[0].get("vod_play_url") or "").split("#"))
            rest_eps = sum(len((x.get("vod_play_url") or "").split("#")) for x in sized[1:])
            if top_eps >= rest_eps * 1.5:
                pool = [sized[0]]
        out = []
        for it in pool:
            season = 0
            m = re.search(r'第\s*([一二三四五六七八九十\d]+)\s*季', it.get("vod_name") or "")
            if m:
                cn = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
                s = m.group(1)
                season = int(s) if s.isdigit() else cn.get(s, 0)
            out.append((season, it))
        return out

    def _merge_seasons(self, items):
        """把多季条目合并成连续编号的完整播放串（第01集、第02集...）。
        注意：苹果CMS 条目内可能有多线路（$$$分隔），这里只取第一条线路的剧集合并，避免污染。
        """
        total = []
        ep_no = 1
        for season, it in sorted(items, key=lambda x: (x[0] == 0, x[0])):
            line = (it.get("vod_play_url") or "").split("$$$")[0]
            for ep in line.split("#"):
                if "$" not in ep:
                    continue
                _name, url = ep.split("$", 1)
                if not url:
                    continue
                total.append("第%02d集$%s" % (ep_no, url))
                ep_no += 1
        return "#".join(total)

    def _http_get(self, url, params=None, timeout=5, verify=False):
        """统一 GET 入口：优先走 Session 连接池，失败回落 requests.get（默认忽略证书）"""
        try:
            if self.sess is not None:
                return self.sess.get(url, params=params, timeout=timeout, verify=False)
        except Exception:
            pass
        return requests.get(url, params=params, headers=self.headers, timeout=timeout, verify=False)

    def _fetch_rh(self, api, name):
        """单站查询，返回 (api, json) 或 None；只请求一次，超时由调用方控制"""
        try:
            r = self._http_get(api, params={"ac": "detail", "wd": name},
                               timeout=self.rh_timeout)
            if r.status_code == 200:
                return api, r.json()
        except Exception:
            pass
        return None

    def _search_play(self, name, anime=False, en_name=None, lang="", extra_names=None, movie=False):
        """多资源站【并发】聚合搜索，返回 [(中文线路名, 完整剧集播放串), ...]，结果缓存，总耗时 ≤2.5s
        策略：中文名（TMDB 已提供）为主，英文名为辅；宽松包含匹配，按季聚合，保证"全站有全集"。
        """
        if not name:
            return []
        target = self._norm(name)
        ck = "play:" + target + (":ani" if anime else "") + ":" + (lang or "") + ":" + (self._norm((extra_names or [""])[0]) if extra_names else "")
        if ck in self.cache:
            return self.cache[ck]
        # 搜索词队列：中文名 > 英文名（宽松包含，资源站收录的是中文名）
        candidates = [target]
        for _n in (extra_names or []):
            _nn = self._norm(_n)
            if _nn and _nn not in candidates:
                candidates.append(_nn)
        if en_name:
            en = self._norm(en_name)
            if en and en not in candidates:
                candidates.append(en)
        datasets = []
        lines = []
        ex = None
        fut4k = None
        futk = None
        try:
            from concurrent.futures import ThreadPoolExecutor, wait
            ex = ThreadPoolExecutor(max_workers=len(self.rh_apis) + 4)
            fut4k = ex.submit(self._search_4k, name, candidates) if movie else None
            futs = [ex.submit(self._fetch_rh, api, name) for api in self.rh_apis]
            # 第一波：1.0s 内能回来的快站全部收集（subo/量子/360/极速/暴风/金鹰都在 0.3~1.0s）
            done1, pending = wait(futs, timeout=1.1)
            for f in done1:
                try:
                    r = f.result()
                    if r:
                        datasets.append(r)
                except Exception:
                    continue
            lines = self._build_lines(datasets, candidates, anime, lang)
            # 线路不足 3 条时再等 1.2s 收慢站（保证多线路）
            if len(lines) < 3 and pending:
                done2, _ = wait(pending, timeout=0.9)
                for f in done2:
                    try:
                        r = f.result()
                        if r:
                            datasets.append(r)
                    except Exception:
                        continue
                lines = self._build_lines(datasets, candidates, anime, lang)
            # 主力仍不足 2 条时，补查备用站（只在覆盖差时才付这个时间）
            if len(lines) < 2 and self.rh_backup:
                try:
                    futsb = [ex.submit(self._fetch_rh, api, name) for api in self.rh_backup]
                    doneb, _ = wait(futsb, timeout=1.2)
                    for f in doneb:
                        try:
                            r = f.result()
                            if r:
                                datasets.append(r)
                        except Exception:
                            continue
                    lines = self._build_lines(datasets, candidates, anime, lang)
                except Exception:
                    pass
            # 可可影视整站多线路：并行尝试，1.0s 内有结果就合并（带集数校验）
            try:
                fk = ex.submit(self._kekys_lines, name, anime, lang)
                dk, _ = wait([fk], timeout=1.0)
                if dk:
                    kicks = fk.result() or []
                    base_max = max([len(u.split("#")) for _, u in lines] or [0])
                    if kicks:
                        kmax = max(len(u.split("#")) for _, u in kicks)
                        if base_max == 0 or (base_max * 0.5 <= kmax <= base_max * 2):
                            lines = kicks + lines
            except Exception:
                pass
            # 电影补充真 4K 线路（最多再等 0.9s）
            if fut4k is not None:
                try:
                    d4, _ = wait([fut4k], timeout=0.8)
                    if d4:
                        lines = fut4k.result() + lines
                except Exception:
                    pass
        except Exception:
            for api in self.rh_apis:
                r = self._fetch_rh(api, name)
                if r:
                    datasets.append(r)
            lines = self._build_lines(datasets, candidates, anime, lang)
        finally:
            if ex is not None:
                try:
                    ex.shutdown(wait=False)
                except Exception:
                    pass
        # 去重，集数完整优先、高清/直链次之，最多 10 条
        seen, out = set(), []
        for ln, u in lines:
            if u in seen:
                continue
            seen.add(u)
            out.append((ln, u))
        def _line_score(x):
            ln, u = x[0], x[1].lower()
            eps = len(x[1].split("#"))
            # 主排序：集数越多越靠前（确保正片全集优先，短剧/电影解说靠后）
            score = -eps * 100
            # 次排序：高清标记
            if any(k in ln for k in ("高清", "4k", "超清", "蓝光")):
                score -= 20
            if any(k in u for k in ("4k", "2160", "hd.", "vip.", "super", "hds", "1080")):
                score -= 10
            if ".m3u8" in u or ".mp4" in u:
                score -= 5
            return score
        out.sort(key=_line_score)
        # 过滤明显残缺的线路：当存在完整剧集（>=10集）时，丢弃 <3 集的版本（电影解说/片段）
        if out:
            max_eps = len(out[0][1].split("#"))
            if max_eps >= 10:
                out = [x for x in out if len(x[1].split("#")) >= 3]
        self.cache[ck] = out[:12]
        return self.cache[ck]

    def _search_4k(self, name, candidates):
        """4K 专站两段式搜索：suggest 找 id -> detail 取播放串，返回真 4K/高清线路"""
        out = []
        try:
            from concurrent.futures import ThreadPoolExecutor, wait
            def one(base):
                try:
                    r = self._http_get(base + "/index.php/ajax/suggest",
                                       params={"mid": 1, "wd": name}, timeout=1.2)
                    lst = (r.json() or {}).get("list") or []
                    ids = []
                    for cand in candidates:
                        hit = [x for x in lst if self._norm(x.get("name")) == cand]
                        if not hit:
                            hit = [x for x in lst if self._is_main_match(self._norm(x.get("name")), cand)]
                        if hit:
                            ids = [x.get("id") for x in hit[:2] if x.get("id")]
                            break
                    items = []
                    for i in ids:
                        d = self._http_get(base + "/api.php/provide/vod",
                                           params={"ac": "detail", "ids": i}, timeout=1.2)
                        items += ((d.json() or {}).get("list") or [])
                    return base, items
                except Exception:
                    return base, []
            ex2 = ThreadPoolExecutor(max_workers=len(self.rh_4k))
            futs2 = [ex2.submit(one, b) for b in self.rh_4k]
            done2, _ = wait(futs2, timeout=1.2)
            for f in done2:
                try:
                    base, items = f.result()
                except Exception:
                    continue
                if not items:
                    continue
                picked = []
                for cand in candidates:
                    picked = self._pick_items(items, cand, False, "")
                    if picked:
                        break
                if not picked:
                    continue
                merged = self._merge_seasons(picked)
                if not merged:
                    continue
                raw = " ".join(((it.get("vod_play_url") or "") for _, it in picked)).lower()
                label = self.rh_4k_map.get(base, "4K站")
                if not (("4k" in raw) or ("2160" in raw)):
                    label = "📺" + label
                out.append((label, merged))
            try:
                ex2.shutdown(wait=False)
            except Exception:
                pass
        except Exception:
            pass
        return out

    def _kekys_lines(self, name, anime=False, lang=""):
        """可可影视整站：搜索 → 详情 → 解析全部线路（蓝光/超清/HN/FF…）。
        该站一部剧常有 10~20 条线路，是 appleCMS 站点的有力补充。
        """
        base = "https://103.51.147.112:51120"
        try:
            r = self._http_get(base + "/search", params={"k": name}, timeout=2.5)
            if r is None or r.status_code != 200:
                return []
            r.encoding = "utf-8"
            m = re.search(r'name="t" value="([^"]+)"', r.text)
            if m:
                r = self._http_get(base + "/search", params={"k": name, "t": m.group(1)}, timeout=2.5)
                r.encoding = "utf-8"
            cands = []
            if pq is not None:
                for it in pq(r.text)(".search-result-item").items():
                    href = it.attr("href") or ""
                    mm = re.search(r"/detail/(\d+)\.html", href)
                    if not mm:
                        continue
                    title = it.find(".title").text().strip()
                    if not title:
                        img = it.find("img")
                        title = (img.attr("alt") or "") if img.length else ""
                    cands.append((title.strip(), mm.group(1)))
            else:
                for mm in re.finditer(r'href="/detail/(\d+)\.html"', r.text):
                    cands.append(("", mm.group(1)))
            target = self._norm(name)
            # 保持搜索排序（该站高质量条目常排在前），只要标题能对上就收
            picks = []
            for t, vid in cands:
                if t and self._is_main_match(self._norm(t), target):
                    picks.append(vid)
                elif not t:
                    picks.append(vid)
            if not picks:
                return []
            def _one(vid):
                try:
                    d = self._http_get(base + "/detail/%s.html" % vid, timeout=2.5)
                    if d is None or d.status_code != 200:
                        return []
                    d.encoding = "utf-8"
                    play = re.findall(r'href="(/play/\d+-(\d+)-(\d+)\.html)"[^>]*>(.*?)</a>', d.text, re.DOTALL)
                    labels = [x.strip() for x in re.findall(r'class="source-item-label"[^>]*>([^<]+)</', d.text)]
                    order, eps = [], {}
                    for href, sid, nid, text in play:
                        txt = re.sub(r"<[^>]+>", "", text).strip() or ("第%s集" % nid)
                        if sid not in eps:
                            eps[sid] = []
                            order.append(sid)
                        eps[sid].append("%s$%s" % (txt, base + href))
                    lines = []
                    for i, sid in enumerate(order):
                        label = labels[i] if i < len(labels) else ("线路%s" % sid)
                        if label.strip() == "4K":
                            continue
                        if eps.get(sid):
                            lines.append(("可可·" + label, "#".join(eps[sid])))
                    return lines
                except Exception:
                    return []
            best_lines, best_total = [], 0
            cands3 = picks[:2]
            if cands3:
                try:
                    from concurrent.futures import ThreadPoolExecutor, wait as _w
                    ex2 = ThreadPoolExecutor(max_workers=len(cands3))
                    fs = [ex2.submit(_one, v) for v in cands3]
                    _d, _ = _w(fs, timeout=1.0)
                    for f in _d:
                        try:
                            ls = f.result()
                        except Exception:
                            continue
                        total = sum(len(u.split("#")) for _, u in ls)
                        if total > best_total:
                            best_lines, best_total = ls, total
                    try:
                        ex2.shutdown(wait=False)
                    except Exception:
                        pass
                except Exception:
                    pass
            return best_lines[:12]
        except Exception:
            return []

    def _build_lines(self, datasets, candidates, anime, lang=""):
        """把各站返回的原始 JSON 转换成线路列表 [(中文线路名, 播放串), ...]"""
        lines = []
        for api, data in datasets:
            try:
                lst = data.get("list") or []
                if not lst:
                    continue
                items = []
                for cand in candidates:
                    items = self._pick_items(lst, cand, anime, lang)
                    if items:
                        break
                if not items:
                    continue
                zh = self.rh_map.get(api, "资源")
                merged = self._merge_seasons(items)
                if not merged:
                    continue
                # 识别真 4K：条目类型含 4K 或播放串带 4K$ 标签
                raw = " ".join([(it.get("type_name") or "") + " " + (it.get("vod_play_url") or "") for _, it in items]).lower()
                if ("4k电影" in raw) or ("4k$" in raw) or ("2160" in raw):
                    zh = "🅺4K·" + zh
                elif any(k in merged.lower() for k in ("hd.", "vip.", "super", "hds", "1080")):
                    zh = "📺" + zh
                lines.append((zh, merged))
            except Exception:
                continue
        return lines

    def _trailer_urls(self, video_data):
        """从 TMDB videos 提取可用的 trailer 链接（YouTube 签名 URL），保底用"""
        urls = []
        for v in (video_data or {}).get("results", []) or []:
            key = v.get("key")
            if not key:
                continue
            typ = (v.get("type") or "").lower()
            if typ in ("trailer", "teaser"):
                urls.append("https://www.youtube.com/embed/" + key)
        return urls
    def _get(self, endpoint, params=None):
        params = params or {}
        params["api_key"] = self.key
        for base in self.apis:
            try:
                r = self._http_get(base + endpoint, params=params, timeout=8)
                if r.status_code == 200: return r.json()
            except Exception:
                continue
        return {}
    def _today(self):
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d")
    def _filters(self):
        return [{"key":"sort","name":"🔥 动态追踪","value":[{"n":"📅 追更模式","v":"next_episode"},{"n":"📆 今日播出","v":"daily_airing"},{"n":"🆕 最新上线","v":"first_air_date.desc"},{"n":"⭐ 综合热度","v":"popularity.desc"}]},{"key":"type","name":"📺 内容类型","value":[{"n":"🎥 电视剧集","v":"tv"},{"n":"🎬 电影作品","v":"movie"},{"n":"🌸 动漫动画","v":"anime"},{"n":"🎤 综艺节目","v":"variety"}]}]
    def _pic(self, p): return self.img + p if p else ""
    def _vod(self, item, typ, sort="popularity.desc"):
        mid = str(item.get("id",""))
        name = item.get("name") or item.get("title") or ""
        remark = "⭐" + str(round(float(item.get("vote_average") or 0), 1))
        date = item.get("first_air_date") or item.get("release_date") or "1900-01-01"
        ck = "info_" + typ + "_" + mid + "_" + sort
        if ck in self.cache: return self.cache[ck]
        if not any("\u4e00" <= x <= "\u9fff" for x in name):
            d = self._get(("/movie/" if typ == "movie" else "/tv/") + mid, {"language":"zh-CN","append_to_response":"alternative_titles,external_ids"})
            alt = ((d.get("alternative_titles") or {}).get("titles") or (d.get("alternative_titles") or {}).get("results") or [])
            for t in alt:
                if t.get("iso_3166_1") == "CN" and t.get("title"):
                    name = t.get("title")
                    break
        if typ != "movie" and sort in ["next_episode","daily_airing","first_air_date.desc"]:
            d = self._get("/tv/" + mid, {"language":"zh-CN"})
            ep = d.get("next_episode_to_air") or d.get("last_episode_to_air")
            if ep:
                date = ep.get("air_date") or date
                remark = ("🕒" if d.get("next_episode_to_air") else "✅") + date[5:] + " S" + str(ep.get("season_number") or 0).zfill(2) + "E" + str(ep.get("episode_number") or 0).zfill(2)
        vod = {"vod_id":typ + ":" + mid, "vod_name":name, "vod_pic":self._pic(item.get("poster_path")), "vod_remarks":remark, "_date":date}
        self.cache[ck] = vod
        return vod
    def homeContent(self, filter):
        fs = self._filters()
        return {"class":[{"type_id":p["id"],"type_name":p["name"]} for p in self.platforms], "filters":{p["id"]:fs for p in self.platforms}, "list":[]}
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        p = next((x for x in self.platforms if x["id"] == tid), None)
        if not p: return {"page":page,"pagecount":1,"limit":20,"total":0,"list":[]}
        sort = (extend or {}).get("sort") or "popularity.desc"
        typ = (extend or {}).get("type") or "tv"
        media = "movie" if typ == "movie" else "tv"
        endpoint = "/discover/movie" if media == "movie" else "/discover/tv"
        base = {"language":"zh-CN","page":page,"sort_by":"popularity.desc" if sort in ["daily_airing","next_episode"] else sort}
        if typ == "anime": base["with_genres"] = "16"
        if typ == "variety": base["with_genres"] = "10764|10767"
        if sort == "daily_airing":
            base["air_date.gte"] = self._today()
            base["air_date.lte"] = self._today()
        items, seen = [], set()
        for net in p["network"].split("|"):
            q = dict(base)
            q["with_networks"] = net
            data = self._get(endpoint, q)
            for i in data.get("results", []):
                mid = str(i.get("id",""))
                if mid and mid not in seen:
                    seen.add(mid)
                    items.append(i)
        if sort in ["next_episode","daily_airing","first_air_date.desc"]: items.sort(key=lambda x:x.get("first_air_date") or x.get("release_date") or "", reverse=True)
        else: items.sort(key=lambda x:float(x.get("popularity") or 0), reverse=True)
        return {"page":page,"pagecount":100,"limit":20,"total":2000,"list":[self._vod(i, media, sort) for i in items[:20]]}
    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, list) else ids
        arr = str(raw).split(":", 1)
        typ, mid = (arr[0], arr[1]) if len(arr) == 2 else ("tv", str(raw))
        data = self._get(("/movie/" if typ == "movie" else "/tv/") + mid, {"language":"zh-CN","append_to_response":"credits,videos,alternative_titles"})
        if not data and typ != "movie":
            typ = "movie"
            data = self._get("/movie/" + mid, {"language":"zh-CN","append_to_response":"credits"})
        if not data: return {"list":[]}
        name = data.get("name") or data.get("title") or ""
        year = (data.get("release_date") or data.get("first_air_date") or "")[:4]
        area = ", ".join([c.get("name","") for c in data.get("production_countries", [])])
        actor = ", ".join([c.get("name","") for c in (data.get("credits") or {}).get("cast", [])[:8]])
        director = ", ".join([c.get("name","") for c in (data.get("credits") or {}).get("crew", []) if c.get("job") == "Director"][:3])
        # 是否动漫（TMDB 类型含“动画”）
        is_anime = any((g or {}).get("id") == 16 for g in data.get("genres") or [])
        en_name = data.get("original_name") or data.get("original_title") or ""
        lang = data.get("original_language") or ""
        alts = []
        _alt = (data.get("alternative_titles") or {})
        for t in (_alt.get("results") or _alt.get("titles") or []):
            if t.get("iso_3166_1") in ("CN", "HK", "TW") and t.get("title"):
                alts.append(t.get("title"))
        alts = alts[:3]
        # 资源站聚合（data 里已带 videos，直接用于 trailer 保底）
        lines = self._search_play(name, anime=is_anime, en_name=en_name, lang=lang, extra_names=alts, movie=(typ == "movie"))
        # 无正片时用 trailer 保底，保证"全站不空"
        if not lines:
            tb = self._trailer_urls(data.get("videos"))
            if tb:
                lines = [("官方预告", tb[0])]
        if lines:
            play_from = "$$$".join([ln for ln, _ in lines])
            play_url = "$$$".join([u for _, u in lines])
        else:
            play_from = "其他源"
            play_url = "播放$" + quote(name)
        return {"list":[{"vod_id":typ + ":" + mid,"vod_name":name,"vod_pic":self._pic(data.get("poster_path")),"type_name":"电影" if typ == "movie" else "电视剧","vod_year":year,"vod_area":area,"vod_remarks":"电影" if typ == "movie" else ("已完结" if data.get("status") == "Ended" else "连载中"),"vod_actor":actor,"vod_director":director,"vod_content":data.get("overview") or "暂无剧情简介","vod_play_from":play_from,"vod_play_url":play_url}]}
    def searchContent(self, key, quick, pg="1"):
        page = int(pg or 1)
        data = self._get("/search/multi", {"query":key,"page":page,"language":"zh-CN"})
        return {"list":[{"vod_id":i.get("media_type","tv") + ":" + str(i.get("id","")),"vod_name":i.get("title") or i.get("name") or key,"vod_pic":self._pic(i.get("poster_path")),"vod_remarks":"电影" if i.get("media_type") == "movie" else "剧集","goSearch":True} for i in data.get("results", []) if i.get("media_type") in ["movie","tv"]],"page":page,"pagecount":data.get("total_pages",1),"total":data.get("total_results",0)}
    def _resolve_kekys(self, url):
        """可可影视播放页 → 真实 m3u8（含 Referer，部分线路校验）"""
        try:
            r = self._http_get(url, timeout=8)
            if r is None:
                return ""
            r.encoding = "utf-8"
            for pat in (r'src:\s*["\']([^"\']+\.(m3u8|mp4)[^"\']*)["\']',
                        r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"',
                        r"url\s*:\s*'([^']+\.m3u8[^']*)'"):
                m = re.search(pat, r.text, re.DOTALL)
                if m:
                    return m.group(1)
            us = re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*', r.text)
            for u in us:
                if "index.m3u8" in u or "video.m3u8" in u or ".mp4" in u:
                    return u
            return us[0] if us else ""
        except Exception:
            return ""

    def playerContent(self, flag, id, vipFlags):
        # 可可影视播放页：现取 m3u8
        if id and "/play/" in id and id.endswith(".html"):
            u = self._resolve_kekys(id)
            if u:
                return {"parse": 0, "url": u, "jx": 0,
                        "header": {"User-Agent": self.ua, "Referer": "https://103.51.147.112:51120/"}}
            return {"parse": 1, "url": id, "jx": 0}
        if id and (".m3u8" in id.lower() or ".mp4" in id.lower()):
            return {"parse": 0, "url": id}
        return {"parse": 1, "url": id}