import re # 用于正则匹配
import time # 用于延迟
import urllib.error # 用于处理URL请求异常
import urllib.request # 用于处理URL请求
from urllib.parse import quote # URL编码
from typing import Dict, List, Optional # 用于类型提示
from bs4 import BeautifulSoup # 用于解析HTML
from utils.logger import logger # 导入日志模块


class DoubanSpider:
    """豆瓣电影列表爬虫 (支持 Top250 或指定标签)."""
    def __init__(self, base_url: str = "https://movie.douban.com/top250", tag: str = "", sort: str = "recommend", pages: int = 10, limit: int = 200, delay: float = 1.0, start: int = 0):
        self.base_url = base_url.rstrip("/")
        self.tag = tag
        self.sort = sort
        if self.tag:
            # base_url 用作HTTP请求头的Referer，API请求用作URL
            self.base_url = f"https://movie.douban.com/tag/{quote(self.tag)}"
        
        self.pages = pages
        self.limit = limit
        self.delay = delay
        self.start = start 
        self.headers = { # 设置HTTP头，伪装为Chrome浏览器
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        # 例如: "123456 人评价"
        self.rating_count_pattern = re.compile(r"(\d+)\s*人评价") # 匹配评价人数
        # 例如: "1994 / 美国 / 剧情 犯罪" (Top250 标准格式)
        self.meta_pattern = re.compile(r"(\d{4})\s*/\s*([^/]+)\s*/\s*(.+)") # 匹配年份、国家、类型

    def fetch(self, progress_callback=None, save_callback=None) -> List[Dict[str, str]]:
        """抓取豆瓣电影列表，返回电影字典列表
        Args:
            progress_callback: 进度回调函数
            save_callback: 数据保存回调函数 (batch_data -> None)
        """
        records: List[Dict[str, str]] = [] 
        
        # 模式一：标签搜索 (使用 j/new_search_subjects API)
        if self.tag:
            self.headers.update({"Referer": f"https://movie.douban.com/tag/{quote(self.tag)}"})
            start = self.start # 使用传入的 start 作为起点
            batch_size = 20
            
            # 映射排序参数
            # T: 热度 (Hot), S: 评分 (Score), R: 上映日期 (Release)
            sort_map = {
                "recommend": "T",
                "rank": "S", 
                "time": "R",
                "recent": "U" 
            }
            api_sort = sort_map.get(self.sort, "T")

            while len(records) < self.limit:
                remaining = self.limit - len(records)
                current_limit = min(batch_size, remaining)
                
                # 使用新版 API，支持更丰富的筛选
                # tags: tags=2023, tags=喜剧
                # range: 0,10 (默认全范围)
                url = f"https://movie.douban.com/j/new_search_subjects?sort={api_sort}&range=0,10&tags={quote(self.tag)}&start={start}"
                
                logger.info(f"Fetching API {url} ...")
                if progress_callback:
                    progress_callback(len(records), self.limit)

                content = self._get(url)
                if not content:
                    logger.warning("Empty response from API")
                    break
                    
                batch = self._parse_json(content)
                if not batch:
                    logger.info("No more data in response")
                    break
                
                if save_callback:
                    logger.info(f"  > Saving {len(batch)} records...")
                    save_callback(batch)
                
                records.extend(batch)
                start += len(batch)
                
                if self.delay and len(records) < self.limit:
                    time.sleep(self.delay)
            
            if progress_callback:
                progress_callback(len(records), self.limit)
                
        # 模式二：Top 250 (网页分页抓取)
        else:
            for i in range(self.pages):  # 循环，从第0页到第self.pages-1页
                if progress_callback:
                    progress_callback(i + 1, self.pages) # 更新进度
                
                start = i * 25
                url = f"{self.base_url}?start={start}"
                self.headers.update({"Referer": "https://movie.douban.com/top250"})

                logger.info(f"Fetching {url} ...")
                content = self._get(url)
                if not content:
                    continue
                
                batch = self._parse(content)
                if save_callback:
                     logger.info(f"  > Saving {len(batch)} records...")
                     save_callback(batch)
                records.extend(batch)
                    
                if self.delay:
                    time.sleep(self.delay)
        return records

    def _get(self, url: str) -> str:
        request = urllib.request.Request(url, headers=self.headers)
        
        # 重试机制：最多尝试3次
        for attempt in range(3):
            try:
                # 增加超时时间到 15 秒，应对网络波动
                with urllib.request.urlopen(request, timeout=15) as resp:
                    return resp.read().decode("utf-8")
            except Exception as e:
                logger.warning(f"Request Error for {url} (Attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1)) # 失败后稍微等待 2s, 4s 再重试
                else:
                    logger.error(f"Failed to fetch {url} after 3 attempts.")
                    return ""

    def _parse_json(self, json_str: str) -> List[Dict[str, str]]:
        import json
        records: List[Dict[str, str]] = []
        try:
            data = json.loads(json_str)
            # 兼容新旧 API: new -> "data", old -> "subjects"
            subjects = data.get("data") if "data" in data else data.get("subjects", [])
            
            for sub in subjects:
                # API 返回有限字段: rate, title, url, cover, is_new, id, casts, directors
                # 我们将其映射到我们的 schema
                
                info_link = sub.get("url", "")
                
                # 获取详情以补充缺失字段
                # 注意: 即使新API有 casts/directors, 我们仍需 get_details 获取 introduction, country 等
                logger.debug(f"  > Fetching details for {sub.get('title', '')} ...")
                details = self._get_movie_details(info_link)

                # 优先使用 API 提供的 metadata (如果有), 否则用详情页数据
                # New API: directors, casts are lists of strings or objects. Old API: absent or diff.
                # Safe strategy: trust get_movie_details for deep info, use API for basic ID/Score
                
                records.append({
                    "info_link": info_link,
                    "pic_link": sub.get("cover", ""),
                    "cname": sub.get("title", ""),
                    "score": sub.get("rate", "0"),
                    "rated": details["rated"], 
                    "introduction": details["introduction"],
                    "year_release": sub.get("year") or details["year"], # Try API year first
                    "country": details["country"], 
                    "category": details["category"] if details["category"] else self.tag, 
                    "directors": details["directors"],
                    "actors": details["actors"],
                })

                # 关键修复：在每部电影详情抓取后等待，防止请求过快
                if self.delay:
                    time.sleep(self.delay)
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response")
        return records

    def _get_movie_details(self, url: str) -> Dict[str, str]:
        """抓取电影详情页，获取完整信息"""
        details = {
            "introduction": "", "country": "", "year": "", "category": "",
            "rated": "", "directors": "", "actors": ""
        }
        if not url:
            return details
            
        try:
            time.sleep(0.5) # 缩短延迟到 0.5s，并在下方 _get 增加了超时控制
            html = self._get(url)
            if not html:
                return details
                
            soup = BeautifulSoup(html, "html.parser")
            
            # 1. 简介 (v:summary)
            related_info = soup.find("div", class_="related-info")
            if related_info:
                # 优先寻找隐藏的“展开全部”里的完整简介
                hidden_span = related_info.find("span", class_="all hidden")
                if hidden_span:
                    details["introduction"] = hidden_span.get_text(strip=True)
                else:
                    span = related_info.find("span", property="v:summary")
                    if span:
                        # 处理可能存在的 <br>
                        details["introduction"] = span.get_text(strip=True)

            # 2. Meta 信息 (#info)
            info_div = soup.find("div", id="info")
            if info_div:
                text = info_div.get_text()
                # 制片国家/地区
                if "制片国家/地区:" in text:
                    parts = text.split("制片国家/地区:")
                    if len(parts) > 1:
                        details["country"] = parts[1].split("\n")[0].strip()
                
                # 上映年份 (优先从 JSON 或 List 获取，这里作为补充)
                if "上映日期:" in text or "首播:" in text:
                    y_parts = re.findall(r"(\d{4})", text)
                    if y_parts:
                        details["year"] = y_parts[0]

            # 3. 评价人数 (v:votes)
            vote_tag = soup.find("span", property="v:votes")
            if vote_tag:
                 details["rated"] = vote_tag.get_text(strip=True)

            # 4. 类型 (v:genre) -  获取完整类型列表
            genre_tags = soup.find_all("span", property="v:genre")
            if genre_tags:
                details["category"] = " ".join([t.get_text(strip=True) for t in genre_tags])

            # 5. 导演 (v:directedBy)
            bus = soup.find_all("a", rel="v:directedBy")
            if bus:
                details["directors"] = " ".join([b.get_text(strip=True) for b in bus])
            
            # 6. 主演 (v:starring)
            acts = soup.find_all("a", rel="v:starring")
            if acts:
                details["actors"] = " ".join([a.get_text(strip=True) for a in acts[:5]]) # 仅取前5

        except Exception as e:
            logger.warning(f"Failed to fetch details for {url}: {e}")
            
        return details

    def _parse(self, html: str) -> List[Dict[str, str]]: # 解析HTML（top250）
        soup = BeautifulSoup(html, "html.parser") 
        records: List[Dict[str, str]] = []
        
        items = soup.find_all("div", class_="item")
        for item in items:
            link_tag = item.find("a", href=True)
            info_link = link_tag["href"] if link_tag else ""

            img_tag = item.find("img")
            pic_link = img_tag["src"] if img_tag else ""

            title_tag = item.find("span", class_="title")
            cname = title_tag.get_text(strip=True) if title_tag else ""

            rating_tag = item.find("span", class_="rating_num")
            score = rating_tag.get_text(strip=True) if rating_tag else ""

            # 暂时获取列表页的基础信息作为兜底
            list_rated = ""
            star_div = item.find("div", class_="star")
            if star_div:
                m = self.rating_count_pattern.search(star_div.get_text())
                if m:
                    list_rated = m.group(1)

            # 列表页的简介通常只是短评(quote)，不是真正的简介
            quote_tag = item.find("span", class_="inq")
            short_quote = quote_tag.get_text(strip=True) if quote_tag else ""

            # 解析列表页的元数据 (年份/国家/类型)
            list_year = list_country = list_category = ""
            list_directors = list_actors = ""
            
            bd_div = item.find("div", class_="bd")
            if bd_div:
                p_tag = bd_div.find("p")
                if p_tag:
                    raw_text = str(p_tag)
                    parts = re.split(r"<br\s*/?>", raw_text)
                    if len(parts) >= 1:
                        line1 = BeautifulSoup(parts[0], "html.parser").get_text(strip=True)
                        if "导演:" in line1:
                            d_parts = line1.split("主演:")
                            list_directors = d_parts[0].replace("导演:", "").strip()
                            if len(d_parts) > 1:
                                list_actors = d_parts[1].strip()
                    if len(parts) >= 2:
                        line2 = BeautifulSoup(parts[1], "html.parser").get_text(strip=True)
                        m = self.meta_pattern.search(line2)
                        if m:
                            list_year = m.group(1).strip()
                            list_country = m.group(2).strip()
                            list_category = m.group(3).strip()

            # --- 关键修改：进入详情页抓取完整信息 ---
            logger.debug(f"  > Fetching details for {cname} ...")
            details = self._get_movie_details(info_link)
            
            # 合并逻辑：优先使用详情页信息，列表页信息兜底
            final_record = {
                "info_link": info_link,
                "pic_link": pic_link,
                "cname": cname,
                "score": score,
                "rated": details["rated"] if details["rated"] else list_rated,
                # 简介：如果有详情页简介则用详情页，否则用 Quote，实在没有为空
                "introduction": details["introduction"] if details["introduction"] else short_quote,
                "year_release": details["year"] if details["year"] else list_year,
                "country": details["country"] if details["country"] else list_country,
                "category": details["category"] if details["category"] else list_category,
                "directors": details["directors"] if details["directors"] else list_directors,
                "actors": details["actors"] if details["actors"] else list_actors,
            }

            records.append(final_record)

        return records


__all__ = ["DoubanSpider"]
