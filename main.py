import argparse
import os

from spider.douban_spider import DoubanSpider
from storage.repository import MovieRepository
from utils.logger import logger


def ensure_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def run_crawl(
    base_url: str,
    tag: str,
    pages: int,
    limit: int,
    delay: float,
    db_path: str,
    clear: bool = True,
    target_table: str = "movies",
    sort: str = "recommend",
    verbose: bool = True,
    progress_callback = None,
    start: int = 0
) -> None:
    # Determine table name based on logic
    # 逻辑现在由外部（args）控制，这里直接用 target_table
    table_name = target_table
    if not table_name: # Fallback
        table_name = "movies"
        if tag and not clear:
            table_name = f"movies_{tag}"
    
    ensure_dir(db_path)
    repo = MovieRepository(db_path, table_name)
    
    if clear:
        repo.clear_table()
    else:
        repo.create_table_if_not_exists()

    # Define incremental save callback
    def _save_chunk(chunk):
        saved_count = repo.save_all(chunk)
        if verbose:
            logger.info(f"  [Saved {saved_count} records]")

    spider = DoubanSpider(base_url=base_url, tag=tag, sort=sort, pages=pages, limit=limit, delay=delay, start=start)
    movies = spider.fetch(progress_callback, save_callback=_save_chunk)
    
    if verbose:
        logger.info(f"Fetched total {len(movies)} movies from {spider.base_url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="豆瓣电影爬虫工具")
    
    # 模式选择
    parser.add_argument("--type", type=str, choices=["top250", "tag"], default="top250", 
                        help="爬取模式: 'top250' (默认) 或 'tag' (按标签分类).")
    
    parser.add_argument("--tag", type=str, default="", help="指定电影类型 (当 mode='tag' 时必填), 例如 '喜剧'")
    parser.add_argument("--sort", type=str, default="recommend", choices=["recommend", "rank", "time"], help="排序方式: recommend (推荐), rank (高分), time (时间)")
    
    # 通用选项
    parser.add_argument("--pages", type=int, default=10, help="爬取页数 (默认: 10). Top 250共10页.")
    parser.add_argument("--limit", type=int, default=200, help="爬取数量 (仅当 mode='tag' 时生效, 默认: 200).")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔 (秒)")
    parser.add_argument("--db", type=str, default=os.path.join("data", "movie.db"), help="数据库保存路径")
    parser.add_argument("--table", type=str, default="", help="指定数据表名 (默认: movies, 或根据 tag 自动生成)")
    parser.add_argument("--append", action="store_true", help="追加模式: 如果表存在，不清空数据直接追加 (默认: 每次爬取前清空)")
    parser.add_argument("--start", type=int, default=0, help="从第几部开始爬取 (默认: 0)")
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    # 准备基础URL与模式
    base_url = "https://movie.douban.com/top250"
    tag_arg = ""
    
    if args.type == "tag":
        if not args.tag:
            logger.error("请指定电影类型 (当 mode='tag' 时必填), 例如 '喜剧'")
            logger.error("python main.py --type tag --tag 喜剧")
            exit(1)
        # 使用 JSON API, base_url 由 spider 内部处理
        base_url = "JSON_API" 
        tag_arg = args.tag
    elif args.type == "top250":
        pass # 默认模式
        
    logger.info(f"开始爬取... 模式: {args.type}, 起点: {args.start}, 页数: {args.pages}")
    
    # 决定表名
    final_table = "movies"
    if args.table:
        final_table = args.table
    elif args.type == "tag" and not args.append:
        # 旧逻辑兼容:如果是 tag 模式且非追加，默认分表(可选，但用户现在更想指定表)
        pass 

    # 现在的逻辑：
    # 1. 优先用 --table
    # 2. 没指定 table，默认是 "movies"
    
    run_crawl(
        base_url=base_url,
        tag=tag_arg,
        pages=args.pages,
        limit=args.limit,
        delay=args.delay,
        db_path=args.db,
        clear=not args.append, # 追加模式 = 不清空
        target_table=final_table, # 传递表名
        sort=args.sort,
        verbose=True,
        start=args.start # 传递 start
    )
