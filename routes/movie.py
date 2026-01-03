# routes/movie.py
"""电影相关路由模块

包含首页、电影列表、电影详情、词云、搜索等功能。
"""
import os
from io import BytesIO
from flask import Blueprint, render_template, request, send_file, current_app

movie_bp = Blueprint('movie', __name__)


@movie_bp.route("/")
def index():
    """首页：展示统计概览"""
    from app import repo
    stats = repo.get_stats()
    return render_template("index.html", stats=stats)


@movie_bp.route("/index")
def home():
    """重定向到首页"""
    return index()


@movie_bp.route("/movie")
def movie_list():
    """电影列表页：支持分页展示"""
    from app import repo
    page = int(request.args.get("page", 1))
    limit = 50
    movies, total_pages = repo.get_paginated_movies(page, limit)
    return render_template("movie.html", movies=movies, page=page, total_pages=total_pages)


@movie_bp.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    """电影详情页：展示基本信息和相似推荐"""
    from app import repo, vector_service
    from analysis.clustering import ClusteringService
    
    # 1. 获取电影基本信息
    movie = repo.get_movie_by_id(movie_id)
    if not movie:
        return "未找到电影", 404
    
    # 2. 获取相似推荐 (对比模式)
    # A. 基于内容 (TF-IDF + 关键词)
    cluster_service = ClusteringService(repo)
    rec_tfidf = cluster_service.get_similar_movies(movie_id, n_top=6)
    
    # B. 基于语义 (Embedding)
    rec_embedding = vector_service.search_by_id(movie_id, top_k=6)
    
    return render_template("detail.html", movie=movie, rec_tfidf=rec_tfidf, rec_embedding=rec_embedding)


@movie_bp.route("/word")
def word():
    """词云页面"""
    return render_template("cloud.html")


@movie_bp.route("/word/generate")
def word_generate():
    """生成动态词云图片"""
    try:
        import jieba
        import jieba.analyse
        from wordcloud import WordCloud
        import numpy as np
        from PIL import Image
        from app import repo
        
        # 0. 获取词云类型
        wc_type = request.args.get("type", "category")
        
        # 1. 加载蒙版图
        img_name = 'tree.jpg' if wc_type == 'category' else 'image.jpg'
        img_path = os.path.join(current_app.root_path, 'static', 'assets', 'img', img_name)
        img_array = None
        if os.path.exists(img_path):
            img_array = np.array(Image.open(img_path))
            img_array[img_array > 240] = 255
        
        # 2. 确定字体路径
        font_candidates = [
            "/mnt/c/Windows/Fonts/msyh.ttc",
            "/mnt/c/Windows/Fonts/simhei.ttf",
            "msyh.ttc", "simhei.ttf",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        font_path = None
        for f in font_candidates:
            if os.path.exists(f) or (not f.startswith("/") and os.path.exists(os.path.join(current_app.root_path, f))):
                font_path = f
                break
        
        wc = WordCloud(
            background_color='white',
            mask=img_array,
            font_path=font_path
        )
        
        # 3. 处理文本与生成逻辑
        if wc_type == "intro":
            text = repo.get_all_intro_text()
            tags = jieba.analyse.extract_tags(text, topK=300, withWeight=True, allowPOS=('n', 'nz', 'v', 'vn'))
            wc.generate_from_frequencies(dict(tags))
        else:
            text = repo.get_all_category_text()
            cut = jieba.cut(text)
            string = ' '.join(cut)
            wc.generate_from_text(string)
        
        # 4. 输出图片
        image = wc.to_image()
        out = BytesIO()
        image.save(out, format='PNG')
        out.seek(0)
        return send_file(out, mimetype='image/png')
    
    except Exception as e:
        print(f"WordCloud Error: {e}")
        return f"Error generating wordcloud: {e}", 500


@movie_bp.route("/aboutMe")
def aboutMe():
    """关于项目页面"""
    return render_template("aboutMe.html")


@movie_bp.route("/help")
def help():
    """帮助页面"""
    return render_template("help.html")


@movie_bp.route("/search")
def search():
    """搜索页面"""
    from app import repo
    keyword = request.args.get("q", "")
    datalist = repo.search_movies(keyword)
    return render_template("search.html", movies=datalist, keyword=keyword)
