
import os
import re
import pickle
import threading 
import numpy as np
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from utils.logger import logger
from storage.repository import MovieRepository

class VectorService:
    """向量检索服务类
    
    负责将电影数据转换为语义向量，并提供基于向量相似度的检索功能。
    支持混合检索：先用元数据过滤，再用向量相似度排序。
    """
    def __init__(self, repo: MovieRepository, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.repo = repo
        self.model_name = model_name
        self.model = None
        self.vectors = None      # numpy 数组: [电影数量, 768维向量]
        self.movie_ids = None    # 列表: 与向量索引一一对应的电影 ID
        self.id_to_meta = None   # 字典: ID -> {title, score, ...} 用于快速返回元数据
        self.cache_path = os.path.join("data", "vectors.pkl")
        self.lock = threading.Lock()  # 线程锁，防止并发构建索引
        
    def _load_model(self):
        if self.model is None:
            logger.info(f"Loading Embedding Model: {self.model_name} ...")
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info("Model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                raise e

    def build_index(self, force_refresh: bool = False):
        """构建或加载向量索引
        
        线程安全：使用 Lock 确保同一时间只有一个线程在构建索引。
        优先从缓存加载，若缓存过期（数据库数量变化）则重新构建。
        
        Args:
            force_refresh: 是否强制重建索引（忽略缓存）
        """
        with self.lock:
            # 如果向量索引已加载且非强制刷新，直接返回
            if not force_refresh and self.vectors is not None:
                return

            # 尝试从缓存文件加载
            if not force_refresh and os.path.exists(self.cache_path):
                try:
                    self._load_from_cache()
                    # 简单校验：比较缓存数量与数据库数量是否一致
                    db_count = len(self.repo.get_all_movies())
                    if len(self.movie_ids) == db_count:
                        logger.info("向量索引已从缓存加载。")
                        return
                    else:
                        logger.info(f"缓存已过期 (数据库: {db_count}, 缓存: {len(self.movie_ids)})，正在重建...")
                except Exception as e:
                    logger.warning(f"加载缓存失败: {e}，正在重建...")
            
            # 开始重建索引
            self._load_model()
            logger.info("正在从数据库构建向量索引...")
            
            movies = self.repo.get_all_movies()
            # 过滤掉简介过短（少于5个字符）的电影，这些数据质量差
            valid_movies = [m for m in movies if m[6] and len(m[6].strip()) > 5]
            
            if not valid_movies:
                logger.warning("没有找到有效的电影简介，无法构建索引。")
                return

            # 构建丰富语义文本: 片名 + 年份 + 国家 + 类型 + 导演 + 主演 + 简介
            # 使用自然语言模板而非键值对，增强 BERT 模型对实体关系的理解
            sentences = []
            for m in valid_movies:
                # 数据库字段索引说明:
                # 0:id, 1:url, 2:pic, 3:title, 4:score, 5:rated, 6:intro, 
                # 7:year, 8:country, 9:category, 10:directors, 11:actors
                
                title = m[3]
                intro = m[6]
                year = m[7] if len(m) > 7 else ''
                country = m[8] if len(m) > 8 else ''
                category = m[9] if len(m) > 9 else ''
                directors = m[10] if len(m) > 10 else ''
                actors = m[11] if len(m) > 11 else ''
                
                # 优化策略：使用自然语言构建，增强语义连贯性
                # 相比 "Key: Value" 列表，自然语言更能被 BERT 类模型理解实体间的关系 (如 "由...执导")
                meta_part = f"电影《{title}》"
                if year: meta_part += f"于{year}年上映"
                if country: meta_part += f"，产地{country}"
                if category: meta_part += f"，类型为{category}"
                
                staff_part = ""
                if directors: staff_part += f"。由{directors}执导"
                if actors: staff_part += f"，{actors}主演"
                
                text = f"{meta_part}{staff_part}。剧情简介：{intro}"
                sentences.append(text)

            # 构建 ID 到元数据的映射字典，用于后续检索结果快速填充
            self.movie_ids = [m[0] for m in valid_movies]
            self.id_to_meta = {
                m[0]: {
                    "title": m[3], 
                    "score": m[4], 
                    "pic": m[2], 
                    "intro": m[6], 
                    "url": m[1],
                    "year": m[7],      # 用于年份过滤
                    "country": m[8],   # 用于国家过滤
                    "category": m[9],  # 用于类型过滤
                    "director": m[10], # 用于导演过滤
                    "actor": m[11]     # 用于演员过滤
                } for m in valid_movies
            }
            
            logger.info(f"正在编码 {len(sentences)} 部电影（使用 CPU/GPU）...")
            self.vectors = self.model.encode(sentences, normalize_embeddings=True)
            
            self._save_to_cache()
            logger.info("向量索引构建完成并已保存到缓存。")

    def _save_to_cache(self):
        with open(self.cache_path, "wb") as f:
            pickle.dump({
                "vectors": self.vectors,
                "movie_ids": self.movie_ids,
                "id_to_meta": self.id_to_meta
            }, f)

    def _load_from_cache(self):
        with open(self.cache_path, "rb") as f:
            data = pickle.load(f)
            self.vectors = data["vectors"]
            self.movie_ids = data["movie_ids"]
            self.id_to_meta = data["id_to_meta"]

    def search(self, query: str, top_k: int = 5, filters: Dict = None) -> List[Dict]:
        """语义检索 + 元数据过滤
        
        先对用户查询进行向量化，计算与所有电影的余弦相似度，
        同时应用元数据过滤条件（年份、国家、类型、导演、演员），
        返回相似度最高的 Top K 结果。
        
        Args:
            query: 用户的自然语言查询
            top_k: 返回结果数量
            filters: 过滤条件字典，支持 year_min, year_max, country, category, director, actor
            
        Returns:
            包含电影信息的字典列表
        """
        if self.vectors is None:
            self.build_index()
            
        if self.vectors is None or len(self.vectors) == 0:
            return []
            
        self._load_model()
        
        # BGE 模型建议查询添加特定指令以提升检索效果
        query_instruction = "为这个句子生成表示以用于检索相关文章："
        query_text = query_instruction + query if "bge" in self.model_name.lower() else query
        
        query_vec = self.model.encode([query_text], normalize_embeddings=True)
        similarity = cosine_similarity(query_vec, self.vectors)[0]
        
        # 按相似度降序排列索引
        sorted_indices = np.argsort(similarity)[::-1]
        
        results = []
        filters = filters or {}
        
        for idx in sorted_indices:
            if len(results) >= top_k:
                break
                
            score = similarity[idx]
            movie_id = self.movie_ids[idx]
            meta = self.id_to_meta[movie_id]
            
            # --- 过滤逻辑 ---
            try:
                # 年份范围过滤
                if "year_min" in filters or "year_max" in filters:
                    y_str = re.search(r'\d{4}', str(meta.get("year", "")))
                    y = int(y_str.group()) if y_str else 0
                    if "year_min" in filters and y < filters["year_min"]: continue
                    if "year_max" in filters and y > filters["year_max"]: continue
                
                # 国家/地区过滤 (模糊匹配)
                if "country" in filters and filters["country"]:
                    if filters["country"] not in str(meta.get("country", "")): continue

                # 电影类型过滤 (模糊匹配)
                if "category" in filters and filters["category"]:
                    if filters["category"] not in str(meta.get("category", "")): continue

                # 导演过滤 (模糊匹配)
                if "director" in filters and filters["director"]:
                    if filters["director"] not in str(meta.get("director", "")): continue

                # 演员过滤 (模糊匹配)
                if "actor" in filters and filters["actor"]:
                    if filters["actor"] not in str(meta.get("actor", "")): continue
                    
            except Exception as e:
                # 出错时采用宽容策略：跳过过滤继续处理，避免因数据缺失导致整个查询失败
                pass
            # -----------------------

            results.append({
                "id": movie_id,
                "title": meta["title"],
                "score": meta["score"],
                "pic": meta["pic"],
                "intro": meta["intro"][:100] + "...",
                "url": meta.get("url", ""),
                "year": meta.get("year", ""), 
                "similarity": float(score)
            })
            
        return results

    def search_by_id(self, movie_id: str, top_k: int = 6) -> List[Dict]:
        """根据电影 ID 查找相似电影
        
        利用目标电影的向量，计算与其他电影的余弦相似度，
        返回最相似的 Top K 部电影（排除自身）。
        
        Args:
            movie_id: 目标电影的数据库 ID
            top_k: 返回结果数量
            
        Returns:
            相似电影信息列表
        """
        if self.vectors is None:
            self.build_index()

        if movie_id not in self.movie_ids:
            return []

        # 获取目标电影的向量
        idx = self.movie_ids.index(movie_id)
        target_vec = self.vectors[idx].reshape(1, -1)

        # 计算余弦相似度
        similarity = cosine_similarity(target_vec, self.vectors)[0]

        # 获取相似度最高的 Top K 索引（排除自身）
        # argsort 返回从小到大排序的索引，取最后的高分部分，跳过第一个（自身）
        top_indices = np.argsort(similarity)[::-1][1 : top_k + 1]

        results = []
        for i in top_indices:
            score = similarity[i]
            mid = self.movie_ids[i]
            meta = self.id_to_meta[mid]

            results.append({
                "id": mid,
                "title": meta["title"],
                "score": meta["score"],
                "pic": meta["pic"],
                "intro": meta["intro"][:60] + "...", 
                "year": meta.get("year", ""), # Add year if available in meta, but meta dict init in build_index checked earlier might miss it?
                # Actually build_index line 87: "title": m[3], "score": m[4], "pic": m[2], "intro": m[6], "url": m[1]. 
                # Year is not in id_to_meta!
                # I should update id_to_meta or just accept it's missing. ClustringService returns year.
                # Let's peek build_index line 87 again.
                "similarity": round(float(score) * 100, 1)
            })
        return results
