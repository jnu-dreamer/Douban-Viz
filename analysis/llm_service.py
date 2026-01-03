
import os
import requests
import json
from utils.logger import logger

class LLMService:
    def __init__(self, api_key: str = None, base_url: str = "https://api.deepseek.com/v1", model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model 
        
    def generate_answer(self, query: str, context_movies: list, requirements: str = "") -> str:
        """
        根据检索到的电影信息和用户特定要求，生成回复。
        """
        if not self.api_key:
            return "AI 助手：由于尚未配置 API Key，我目前只能为您展示搜索结果，无法进行详细对话。"
            
        # 构建 Prompt
        movie_context = ""
        for i, m in enumerate(context_movies):
            movie_context += f"{i+1}. 《{m['title']}》 (评分:{m['score']}): {m['intro']}\n"
            
        requirement_part = f"\n用户特定要求：{requirements}" if requirements else ""
            
        prompt = f"""
你是一个资深的电影评论家和推荐助手。
用户的问题是："{query}"
{requirement_part}

以下是系统中检索到的相关电影资料：
{movie_context}

请结合这些资料和用户要求进行回答。你需要：
1. 语气亲切、专业。
2. 简要点评这些电影为什么符合用户的要求。
3. 如果资料中没有完全符合的，请诚实说明。

回答要求简洁有力，不要超过 300 字。
        """
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的电影推荐助手。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return f"AI 助手：对话生成失败（{str(e)}），但为您找到了以下电影..."

    def analyze_query(self, query: str) -> dict:
        """
        分析用户问题，拆分为：
        1. keywords: 向量检索核心词
        2. requirements: 回答风格要求
        3. filters: 结构化过滤条件 (Metadata Filtering)
        """
        if not self.api_key:
            return {"keywords": query, "requirements": "", "filters": {}}
            
        prompt = f"""
分析以下电影搜索问句，提取出三个部分：
1. keywords: 核心搜索词（去除时间、地点限制后的语义词），用空格分隔。
2. requirements: 用户提出的特定要求（如：字数限制、口吻要求、对比要求等）。如果不涉及则留空。
3. filters: 结构化过滤条件字典。支持以下字段：
   - year_min (int): 起始年份
   - year_max (int): 结束年份
   - country (str): 国家/地区 (如 "美国", "中国")
   - category (str): 电影标准类型 (仅限：剧情, 喜剧, 动作, 爱情, 科幻, 动画, 悬疑, 惊悚, 恐怖, 犯罪, 音乐, 歌舞, 传记, 历史, 战争, 西部, 奇幻, 冒险, 灾难, 武侠)。**警告：不要将"梦境"、"时间"等剧情关键词放入此处，应放入 keywords。**
   - director (str): 导演姓名 (如 "诺兰", "姜文")
   - actor (str): 演员姓名 (如 "成龙", "小李子")
   如果不涉及某项过滤，不要包含该字段。

例子1：
用户："推荐几部90年代成龙主演的动作片"
输出：{{"keywords": "动作", "requirements": "", "filters": {{"year_min": 1990, "year_max": 1999, "category": "动作", "actor": "成龙"}}}}

例子2 (剧情关键词)：
用户："推荐几部关于梦境的电影"
输出：{{"keywords": "梦境", "requirements": "", "filters": {{}}}}

用户问句："{query}"

请直接输出 JSON 格式。
        """
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个查询分析专家。只需输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            res_content = response.json()['choices'][0]['message']['content'].strip()
            # 兼容有些模型会带 markdown 代码块的情况
            if "```json" in res_content:
                res_content = res_content.split("```json")[1].split("```")[0].strip()
            elif "```" in res_content:
                res_content = res_content.split("```")[1].split("```")[0].strip()
                
            data = json.loads(res_content)
            logger.info(f"Query Analysis: {data}")
            
            # Ensure filters exists
            if "filters" not in data:
                data["filters"] = {}
                
            return data
        except Exception as e:
            logger.warning(f"Query analysis failed: {e}, fallback to original query.")
            return {"keywords": query, "requirements": "", "filters": {}}
