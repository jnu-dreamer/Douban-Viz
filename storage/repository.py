import sqlite3
import re
from typing import Dict, Iterable, List, Sequence, Any, Tuple, Optional
from utils.logger import logger

class MovieRepository:
    """SQLite 电影数据管理辅助类."""

    def __init__(self, db_path: str = "data/movie.db", table_name: str = "movies") -> None:
        self.db_path = db_path
        self.table_name = table_name

    def set_table(self, table_name: str) -> None:
        self.table_name = table_name

    def create_table_if_not_exists(self) -> None:
        sql = f"""
        create table if not exists {self.table_name}
        (
            id integer primary key autoincrement,
            info_link text,
            pic_link text,
            cname text,
            score text,
            rated text,
            introduction text,
            year_release text,
            country text,
            category text,
            directors text,
            actors text
        );
        """
        with self._connect() as conn:
            conn.execute(sql)
            conn.commit()

    def clear_table(self) -> None:
        self.create_table_if_not_exists()
        with self._connect() as conn:
            conn.execute(f"delete from {self.table_name}")
            conn.commit()

    def rename_table(self, old_name: str, new_name: str) -> None:
        """重命名数据表"""
        # 简单验证：只允许字母数字下划线
        if not new_name.isidentifier():
             raise ValueError("非法表名，仅支持字母、数字、下划线")
             
        with self._connect() as conn:
            conn.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
            conn.commit()
            
        # 如果重命名的是当前操作的表，更新实例变量
        if self.table_name == old_name:
            self.table_name = new_name

    def save_all(self, records: Iterable[Dict[str, str]]) -> int:
        records_list: List[Dict[str, str]] = list(records)
        if not records_list:
            return 0

        self.create_table_if_not_exists()
        
        # --- 去重逻辑 ---
        with self._connect() as conn:
            # 1. 获取库中已存在的链接
            try:
                existing_rows = conn.execute(f"select info_link from {self.table_name}").fetchall()
                existing_links = set(r[0] for r in existing_rows)
            except Exception:
                # 假如表刚创建或出错，默认无重复
                existing_links = set()
        
        # 2. 过滤掉库里已有的 + 过滤掉本次批次内重复的
        unique_records = []
        seen_links = set()
        
        for r in records_list:
            link = r.get("info_link", "")
            # 如果库里没有 且 本次未添加过
            if link and link not in existing_links and link not in seen_links:
                unique_records.append(r)
                seen_links.add(link)
        
        if not unique_records:
            return 0
            
        # 3. 执行插入
        fields: Sequence[str] = (
            "info_link",
            "pic_link",
            "cname",
            "score",
            "rated",
            "introduction",
            "year_release",
            "country",
            "category",
            "directors",
            "actors",
        )
        placeholders = ",".join(["?"] * len(fields))
        sql = f"insert into {self.table_name} ({','.join(fields)}) values ({placeholders})"
        values = [tuple(record.get(f, "") for f in fields) for record in unique_records]

        with self._connect() as conn:
            conn.executemany(sql, values)
            conn.commit()
            
        logger.info(f"  > Batch saved: {len(unique_records)} new, {len(records_list) - len(unique_records)} skipped.")
        return len(unique_records)

    # --- 读取方法 (从 app.py 重构而来) ---

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def get_stats(self) -> Dict[str, Any]:
        """获取看板的汇总统计信息."""
        with self._connect() as conn:
            cur = conn.cursor()
            total = cur.execute(f"select count(*) from {self.table_name}").fetchone()[0] or 0
            avg_score_row = cur.execute(f"select round(avg(score),2) from {self.table_name}").fetchone()
            avg_score = avg_score_row[0] if avg_score_row and avg_score_row[0] else 0
            high_score = cur.execute(f"select count(*) from {self.table_name} where score >= 9.0").fetchone()[0] or 0
            years = cur.execute(f"select count(distinct year_release) from {self.table_name}").fetchone()[0] or 0
            return {
                "total": total,
                "avg_score": avg_score,
                "high_score": high_score,
                "years": years
            }

    def get_paginated_movies(self, page: int, limit: int = 50) -> Tuple[List[Any], int]:
        """获取指定页码的电影及总页数."""
        offset = (page - 1) * limit
        with self._connect() as conn:
            cur = conn.cursor()
            total = cur.execute(f"select count(*) from {self.table_name}").fetchone()[0] or 0
            
            import math
            total_pages = math.ceil(total / limit) if limit > 0 else 1
            if total == 0: total_pages = 1

            rows = cur.execute(f"select * from {self.table_name} limit ? offset ?", (limit, offset)).fetchall()
            return rows, total_pages

    def search_movies(self, keyword: str) -> List[Any]:
        """按标题、演员、导演或类型搜索电影."""
        if not keyword:
            return []
        
        # 1. 动态检查表列名
        with self._connect() as conn:
            columns_info = conn.execute(f"PRAGMA table_info({self.table_name})").fetchall()
            columns = [info[1] for info in columns_info]

        # 2. 构建查询
        search_fields = ["cname", "category", "introduction", "year_release", "score", "rated"]
        if "actors" in columns:
            search_fields.append("actors")
        if "directors" in columns:
            search_fields.append("directors")
        if "country" in columns:
            search_fields.append("country")
            
        where_clause = " OR ".join([f"{field} LIKE ?" for field in search_fields])
        sql = f"select * from {self.table_name} where {where_clause}"
        
        # 3. 执行
        pattern = f"%{keyword}%"
        args = [pattern] * len(search_fields)
        
        with self._connect() as conn:
             return conn.execute(sql, args).fetchall()

    def get_all_movies(self) -> List[Any]:
        """获取所有电影记录 (例如用于导出)."""
        with self._connect() as conn:
            return conn.execute(f"select * from {self.table_name}").fetchall()

    def get_score_distribution(self) -> Tuple[List[str], List[int]]:
        """获取电影评分分布(排除 0 分或无评分数据)."""
        with self._connect() as conn:
            sql = f"""
                select score, count(score) 
                from {self.table_name} 
                where score is not null 
                  and score != '' 
                  and score != '0' 
                  and score != '0.0'
                group by score 
                order by score
            """
            data = conn.execute(sql).fetchall()
        labels = [str(r[0]) for r in data]
        counts = [r[1] for r in data]
        return labels, counts

    def get_year_distribution(self) -> Tuple[List[str], List[int]]:
        """获取电影上映年份分布(清洗并排序)."""
        import re
        with self._connect() as conn:
            # 获取所有原始年份字段
            raw_data = conn.execute(f"select year_release from {self.table_name}").fetchall()
        
        from collections import Counter
        year_counts = Counter()
        
        for row in raw_data:
            val = str(row[0]) if row[0] else ""
            # 提取4位数字年份 (例如: "2024(中国大陆)" -> "2024")
            match = re.search(r'(\d{4})', val)
            if match:
                year = match.group(1)
                # 简单过滤异常年份
                if 1900 <= int(year) <= 2030:
                    year_counts[year] += 1
        
        # 按年份排序
        sorted_years = sorted(year_counts.keys())
        labels = sorted_years
        counts = [year_counts[y] for y in sorted_years]
        
        return labels, counts

    def get_genre_statistics(self) -> List[Dict[str, Any]]:
        """获取 ECharts 使用的类型统计."""
        with self._connect() as conn:
            rows = conn.execute(f"select category from {self.table_name}").fetchall()
        
        genre_data: Dict[str, int] = {}
        for row in rows:
            if not row[0]: continue
            # Split by space as crawler saves them space-separated
            cats = row[0].split() 
            for c in cats:
                genre_data[c] = genre_data.get(c, 0) + 1
        
        return [{"name": k, "value": v} for k, v in genre_data.items()]

    def get_country_statistics(self) -> Tuple[List[str], List[int]]:
        """获取国家/地区统计."""
        with self._connect() as conn:
            rows = conn.execute(f"select country from {self.table_name}").fetchall()
        
        country_data: Dict[str, int] = {}
        for row in rows:
            if not row[0]: continue
            # 使用正则分割：同时支持空格和斜杠，排除空字符串
            # [ /]+ 匹配一个或多个空格或斜杠
            cts = re.split(r'[ /]+', row[0])
            for c in cts:
                if c.strip():
                    country_data[c] = country_data.get(c, 0) + 1
        
        # 按数量排列
        sorted_data = sorted(country_data.items(), key=lambda x: x[1], reverse=False)
        
        labels = [item[0] for item in sorted_data]
        counts = [item[1] for item in sorted_data]
        return labels, counts

    def get_all_category_text(self) -> str:
        """获取所有合并的分类文本 (用于词云)."""
        with self._connect() as conn:
            rows = conn.execute(f"select category from {self.table_name}").fetchall()
        return " ".join([r[0] for r in rows if r[0]])

    def get_all_intro_text(self) -> str:
        """获取所有合并的简介文本 (用于词云)."""
        with self._connect() as conn:
            rows = conn.execute(f"select introduction from {self.table_name}").fetchall()
        return " ".join([r[0] for r in rows if r[0]])

    def get_movie_by_id(self, movie_id: int) -> Optional[Any]:
        """根据 ID 获取单个电影详情"""
        with self._connect() as conn:
            row = conn.execute(f"select * from {self.table_name} where id = ?", (movie_id,)).fetchone()
            if row:
                return row
            return None

    def get_movies_by_ids(self, ids: List[int]) -> List[Any]:
        """根据 ID 列表批量获取电影"""
        if not ids: return []
        placeholders = ",".join(["?"] * len(ids))
        with self._connect() as conn:
            return conn.execute(f"select * from {self.table_name} where id in ({placeholders})", ids).fetchall()

    def get_top_genres(self, limit: int = 9) -> List[str]:
        """获取数量最多的前 N 个电影类型."""
        all_stats = self.get_genre_statistics()
        # 按数量倒序排列
        sorted_stats = sorted(all_stats, key=lambda x: x['value'], reverse=True)
        # 提取名称
        return [item['name'] for item in sorted_stats[:limit]]


__all__ = ["MovieRepository"]
