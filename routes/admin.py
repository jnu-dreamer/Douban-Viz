# routes/admin.py
"""管理后台相关路由模块

包含登录、登出、后台管理、数据表切换等功能。
"""
import os
import sqlite3
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

admin_bp = Blueprint('admin', __name__)

# 数据库路径常量
DB_PATH = os.path.join("data", "movie.db")


def login_required(f):
    """认证装饰器：检查用户是否已登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("admin.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """管理员登录页面"""
    if request.method == "POST":
        password = request.form.get("password")
        if password == "douban666":
            session["logged_in"] = True
            return redirect(url_for("admin.admin"))
        else:
            flash("密码错误！", "danger")
    return render_template("login.html")


@admin_bp.route("/logout")
def logout():
    """退出登录"""
    session.pop("logged_in", None)
    return redirect(url_for("movie.index"))


@admin_bp.route("/admin")
@login_required
def admin():
    """管理后台主页面"""
    from app import repo
    from routes.api import load_status
    
    status = load_status()
    
    # 获取当前数据库的所有表名
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' and name != 'sqlite_sequence'"
        ).fetchall()]
        conn.close()
    except Exception as e:
        print(f"Error fetching tables: {e}")
        tables = []
    
    return render_template("admin.html", status=status, current_table=repo.table_name, tables=tables)


@admin_bp.route("/api/switch_table", methods=["POST"])
@login_required
def switch_table():
    """切换当前操作的数据表"""
    from app import repo
    
    new_table = request.form.get("table_name")
    if new_table:
        repo.set_table(new_table)
        flash(f"已切换数据源为: {new_table}", "success")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/api/rename_table", methods=["POST"])
@login_required
def rename_table():
    """重命名数据表"""
    from app import repo
    
    old_name = request.form.get("old_name")
    new_name = request.form.get("new_name")
    
    if not old_name or not new_name:
        flash("表名不能为空", "danger")
        return redirect(url_for("admin.admin"))
    
    try:
        repo.rename_table(old_name, new_name)
        flash(f"成功将表 {old_name} 重命名为 {new_name}", "success")
    except Exception as e:
        flash(f"重命名失败: {str(e)}", "danger")
    
    return redirect(url_for("admin.admin"))
