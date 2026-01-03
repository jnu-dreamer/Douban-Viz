# routes/api.py
"""API 接口路由模块

包含 RAG 智能问答、爬虫控制、聚类/图谱数据接口等。
"""
import os
import json
import threading
from flask import Blueprint, request, jsonify
from utils.logger import logger

api_bp = Blueprint('api', __name__, url_prefix='/api')

# 状态文件路径
STATUS_FILE = "data/status.json"


def save_status(status_data):
    """保存爬虫状态到文件"""
    try:
        temp_file = STATUS_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f)
        os.replace(temp_file, STATUS_FILE)
    except Exception as e:
        logger.error(f"Status save failed: {e}")


def load_status():
    """加载爬虫状态"""
    if not os.path.exists(STATUS_FILE):
        return {"status": "idle", "current": 0, "total": 0, "message": ""}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"status": "idle", "current": 0, "total": 0, "message": ""}


# ========== RAG 智能问答 ==========

@api_bp.route("/rag/search", methods=["POST"])
def api_rag_search():
    """RAG 语义检索 + 大模型回答"""
    from app import repo, vector_service, llm_service
    
    data = request.json
    query = data.get("query", "")
    if not query:
        return jsonify([])
    
    try:
        # 1. AI 提纯关键词并解析过滤条件
        analysis = llm_service.analyze_query(query)
        keywords = analysis.get("keywords", query)
        requirements = analysis.get("requirements", "")
        filters = analysis.get("filters", {})
        
        # 2. 语义搜索获取电影列表
        movies = vector_service.search(keywords, top_k=5, filters=filters)
        
        # 3. 调用大模型生成推荐语
        answer = llm_service.generate_answer(query, movies, requirements)
        
        return jsonify({
            "answer": answer,
            "movies": movies
        })
    except Exception as e:
        logger.error(f"RAG Search failed: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/rag/rebuild", methods=["POST"])
def api_rag_rebuild():
    """重建 RAG 向量索引"""
    from app import repo, vector_service
    from routes.admin import login_required
    
    try:
        data = request.json or {}
        target_table = data.get("table_name")
        
        logger.info(f"Received rebuild request. Target Table: {target_table}")
        
        if target_table:
            repo.set_table(target_table)
            logger.info(f"Switched repository to table: {target_table}")
        
        def task():
            logger.info("Starting background vector index rebuild...")
            try:
                vector_service.build_index(force_refresh=True)
                logger.info("Background vector rebuild finished successfully.")
            except Exception as e:
                logger.error(f"Background vector rebuild failed: {e}")
        
        threading.Thread(target=task, daemon=True).start()
        
        return jsonify({
            "status": "success",
            "message": f"Index rebuild started for {repo.table_name}."
        })
    except Exception as e:
        logger.error(f"Rebuild failed: {e}")
        return jsonify({"error": str(e)}), 500


# ========== 爬虫控制 ==========

@api_bp.route("/progress")
def api_progress():
    """获取爬虫进度"""
    return jsonify(load_status())


@api_bp.route("/logs")
def api_logs():
    """获取爬虫日志"""
    log_file = os.path.join("logs", "crawler.log")
    if not os.path.exists(log_file):
        return jsonify({"lines": ["暂无日志"]})
    try:
        with open(log_file, "r", encoding="utf-8", errors='ignore') as f:
            lines = f.readlines()
            return jsonify({"lines": lines[-100:]})
    except Exception as e:
        return jsonify({"error": str(e)})


@api_bp.route("/crawl", methods=["POST"])
def api_crawl():
    """启动爬虫任务"""
    import main
    from app import repo
    
    if not os.path.exists("data"):
        os.makedirs("data")
    
    initial_status = {
        "status": "running",
        "current": 0,
        "total": 0,
        "message": "正在初始化..."
    }
    save_status(initial_status)
    
    data = request.json
    crawl_type = data.get("crawl_type", "top250")
    tag = data.get("tag", "")
    pages = int(data.get("pages", 1))
    limit = int(data.get("limit", 200))
    sort = data.get("sort", "recommend")
    target_table_arg = data.get("target_table", "").strip()
    append_mode = data.get("append", False) or data.get("no_clear", False)
    
    if crawl_type == "tag":
        initial_status["total"] = limit
    else:
        initial_status["total"] = pages
    save_status(initial_status)
    
    # 决定目标表名
    final_table = "movies"
    if target_table_arg:
        final_table = target_table_arg
    elif tag and not append_mode:
        final_table = f"movies_{tag}"
    
    repo.set_table(final_table)
    
    base_url = "https://movie.douban.com/top250"
    if crawl_type == "tag":
        base_url = "JSON_API"
    
    def on_progress(current, total):
        status = load_status()
        status["current"] = current
        status["total"] = total
        if crawl_type == "tag":
            status["message"] = f"正在爬取第 {current}/{total} 部..."
        else:
            status["message"] = f"正在爬取第 {current}/{total} 页..."
        save_status(status)
    
    def task():
        try:
            logger.info(f"Starting Background Crawl: {crawl_type}, Table: {final_table}")
            main.run_crawl(
                base_url=base_url,
                tag=tag,
                pages=pages,
                limit=limit,
                delay=3.0,
                db_path="data/movie.db",
                clear=not append_mode,
                target_table=final_table,
                sort=sort,
                verbose=False,
                progress_callback=on_progress
            )
            logger.info("Background Crawl Finished Successfully.")
            
            status = load_status()
            status["status"] = "finished"
            status["message"] = "爬取完成！数据已更新。"
            status["current"] = limit if crawl_type == "tag" else pages
            save_status(status)
            
        except Exception as e:
            logger.error(f"Background Crawl Error: {e}")
            status = load_status()
            status["status"] = "error"
            status["message"] = f"发生错误: {str(e)}"
            save_status(status)
    
    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "success", "message": "爬虫已启动..."})


# ========== 聚类与图谱 ==========

@api_bp.route("/cluster/data")
def clustering_data():
    """获取聚类数据"""
    from app import repo
    from analysis.clustering import ClusteringService
    
    try:
        k = int(request.args.get("k", 10))
        k = max(2, min(k, 50))
        
        service = ClusteringService(repo)
        data = service.perform_clustering(n_clusters=k)
        if data is None:
            return jsonify({"error": "数据不足，无法进行聚类分析"}), 400
        return jsonify(data)
    except Exception as e:
        logger.error(f"Clustering Error: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/graph/data")
def graph_data():
    """获取知识图谱数据"""
    from app import repo
    from analysis.graph import GraphService
    
    try:
        limit = int(request.args.get("limit", 80))
        service = GraphService(repo)
        data = service.build_graph(limit_nodes=limit)
        return jsonify(data)
    except Exception as e:
        logger.error(f"Graph Error: {e}")
        return jsonify({"error": str(e)}), 500
