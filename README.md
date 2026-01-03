# 🎬 Douban AI Analysis: 基于RAG的电影智能分析系统

> **本项目**是一个基于 Python Flask 全栈开发，集成 RAG（检索增强生成）、知识图谱、文本聚类等 AI 技术的电影数据采集与可视化分析平台。

---

### 🌟 核心特性

- **RAG 智能问答**: 集成 DeepSeek 大模型，支持 "推荐一部诺兰拍的悬疑片" 等自然语言语义搜索。
- **知识图谱**: 自动构建 "导演-演员" 合作关系网络，直观展示影人社群。
- **文本聚类**: 基于 TF-IDF + K-Means 对剧情简介进行聚类，自动发现潜在题材流派。
- **动态大屏**: 使用 ECharts 实现词云、地图、折线图等数据可视化。

---

### 🛠️ 环境搭建

本项目基于 Python 3.8+ 开发。

1.  **克隆仓库**
    ```bash
    git clone https://github.com/yourusername/douban-flask.git
    cd douban-flask
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置环境变量**
    复制配置文件模板：
    ```bash
    cp .env.example .env
    ```
    打开 `.env` 文件，填入您的 DeepSeek API Key (或其他兼容 OpenAI 格式的 Key)。

---

### 🚀 运行项目

1.  **获取数据 (可选)**
    (首次运行建议执行，抓取 Top250 数据入库)
    ```bash
    python main.py
    ```

2.  **启动 Web 服务**
    ```bash
    python app.py
    ```
    
3.  **访问系统**
    打开浏览器访问: [http://127.0.0.1:5002](http://127.0.0.1:5002)

---

### 📦 目录结构
- `app.py`: Web 服务主入口
- `main.py`: 爬虫任务入口
- `analysis/`: RAG、聚类、图谱算法核心
- `spider/`: 豆瓣爬虫策略
- `storage/`: 数据库与 CRUD 封装
- `templates/` & `static/`: 前端视图资源
