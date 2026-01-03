# app.py
"""Flask 应用主入口

负责初始化 Flask 应用、数据库连接、AI 服务，
并注册所有路由蓝图。
"""
import os
import threading
from flask import Flask
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ========== 应用初始化 ==========
 
DB_PATH = os.path.join("data", "movie.db")
app = Flask(__name__)
app.secret_key = "douban_secret_key123"  # Flask Session 密钥
 
# ========== 服务初始化 ==========
 
from storage.repository import MovieRepository
from analysis.vector_service import VectorService
from analysis.llm_service import LLMService
 
# 数据仓库（全局单例）
repo = MovieRepository(DB_PATH, table_name="movie_rag")
 
# 向量检索服务
vector_service = VectorService(repo)
 
# 大语言模型服务
# 请在项目根目录创建 .env 文件并设置 DEEPSEEK_API_KEY
llm_service = LLMService(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    model="deepseek-v3-250324"
)


# ========== 后台预加载 ==========

def preload_vectors():
    """后台线程预加载向量索引"""
    try:
        vector_service.build_index()
    except Exception as e:
        print(f"Error preloading vectors: {e}")

threading.Thread(target=preload_vectors, daemon=True).start()


# ========== 全局上下文 ==========

@app.context_processor
def inject_sidebar_tags():
    """注入侧边栏热门标签（实时从数据库获取，最多9个）"""
    try:
        top_genres = repo.get_top_genres(limit=9)
    except Exception:
        top_genres = []
    
    colors = ['secondary']
    tags_data = []
    for i, genre in enumerate(top_genres):
        color = colors[i % len(colors)]
        tags_data.append((genre, color))
    
    return dict(sidebar_tags=tags_data)


# ========== 注册路由蓝图 ==========

from routes import register_blueprints
register_blueprints(app)


# ========== 启动入口 ==========

if __name__ == "__main__":
    app.run(debug=True, port=5002)
