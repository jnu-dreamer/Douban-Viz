import re
from collections import defaultdict
from storage.repository import MovieRepository

class GraphService:
    def __init__(self, repo: MovieRepository):
        self.repo = repo

    def _split_names(self, text):
        if not text:
            return []
        # 分割名字，支持空格、斜杠、逗号等常见分隔符
        # 移除括号内的外文名 (e.g. "张国荣 (Leslie Cheung)")
        text = re.sub(r'\(.*?\)|（.*?）', '', text)
        names = re.split(r'[ /:：,，]', text)
        return [n.strip() for n in names if n.strip() and len(n.strip()) > 1] # 过滤单字名

    def build_graph(self, limit_nodes=80):
        # 1. 获取所有电影数据
        movies = self.repo.get_all_movies()
        
        # 统计频次 (用于决定节点大小和筛选 Top N)
        person_counts = defaultdict(int)
        person_type = {} # 记录是导演还是演员 {name: 'director'/'actor'}
        
        # 合作关系 (Links)
        collaborations = defaultdict(int) 

        for m in movies:
            directors = self._split_names(m[10]) # col 10: director
            actors = self._split_names(m[11])    # col 11: actor
            
            # 记录节点权重
            for d in directors:
                person_counts[d] += 1
                person_type[d] = 'director' # 优先标记为导演
            for a in actors:
                person_counts[a] += 1
                if a not in person_type: # 如果既导又演，优先算导演
                    person_type[a] = 'actor'
            
            # 建立导演-演员关系
            for d in directors:
                for a in actors:
                    if d == a: continue # 排除自己和自己
                    # 排序以保证 A-B 和 B-A 是同一条边
                    edge = tuple(sorted([d, a]))
                    collaborations[edge] += 1
            
            # 建立演员-演员关系(仅限每部戏前3位主演，防止网络过密)
            top_actors = actors[:3]
            for i in range(len(top_actors)):
                for j in range(i+1, len(top_actors)):
                    edge = tuple(sorted([top_actors[i], top_actors[j]]))
                    collaborations[edge] += 1

        # 2. 筛选 Top N 活跃人物 (保留大V)
        top_people = sorted(person_counts.items(), key=lambda x: x[1], reverse=True)[:limit_nodes]
        valid_people_set = set([p[0] for p in top_people])

        # 3. 构建 ECharts 数据结构
        nodes = []
        categories = [{"name": "导演"}, {"name": "演员"}]
        
        for name, count in top_people:
            role = person_type.get(name, 'actor')
            cat_idx = 0 if role == 'director' else 1
            
            # 节点大小：基础大小 10 + 频次 * 3
            size = 10 + (count * 3)
            size = min(size, 60) # 封顶
            
            nodes.append({
                "id": name,
                "name": name,
                "value": count, # 出现次数
                "symbolSize": size,
                "category": cat_idx,
                "draggable": True
            })

        links = []
        for (p1, p2), weight in collaborations.items():
            # 只有当两个人都存在于 Top N 中时才建立连线 (或者至少有1个大V? 这里采用严格策略保证图的整洁)
            if p1 in valid_people_set and p2 in valid_people_set:
                links.append({
                    "source": p1,
                    "target": p2,
                    "value": weight, # 合作次数
                    "lineStyle": {
                        "width": min(1 + weight, 8) # 合作越多线条越粗
                    }
                })

        return {
            "nodes": nodes,
            "links": links,
            "categories": categories
        }
