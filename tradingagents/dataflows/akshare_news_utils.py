import akshare as ak
import pandas as pd
from typing import Annotated, List, Dict, Optional
from datetime import datetime, timedelta
from functools import wraps
import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)
try:
    from .utils import add_market_prefix, convert_symbol
except ImportError:
    from tradingagents.dataflows.utils import add_market_prefix, convert_symbol
    
def convert_symbol(func):
    """装饰器：转换股票代码格式"""
    @wraps(func)
    def wrapper(symbol: str, *args, **kwargs):
        # 移除可能的市场后缀
        symbol = symbol.split('.')[0]
        # 确保是6位数字
        if len(symbol) != 6:
            raise ValueError(f"Invalid A-share stock symbol: {symbol}")
        return func(symbol, *args, **kwargs)
    return wrapper

class AKShareNewsUtils:
    @staticmethod
    @convert_symbol
    def get_company_news(
        symbol: Annotated[str, "股票代码"],
        start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
        end_date: Annotated[str, "结束日期 YYYY-MM-DD"]
    ) -> List[Dict]:
        """获取公司相关新闻"""
        # 获取东方财富新闻
        try:
            df_em = ak.stock_news_em(symbol=symbol)
            df_em = df_em[
                (df_em['发布时间'] >= start_date) & 
                (df_em['发布时间'] <= end_date)
            ]
        except:
            df_em = pd.DataFrame()

        # 获取新浪财经新闻
        try:
            df_sina = ak.stock_news_sina(symbol=symbol)
            df_sina = df_sina[
                (df_sina['date'] >= start_date) & 
                (df_sina['date'] <= end_date)
            ]
        except:
            df_sina = pd.DataFrame()

        news_list = []
        
        # 处理东方财富新闻
        if not df_em.empty:
            for _, row in df_em.iterrows():
                news_list.append({
                    'date': row['发布时间'],
                    'title': row['新闻标题'],
                    'content': row['新闻内容'] if '新闻内容' in row else '',
                    'source': '东方财富',
                    'url': row['新闻链接'] if '新闻链接' in row else ''
                })

        # 处理新浪财经新闻
        if not df_sina.empty:
            for _, row in df_sina.iterrows():
                news_list.append({
                    'date': row['date'],
                    'title': row['title'],
                    'content': row['content'] if 'content' in row else '',
                    'source': '新浪财经',
                    'url': row['url'] if 'url' in row else ''
                })

        return sorted(news_list, key=lambda x: x['date'], reverse=True)

    @staticmethod
    @convert_symbol
    def get_company_announcements(
        symbol: Annotated[str, "股票代码"],
        start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
        end_date: Annotated[str, "结束日期 YYYY-MM-DD"]
    ) -> List[Dict]:
        """获取公司公告"""
        announcements = []
        
        # 转换日期格式从 YYYY-MM-DD 到 YYYYMMDD
        start_date_formatted = start_date.replace('-', '')
        end_date_formatted = end_date.replace('-', '')
        
        # 获取不同类型的公告
        # notice_types = ["全部", "重大事项", "财务报告", "融资公告", "风险提示"]
        notice_types = ["全部"]
        
        for notice_type in notice_types:
            try:
                # 获取指定类型的公告
                df = ak.stock_notice_report(symbol=notice_type, date=start_date_formatted)
                
                # 过滤日期范围
                if not df.empty and '公告日期' in df.columns:
                    df = df[
                        (df['公告日期'] >= pd.to_datetime(start_date).date()) & 
                        (df['公告日期'] <= pd.to_datetime(end_date).date())
                    ]
                    
                    # 添加到公告列表
                    for _, row in df.iterrows():
                        announcements.append({
                            'date': row['公告日期'],
                            'title': row['公告标题'],
                            'type': notice_type,
                            'url': row['公告链接'] if '公告链接' in row else ''
                        })
                        
            except Exception as e:
                print(f"获取{notice_type}类型公告失败: {str(e)}")
                continue

        return sorted(announcements, key=lambda x: x['date'], reverse=True)

    @staticmethod
    def get_market_news(
        start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
        end_date: Annotated[str, "结束日期 YYYY-MM-DD"]
    ) -> List[Dict]:
        """获取市场新闻"""
        try:
            # 获取财联社新闻
            df_cls = ak.stock_news_main_cx()
            df_cls = df_cls[
                (df_cls['pub_time'] >= start_date) & 
                (df_cls['pub_time'] <= end_date)
            ]
        except:
            df_cls = pd.DataFrame()

        try:
            # 获取东方财富财经新闻
            df_em = ak.stock_info_global_cls(symbol="全部")
            df_em = df_em[
                (df_em['发布日期'] >= start_date) & 
                (df_em['发布日期'] <= end_date)
            ]
        except:
            df_em = pd.DataFrame()

        news_list = []

        # 处理财联社新闻
        if not df_cls.empty:
            for _, row in df_cls.iterrows():
                news_list.append({
                    'date': row['pub_time'],
                    'title': row['tag'],
                    'content': row['summary'] if 'summary' in row else '',
                    'source': '财新网',
                    'url': row['url'] if 'url' in row else ''
                })

        # 处理东方财富新闻
        if not df_em.empty:
            for _, row in df_em.iterrows():
                news_list.append({
                    'date': row['发布日期'],
                    'title': row['标题'],
                    'content': row['内容'] if '内容' in row else '',
                    'source': '财联社-电报',
                    'url': row['链接'] if '链接' in row else ''
                })

        return sorted(news_list, key=lambda x: x['date'], reverse=True)

    @staticmethod
    def get_xueqiu_hot_stocks(
        count: Annotated[int, "获取的热门股票数量"] = 20
    ) -> List[Dict]:
        """获取雪球热门股票"""
        try:
            # 获取最热门股票
            df_hot = ak.stock_hot_tweet_xq(symbol="最热门")
            # 获取本周新增热门股票
            df_new = ak.stock_hot_tweet_xq(symbol="本周新增")
            
            hot_stocks = []
            
            # 处理最热门股票
            if not df_hot.empty:
                for _, row in df_hot.head(count//2).iterrows():
                    hot_stocks.append({
                        'symbol': row['股票代码'] if '股票代码' in row else '',
                        'name': row['股票简称'] if '股票简称' in row else '',
                        'attention': row['关注'] if '关注' in row else 0,
                        'latest_price': row['最新价'] if '最新价' in row else 0,
                        'type': '最热门'
                    })
            
            # 处理本周新增热门股票
            if not df_new.empty:
                for _, row in df_new.head(count//2).iterrows():
                    hot_stocks.append({
                        'symbol': row['股票代码'] if '股票代码' in row else '',
                        'name': row['股票简称'] if '股票简称' in row else '',
                        'attention': row['关注'] if '关注' in row else 0,
                        'latest_price': row['最新价'] if '最新价' in row else 0,
                        'type': '本周新增'
                    })
            
            return hot_stocks
            
        except Exception as e:
            print(f"获取热门股票失败: {str(e)}")
            return []

    @staticmethod
    @convert_symbol
    def get_xueqiu_discussions(
        symbol: Annotated[str, "股票代码"],
        count: Annotated[int, "获取的讨论数量"] = 20
    ) -> List[Dict]:
        """获取雪球讨论（保留原函数名以兼容现有代码）"""
        # 由于 stock_hot_tweet_xq 返回的是股票热度数据而不是讨论，
        # 这里返回空列表，或者可以考虑使用其他函数获取讨论数据
        print("注意：stock_hot_tweet_xq 返回的是股票热度数据，不是讨论内容")
        return []

    @staticmethod
    def format_news_report(
        news_list: List[Dict],
        announcements: List[Dict] = None,
        discussions: List[Dict] = None
    ) -> str:
        """格式化新闻报告"""
        report = []

        if news_list:
            report.append("## 相关新闻：")
            for news in news_list[:10]:  # 限制显示最新的10条
                report.append(f"\n### {news['date']} - {news['source']}")
                report.append(f"**{news['title']}**")
                if news.get('content'):
                    report.append(f"\n{news['content'][:200]}...")  # 限制内容长度
                if news.get('url'):
                    report.append(f"\n链接：{news['url']}")

        if announcements:
            report.append("\n## 公司公告：")
            for ann in announcements[:5]:  # 限制显示最新的5条
                report.append(f"\n### {ann['date']} - {ann.get('type', '公告')}")
                report.append(f"**{ann['title']}**")
                if ann.get('url'):
                    report.append(f"\n链接：{ann['url']}")

        if discussions:
            report.append("\n## 市场讨论：")
            for disc in discussions[:5]:  # 限制显示最新的5条
                report.append(f"\n### {disc['date']} - {disc['author']}")
                report.append(f"**{disc['title']}**")
                if disc.get('content'):
                    report.append(f"\n{disc['content'][:200]}...")  # 限制内容长度
                report.append(f"\n👍 {disc.get('likes', 0)} | 💬 {disc.get('comments', 0)}")

        return "\n".join(report) 

if __name__ == "__main__":
    # 设置显示选项
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_rows', 20)
    
    try:
        # 测试股票代码
        symbol = "600519"  # 贵州茅台
        curr_date = datetime.now()
        start_date = (curr_date - timedelta(days=30)).strftime("%Y-%m-%d")  # 30天前
        end_date = curr_date.strftime("%Y-%m-%d")  # 今天
        
        print("=== AKShareNewsUtils 测试 ===\n")
        
        # 1. 测试获取公司新闻
        print("1. 测试获取公司新闻...")
        try:
            company_news = AKShareNewsUtils.get_company_news(symbol, start_date, end_date)
            if company_news:
                print(f"✓ 成功获取公司新闻，共 {len(company_news)} 条")
                print("最新3条新闻:")
                for i, news in enumerate(company_news[:3]):
                    print(f"  {i+1}. [{news['date']}] {news['title']} ({news['source']})")
            else:
                print("ℹ 该时间段内没有找到公司新闻")
        except Exception as e:
            print(f"✗ 获取公司新闻失败: {str(e)}")
        
        # 2. 测试获取公司公告（重点测试）
        print("\n2. 测试获取公司公告...")
        try:
            announcements = AKShareNewsUtils.get_company_announcements(symbol, start_date, end_date)
            if announcements:
                print(f"✓ 成功获取公司公告，共 {len(announcements)} 条")
                print("最新5条公告:")
                for i, ann in enumerate(announcements[:5]):
                    print(f"  {i+1}. [{ann['date']}] [{ann['type']}] {ann['title']}")
                
                # 统计不同类型的公告
                type_counts = {}
                for ann in announcements:
                    ann_type = ann['type']
                    type_counts[ann_type] = type_counts.get(ann_type, 0) + 1
                
                print(f"\n公告类型统计:")
                for ann_type, count in type_counts.items():
                    print(f"  {ann_type}: {count} 条")
            else:
                print("ℹ 该时间段内没有找到公司公告")
        except Exception as e:
            print(f"✗ 获取公司公告失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
        
        # 3. 测试获取市场新闻
        print("\n3. 测试获取市场新闻...")
        try:
            market_news = AKShareNewsUtils.get_market_news(start_date, end_date)
            if market_news:
                print(f"✓ 成功获取市场新闻，共 {len(market_news)} 条")
                print("最新3条市场新闻:")
                for i, news in enumerate(market_news[:3]):
                    print(f"  {i+1}. [{news['date']}] {news['title']} ({news['source']})")
            else:
                print("ℹ 该时间段内没有找到市场新闻")
        except Exception as e:
            print(f"✗ 获取市场新闻失败: {str(e)}")
        
        # 4. 测试获取雪球讨论
        print("\n4. 测试获取雪球讨论...")
        try:
            hot_stocks = AKShareNewsUtils.get_xueqiu_hot_stocks()
            if hot_stocks:
                print(f"✓ 成功获取雪球讨论，共 {len(hot_stocks)} 条")
                print("最新3条讨论:")
                for i, stock in enumerate(hot_stocks[:3]):
                    print(f"  {i+1}. [{stock['date']}] {stock['title']} (作者: {stock['author']})")
                    print(f"     👍 {stock.get('likes', 0)} | 💬 {stock.get('comments', 0)}")
            else:
                print("ℹ 没有找到雪球讨论")
        except Exception as e:
            print(f"✗ 获取雪球讨论失败: {str(e)}")
        
        # 5. 测试格式化新闻报告
        print("\n5. 测试格式化新闻报告...")
        try:
            # 获取一些测试数据
            test_news = AKShareNewsUtils.get_company_news(symbol, start_date, end_date)
            test_announcements = AKShareNewsUtils.get_company_announcements(symbol, start_date, end_date)
            test_discussions = AKShareNewsUtils.get_xueqiu_discussions(symbol, count=5)
            
            # 格式化报告
            formatted_report = AKShareNewsUtils.format_news_report(
                news_list=test_news,
                announcements=test_announcements,
                discussions=test_discussions
            )
            
            if formatted_report:
                print("✓ 成功生成格式化新闻报告")
                print(f"报告长度: {len(formatted_report)} 字符")
                print("\n报告预览（前500字符）:")
                print(formatted_report[:500] + "..." if len(formatted_report) > 500 else formatted_report)
            else:
                print("ℹ 生成的报告为空")
        except Exception as e:
            print(f"✗ 格式化新闻报告失败: {str(e)}")
        
        # 6. 测试错误处理
        print("\n6. 测试错误处理...")
        try:
            # 测试无效股票代码
            invalid_symbol = "999999"
            invalid_news = AKShareNewsUtils.get_company_news(invalid_symbol, start_date, end_date)
            print(f"✓ 无效股票代码处理正常，返回 {len(invalid_news)} 条结果")
        except Exception as e:
            print(f"✓ 无效股票代码正确抛出异常: {str(e)}")
        
        # 7. 测试不同时间范围
        print("\n7. 测试不同时间范围...")
        try:
            # 测试更短的时间范围
            short_start = (curr_date - timedelta(days=7)).strftime("%Y-%m-%d")
            short_announcements = AKShareNewsUtils.get_company_announcements(symbol, short_start, end_date)
            print(f"✓ 7天时间范围测试正常，返回 {len(short_announcements)} 条公告")
            
            # 测试更长的时间范围
            long_start = (curr_date - timedelta(days=90)).strftime("%Y-%m-%d")
            long_announcements = AKShareNewsUtils.get_company_announcements(symbol, long_start, end_date)
            print(f"✓ 90天时间范围测试正常，返回 {len(long_announcements)} 条公告")
        except Exception as e:
            print(f"✗ 时间范围测试失败: {str(e)}")
        
        print("\n=== 测试完成 ===")
        
    except Exception as e:
        print(f"测试过程中出现错误: {str(e)}")
        import traceback
        print(traceback.format_exc()) 