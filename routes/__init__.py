# routes/__init__.py
"""路由模块初始化

将所有 Blueprint 注册到 Flask 应用。
"""
from .movie import movie_bp
from .analysis import analysis_bp
from .admin import admin_bp
from .api import api_bp


def register_blueprints(app):
    """注册所有路由蓝图到 Flask 应用
    
    Args:
        app: Flask 应用实例
    """
    app.register_blueprint(movie_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)  # API 已在蓝图内设置 url_prefix='/api'
