import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE # 替换 PCA 为 t-SNE
import numpy as np
from storage.repository import MovieRepository
import re

class ClusteringService:
    """电影剧情聚类服务
    
    使用 TF-IDF 提取剧情关键词，结合 K-Means 聚类和 t-SNE 降维，
    将电影按内容相似度分组并可视化展示。
    """
    def __init__(self, repo: MovieRepository):
        self.repo = repo
        self.stopwords = self._load_stopwords()

    def _load_stopwords(self):
        # 扩展停用词表：通用中文停用词 + 电影领域专用噪音词
        # 根据 Top 20 调试结果，剔除了大量高频虚词 (如"为了", "他们") 以提升聚类质量
        common_stops = set(['的', '了', '和', '是', '就', '都', '而', '及', '与', '在', '这', '那', '有', '也', '很', '啊', '吧', '之', '用', '于', '么', '不', '些', '个', '为', '对', '可', '能', '好', '多', '年', '月', '日', '次', '地', '得', '着', '过', '去', '上', '下', '里', '外', '为了', '他们', '它们', '这些', '那些', '自己', '一切', '然而', '只是', '因为', '所以', '虽然', '但是', '如果', '或者', '以及', '正在', '开始', '结束', '最终', '决定', '发现', '认为', '成为', '感觉', '一名', '一位', '一个'])
        # 根据 Top 50 调试结果，继续剔除叙事性虚词 (如"一天", "没有", "离开")
        domain_stops = set(['电影', '影片', '片子', '故事', '讲述', '一个', '一种', '一场', '饰演', '扮演', '导演', '主演', '本片', '上映', '发布', '预告', '剧情', '包含', '关于', '主要', '就是', '但是', '因为', '所以', '虽然', '即使', '之后', '后来', '最终', '开始', '结束', '时候', '这里', '那里', '这个', '那个', '生活', '世界', '两人', '特与', '配音', '一天', '一次', '一起', '回到', '来到', '没有', '离开', '找到', '帮助', '工作', '最佳', '人生', '人类'])
        return common_stops.union(domain_stops)

    def _clean_text(self, text):
        if not text:
            return ""
        # 仅保留中文，去除标点符号和特殊字符
        text = re.sub(r'[^\u4e00-\u9fa5]', '', text)
        return text

    def _get_series_token(self, title):
        if not title: return ""
        # 1. 去除 "第X季", "Season X"
        t = re.sub(r'第[0-9一二三四五六七八九十]+季|Season\s*\d+', '', title, flags=re.IGNORECASE)
        # 2. 去除末尾数字 (例如 " 2", " 3", " II")
        t = re.sub(r'\s+\d+$|\s+[IVX]+$', '', t)
        # 3. 去除冒号后的副标题 (例如 "黑客帝国: 重装上阵" -> "黑客帝国")
        t = t.split("：")[0].split(":")[0]
        # 4. 去除括号内容
        t = re.sub(r'\(.*?\)|（.*?）', '', t)
        return self._clean_text(t).strip()

    def perform_clustering(self, n_clusters=8):
        # 1. 获取数据
        movies = self.repo.get_all_movies()
        # 过滤掉简介过短的电影
        valid_movies = [m for m in movies if m[6] and len(m[6]) > 10]
        
        if not valid_movies:
            return None

        # 2. 特征工程：构建混合语料
        # 策略：简介 + (类型 * 3) + (导演 * 5) + (系列名 * 10)
        # 系列名用于强制将续集聚类在一起
        corpus = []
        titles = []
        ids = []

        for m in valid_movies:
            intro = self._clean_text(m[6])
            # 切词处理简介
            intro_words = [w for w in jieba.cut(intro) if w not in self.stopwords and len(w) > 1]
            
            # 处理类型 (Type is at index 7) - 假设 Type 是 "剧情 犯罪" 这样的字符串
            genre = self._clean_text(m[7])
            genre_words = [w for w in jieba.cut(genre)] * 3
            
            # 处理导演 (Director is at index 10)
            director = self._clean_text(m[10]) # 假设 index 10 是导演
            director_words = [w for w in jieba.cut(director)] * 5

            # 处理系列名，聚合续集/季
            title = m[3]
            series_token = self._get_series_token(title)
            # 极高权重：让 TF-IDF 认为这是最重要的特征
            series_words = [w for w in jieba.cut(series_token) if len(w) > 1] * 10

            # 合并特征
            full_text = " ".join(intro_words + genre_words + director_words + series_words)
            corpus.append(full_text)
            
            titles.append(m[3])
            ids.append(m[1])

        # 3. TF-IDF 向量化：提取最重要的 20 个关键词，支持 1-gram 和 2-gram (如 "奇幻冒险")
        vectorizer = TfidfVectorizer(max_features=200, ngram_range=(1, 2))
        X = vectorizer.fit_transform(corpus)
        
        # 调试输出：打印被选中的核心关键词 (Top 20)
        from utils.logger import logger
        logger.debug(f"【聚类使用的 Top {len(vectorizer.get_feature_names_out())} 核心词】: {vectorizer.get_feature_names_out()}")

        # 4. K-Means 聚类：n_init=100 表示运行 100 次取最优，防止陷入局部最优解
        kmeans = KMeans(n_clusters=n_clusters, random_state=2025, n_init=100)
        labels = kmeans.fit_predict(X)

        # 5. t-SNE 降维（非线性降维，能有效解决点挤在一起的问题）
        n_samples = X.shape[0]
        
        # perplexity 参数需要小于样本数
        perplex = min(200, max(5, n_samples - 1))
        
        tsne = TSNE(n_components=2, perplexity=perplex, early_exaggeration=24, random_state=2025, init='pca', learning_rate='auto')
        coords = tsne.fit_transform(X.toarray())

        # 6. 格式化输出供 ECharts 使用
        result = []
        for i in range(n_clusters):
            cluster_points = []
            for j, label in enumerate(labels):
                if label == i:
                    cluster_points.append([
                        round(float(coords[j][0]), 3), # x
                        round(float(coords[j][1]), 3), # y
                        titles[j],                     # title
                        valid_movies[j][1],            # link
                        valid_movies[j][0]             # id (新增：用于跳转详情页)
                    ])
            result.append({
                "name": f"聚类 {i+1}",
                "data": cluster_points
            })
            
        return result

    def get_similar_movies(self, movie_id: int, n_top: int = 6):
        """基于内容(TF-IDF)计算最相似的电影"""
        from sklearn.metrics.pairwise import cosine_similarity
        
        # 1. 获取所有有效数据
        movies = self.repo.get_all_movies()
        valid_movies = [m for m in movies if m[6] and len(m[6]) > 10]
        
        # 2. 找到目标电影的索引
        target_idx = -1
        for i, m in enumerate(valid_movies):
            if m[0] == movie_id:
                target_idx = i
                break
        
        if target_idx == -1:
            return []

        # 3. 构建特征 (简化版逻辑，保持一致性)
        corpus = []
        for m in valid_movies:
            intro = self._clean_text(m[6])
            intro_words = [w for w in jieba.cut(intro) if w not in self.stopwords and len(w) > 1]
            genre_words = [w for w in jieba.cut(self._clean_text(m[7]))] * 2
            director_words = [w for w in jieba.cut(self._clean_text(m[10]))] * 2
            
            series_token = self._get_series_token(m[3])
            series_words = [w for w in jieba.cut(series_token) if len(w) > 1] * 10
            
            corpus.append(" ".join(intro_words + genre_words + director_words + series_words))

        # 4. 向量化
        vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 3))
        X = vectorizer.fit_transform(corpus)
        
        # 5. 计算余弦相似度
        # 只计算目标向量与所有向量的距离
        target_vec = X[target_idx]
        sim_scores = cosine_similarity(target_vec, X).flatten()
        
        # 6. 排序取 Top K (排除自己)
        # argsort 返回从小到大的索引，取最后 n_top+1 个，然后逆序
        related_indices = sim_scores.argsort()[-(n_top+1):][:-1][::-1]
        
        recommendations = []
        for idx in related_indices:
            if idx == target_idx: continue
            m = valid_movies[idx]
            recommendations.append({
                "id": m[0],
                "title": m[3],
                "pic": m[2],
                "score": m[4],
                "year": m[7],
                "similarity": round(sim_scores[idx] * 100, 1) # 相似度百分比
            })
            
        return recommendations
