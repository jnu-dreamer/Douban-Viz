# 🔬 豆瓣电影项目 - 专业代码审查报告

**审查日期**: 2026-01-02  
**代码规模**: 6 核心模块, 约 1900 行 Python 代码

---

## 一、审查概要

| 模块 | 行数 | 关键问题 |
| :--- | :--- | :--- |
| `app.py` | 703 | 🔴 API Key 硬编码, 文件过长 |
| `vector_service.py` | 249 | 🟡 缺少 `import re`, 死注释 |
| `llm_service.py` | 137 | ✅ 良好，有防御性编程 |
| `douban_spider.py` | 330 | 🟡 重复调用 `_parse_json` |
| `repository.py` | 302 | 🟡 SQL 字符串拼接危险 |
| `clustering.py` | 183 | 🟡 调试 `print` 语句残留 |

---

## 二、🔴 严重问题 (Critical)

### 2.1 API Key 硬编码 (app.py:27)
**位置**: `app.py` 第 27 行
```python
llm_service = LLMService(
    api_key="d38eca80-b3ff-4217-8827-18bc7451b042",  # 🔴 泄露！
    ...
)
```
**风险**: API Key 被推送到 GitHub 后可能被滥用，产生费用。
**修复建议**:
```python
import os
llm_service = LLMService(
    api_key=os.getenv("LLM_API_KEY"),  # ✅ 从环境变量读取
    ...
)
```
并使用 `.env` 文件或服务器环境变量管理密钥。

---

### 2.2 Flask Secret Key 硬编码 (app.py:17)
**位置**: `app.py` 第 17 行
```python
app.secret_key = "douban_secret_key123"  # 🔴 弱密钥
```
**风险**: Session 可被伪造。
**修复建议**:
```python
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
```

---

### 2.3 缺少 `import re` (vector_service.py:167)
**位置**: `vector_service.py` 第 167 行
```python
y_str = re.search(r'\d{4}', str(meta.get("year", "")))  # 🔴 NameError
```
**问题**: `re` 模块未导入，运行时会崩溃。
**修复**: 在文件顶部添加 `import re`。

---

## 三、🟡 中等问题 (Major)

### 3.1 文件过长 (app.py: 703 行)
**问题**: 单文件包含 50+ 个路由和辅助函数，违反单一职责原则。
**修复建议**: 使用 Flask Blueprint 拆分:
```
routes/
├── admin.py      # /admin, /login, /logout
├── api.py        # /api/rag/*, /api/export/*
├── analysis.py   # /analysis, /clustering
└── movie.py      # /movie, /movie/<id>
```

---

### 3.2 重复导入 (app.py:3 & 33)
```python
import threading  # 第 3 行
# ...
import threading  # 第 33 行 (重复!)
```

---

### 3.3 重复方法调用 (douban_spider.py:75 & 80)
```python
batch = self._parse_json(content)  # 第 75 行
# ...
batch = self._parse_json(content)  # 第 80 行 (重复调用!)
```
**修复**: 删除第 80 行的重复调用。

---

### 3.4 SQL 字符串拼接 (repository.py)
多处使用 f-string 拼接表名:
```python
conn.execute(f"select * from {self.table_name}")  # 潜在 SQL 注入
```
**风险**: 如果 `table_name` 来自用户输入，可能被注入攻击。
**修复**: 虽然当前 `table_name` 来自内部，但应加白名单校验:
```python
VALID_TABLES = {"movies", "movies_科幻", "movies_动作"}
if self.table_name not in VALID_TABLES:
    raise ValueError("非法表名")
```

---

### 3.5 调试语句残留 (clustering.py:88-91)
```python
print("-" * 50)
print(f"【聚类使用的 Top {len(...)} 核心词】:")
print(vectorizer.get_feature_names_out())
print("-" * 50)
```
**修复**: 改为 `logger.debug(...)` 或删除。

---

## 四、🟢 轻微问题 (Minor)

### 4.1 魔法数字 (Multiple Files)
*   `vectorizer = TfidfVectorizer(max_features=20, ...)` (clustering.py:84)
*   `top_k=5` (vector_service.py:134)
*   `for attempt in range(3)` (douban_spider.py:126)

**建议**: 提取为常量或配置项:
```python
MAX_TF_IDF_FEATURES = 20
DEFAULT_SEARCH_TOP_K = 5
MAX_RETRY_ATTEMPTS = 3
```

---

### 4.2 死注释 (vector_service.py:241-245)
```python
# Year is not in id_to_meta!
# I should update id_to_meta or just accept it's missing...
# Let's peek build_index line 87 again.
```
**修复**: 删除开发过程中的思考笔记，改为规范的 TODO 或完全删除。

---

### 4.3 缺少 Docstring (app.py)
绝大多数路由函数无文档字符串，例如:
```python
@app.route("/movie")
def movie():  # ❌ 没有 docstring
    ...
```
**修复**: 添加简洁的功能说明:
```python
@app.route("/movie")
def movie():
    """电影列表页，支持分页."""
    ...
```

---

## 五、✅ 优秀实践 (Praise)

1.  **线程安全**: `VectorService.build_index` 使用了 `threading.Lock` 防止并发构建。
2.  **防御性编程**: `LLMService.analyze_query` 对 LLM 返回的 Markdown 代码块进行了清洗。
3.  **去重逻辑**: `MovieRepository.save_all` 在插入前做了链接去重，防止重复数据。
4.  **重试机制**: `DoubanSpider._get` 实现了指数退避重试 (2s, 4s)。

---

## 六、优先修复建议

| 优先级 | 问题 | 工作量 |
| :--- | :--- | :--- |
| P0 | API Key 环境变量化 | 5 分钟 |
| P0 | 添加 `import re` | 1 分钟 |
| P1 | 删除重复 `_parse_json` 调用 | 1 分钟 |
| P1 | 删除调试 `print` 语句 | 2 分钟 |
| P2 | 拆分 app.py 为 Blueprint | 30 分钟 |

---

## 附录: 修复 Patch (可直接应用)

### Patch 1: 修复 vector_service.py 缺少 `import re`
```diff
 import os
 import pickle
 import threading 
 import numpy as np
+import re
 from typing import List, Dict, Tuple
```

### Patch 2: 删除 douban_spider.py 重复调用
```diff
                 batch = self._parse_json(content)
                 if not batch:
                     logger.info("No more data in response")
                     break
-                    
-                batch = self._parse_json(content)
-                if not batch:
-                    break
```
