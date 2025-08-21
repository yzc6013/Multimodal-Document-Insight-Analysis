import asyncio
import re
import datetime
import inspect
import json
import os
from docstring_parser import parse
from typing import List, Optional, Dict, Callable, Any
from decimal import Decimal
from fastmcp import Client as McpClient
import dashscope
from web.utils.analysis_runner import run_stock_analysis
import streamlit as st
import akshare as ak
import time
from volcenginesdkarkruntime import Ark

# 全局变量定义
ARK_API_KEY = "ebf28261-9b79-4a01-b4d6-62548914852d"
MULTIMODAL_MODEL = "doubao-seed-1-6-thinking-250715"


class ToolExecutor:
    """工具执行器，支持从多个MCP服务器URL获取并管理工具"""

    def __init__(self):
        """初始化工具执行器，从多个MCP服务器加载工具"""
        # 工具注册表，键为工具名称，值包含工具配置和来源URL
        self.tools = {
            '个股股票分析工具': {
                'type': 'local',
                'func': self.execute_stock_analysis_tool,
                'source': 'local'  # 标记本地工具
            },
            '基金分析工具': {
                'type': 'local',
                'func': self.execute_fund_analysis_tool,
                'source': 'local'  # 标记本地工具
            },
            '基金数据获取工具': {
                'type': 'local',
                'func': self.get_fund_data,
                'source': 'local'  # 新增基金数据获取工具
            },
            '基金历史行情数据获取工具': {
                'type': 'local',
                'func': self.get_fund_historical_data,
                'source': 'local'  # 新增基金历史行情数据获取工具
            },
            '机构经营情况分析工具': {
                'type': 'local',
                'func': self.deposit_analyze,
                'source': 'local'
            }
        }

        # MCP相关配置
        self.mcp_server_urls = self._load_mcp_server_urls()  # 所有MCP服务器URL列表
        self.mcp_tools = {}  # 存储MCP工具信息，包含来源URL
        self.available_mcp_urls = []  # 可用的MCP服务器URL

        # 从所有MCP服务器加载工具
        asyncio.run(self.initialize_all_mcp_servers())

    def _load_mcp_server_urls(self) -> List[str]:
        """从mcp.json加载所有有效的MCP服务器URL"""
        try:
            config_path = os.path.join(os.getcwd(), "planning", "mcp.json")

            if not os.path.exists(config_path):
                raise FileNotFoundError(f"mcp.json配置文件未找到，路径：{config_path}")

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            mcp_servers = config.get("mcpServers", {})
            if not mcp_servers:
                raise ValueError("mcp.json中未配置任何MCP服务器（mcpServers为空）")

            # 收集所有有效URL
            valid_urls = []
            for server_name, server_config in mcp_servers.items():
                if isinstance(server_config, dict) and "url" in server_config and server_config["url"]:
                    valid_urls.append({
                        "name": server_name,
                        "url": server_config["url"]
                    })
                    print(f"发现MCP服务器：{server_name}，URL：{server_config['url']}")

            if not valid_urls:
                raise ValueError("mcp.json中的所有MCP服务器配置均未包含有效的url")

            return valid_urls

        except Exception as e:
            # 异常时返回默认服务器配置
            default_config = [{
                "name": "default",
                "url": "https://data-api.investoday.net/data/mcp?apiKey=b04a7df2b76b489484335a26596dfab9"
            }]
            print(f"加载mcp.json失败：{str(e)}，将使用默认服务器：{default_config[0]['url']}")
            return default_config

    async def initialize_all_mcp_servers(self):
        """从所有MCP服务器加载工具"""
        # 为每个服务器创建任务
        tasks = [
            self._initialize_single_mcp(server["name"], server["url"])
            for server in self.mcp_server_urls
        ]

        # 并行执行所有初始化任务
        results = await asyncio.gather(*tasks)

        # 收集可用的服务器
        for result in results:
            if result["success"]:
                self.available_mcp_urls.append(result["url"])

        print(f"初始化完成，可用MCP服务器数量：{len(self.available_mcp_urls)}/{len(self.mcp_server_urls)}")

    async def _initialize_single_mcp(self, server_name: str, server_url: str) -> Dict[str, Any]:
        """初始化单个MCP服务器并加载工具"""
        try:
            print(f"开始初始化MCP服务器：{server_name}（{server_url}）")
            async with McpClient(server_url) as mcp_client:
                # 拉取工具列表
                tools = await mcp_client.list_tools()
                if not tools:
                    print(f"MCP服务器 {server_name} 未提供任何工具")
                    return {
                        "success": True,
                        "name": server_name,
                        "url": server_url,
                        "tool_count": 0
                    }

                # 注册工具并记录来源
                for tool in tools:
                    tool_name = tool.name
                    # 处理工具名称冲突：如果工具已存在，添加服务器名称作为后缀
                    if tool_name in self.tools:
                        original_name = tool_name
                        tool_name = f"{tool_name}@{server_name}"
                        print(f"工具名称冲突：{original_name} 已存在，重命名为 {tool_name}")

                    # 注册工具
                    self.tools[tool_name] = {
                        'type': 'mcp',
                        'tool_info': tool,
                        'source': server_name,
                        'url': server_url  # 记录工具所属的服务器URL
                    }

                    # 存储工具元信息
                    self.mcp_tools[tool_name] = {
                        "name": tool.name,
                        "description": (tool.description or "").strip(),
                        "parameters": tool.inputSchema,
                        "source": server_name,
                        "url": server_url
                    }

                print(f"成功从 {server_name} 加载 {len(tools)} 个工具")
                return {
                    "success": True,
                    "name": server_name,
                    "url": server_url,
                    "tool_count": len(tools)
                }

        except Exception as e:
            print(f"初始化MCP服务器 {server_name} 失败: {str(e)}")
            return {
                "success": False,
                "name": server_name,
                "url": server_url,
                "error": str(e)
            }

    def get_available_tools(self) -> List[str]:
        """获取所有可用工具的列表"""
        return list(self.tools.keys())

    @staticmethod
    def get_tool_metadata(tool_func):
        """提取工具函数的元信息"""
        tool_name = tool_func.__name__
        docstring = inspect.getdoc(tool_func) or ""
        parsed_doc = parse(docstring)
        tool_description = parsed_doc.short_description or "无描述"

        sig = inspect.signature(tool_func)
        parameters = []
        for param_name, param in sig.parameters.items():
            param_type = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "未指定"
            default_value = param.default if param.default != inspect.Parameter.empty else "必填"

            param_desc = ""
            for doc_param in parsed_doc.params:
                if doc_param.arg_name == param_name:
                    param_desc = doc_param.description or "无描述"
                    break

            parameters.append({
                "name": param_name,
                "type": param_type,
                "default": default_value,
                "description": param_desc
            })

        return {
            "name": tool_name,
            "description": tool_description,
            "parameters": parameters
        }

    def get_mcp_tool_metadata(self, tool_info):
        """提取MCP工具的元信息"""
        parameters = []
        if hasattr(tool_info, 'inputSchema') and tool_info.inputSchema:
            properties = tool_info.inputSchema.get('properties', {})
            required = tool_info.inputSchema.get('required', [])

            for param_name, param_details in properties.items():
                param_type = param_details.get('type', '未指定')
                param_desc = param_details.get('description', '无描述')
                default_value = param_details.get('default', '必填' if param_name in required else '可选')

                parameters.append({
                    "name": param_name,
                    "type": param_type,
                    "default": default_value,
                    "description": param_desc
                })

        return {
            "name": tool_info.name,
            "description": (tool_info.description or "无描述").strip(),
            "parameters": parameters
        }

    def generate_available_tools(self) -> str:
        """生成包含参数信息和来源的可用工具列表"""
        tool_list = []

        for idx, (tool_display_name, tool_config) in enumerate(self.tools.items(), 1):
            if tool_config['type'] == 'local':
                metadata = ToolExecutor.get_tool_metadata(tool_config['func'])
                source_info = "本地工具"
            else:
                metadata = self.get_mcp_tool_metadata(tool_config['tool_info'])
                source_info = f"远程MCP工具（来自 {tool_config['source']}）"

            tool_info = [
                f"{idx}. 工具名称：{tool_display_name}",
                f"   工具来源：{source_info}",
                f"   工具描述：{metadata['description']}",
                "   参数列表："
            ]
            for param in metadata["parameters"]:
                param_line = (
                    f"   - {param['name']}（类型：{param['type']}，"
                    f"默认值：{param['default']}）：{param['description']}"
                )
                tool_info.append(param_line)
            tool_list.append("\n".join(tool_info))

        return "# 可用工具列表（含参数说明）\n" + "\n\n".join(tool_list)

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """执行指定的工具"""
        if tool_name not in self.tools:
            return f"错误：未知工具 '{tool_name}'，无法执行。可用工具：{', '.join(self.get_available_tools())}"

        tool_config = self.tools[tool_name]

        try:
            if tool_config['type'] == 'local':
                # 执行本地工具
                tool_func = tool_config['func']
                sig = inspect.signature(tool_func)

                # 过滤有效参数
                valid_kwargs = {
                    k: v for k, v in parameters.items()
                    if k in sig.parameters
                }

                # 执行工具（区分同步/异步）
                if inspect.iscoroutinefunction(tool_func):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(tool_func(**valid_kwargs))
                    finally:
                        loop.close()
                    return result
                else:
                    return tool_func(**valid_kwargs)

            else:
                # 执行MCP远程工具，传入对应的服务器URL
                return asyncio.run(self.execute_mcp_tool(
                    tool_name, parameters, tool_config['url']
                ))

        except Exception as e:
            return f"执行工具 '{tool_name}' 时发生错误: {str(e)}"

    async def execute_mcp_tool(self, tool_name: str, tool_parameters: Dict[str, Any], server_url: str) -> str:
        """执行指定MCP服务器上的工具"""
        if tool_name not in self.mcp_tools:
            return f"错误：MCP工具 '{tool_name}' 不存在"

        try:
            # 使用工具对应的服务器URL连接
            async with McpClient(server_url) as mcp_client:
                # 调用MCP工具
                result = await mcp_client.call_tool(tool_name.split("@")[0], tool_parameters)  # 移除可能的后缀
                raw_result = result.content[0].text if result.content else ""
                if not raw_result:
                    return f"工具 {tool_name} 执行成功，但未返回任何结果"

            # 调用大模型处理结果
            ark = Ark(api_key=ARK_API_KEY)
            prompt = f"""
                请处理以下工具返回的原始数据，并生成一份清晰、结构化的分析报告：
                1. 提炼核心信息和关键指标
                2. 分析数据中存在的规律或问题
                3. 要保留所有的数据和内容
                4. 保持客观中立的态度

                原始数据：
                {raw_result}
            """

            resp = ark.chat.completions.create(
                model=MULTIMODAL_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            processed_result = resp.choices[0].message.content or "大模型处理失败，未返回结果"
            return processed_result

        except Exception as e:
            # 尝试其他可用服务器（如果有）
            alternative_urls = [url for url in self.available_mcp_urls if url != server_url]
            if alternative_urls:
                return await self._retry_with_alternative_server(
                    tool_name, tool_parameters, alternative_urls, str(e)
                )
            return f"执行MCP工具 '{tool_name}' 时发生错误: {str(e)}"

    async def _retry_with_alternative_server(self, tool_name: str, parameters: Dict[str, Any],
                                             alternative_urls: List[str], original_error: str) -> str:
        """使用备用服务器重试执行工具"""
        for url in alternative_urls:
            try:
                print(f"尝试使用备用服务器 {url} 执行工具 {tool_name}")
                async with McpClient(url) as mcp_client:
                    # 尝试调用工具（不检查工具是否存在于该服务器，直接调用）
                    result = await mcp_client.call_tool(tool_name.split("@")[0], parameters)
                    raw_result = result.content[0].text if result.content else ""

                    # 处理结果
                    ark = Ark(api_key=ARK_API_KEY)
                    prompt = f"请处理以下数据并生成报告：{raw_result}"
                    resp = ark.chat.completions.create(
                        model=MULTIMODAL_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )

                    processed_result = resp.choices[0].message.content or "大模型处理失败"
                    return f"注意：原服务器执行失败（{original_error}），已使用备用服务器 {url} 执行成功。\n\n{processed_result}"

            except Exception as e:
                print(f"备用服务器 {url} 执行工具 {tool_name} 失败: {str(e)}")
                continue

        return f"执行工具 '{tool_name}' 失败，原错误：{original_error}，所有备用服务器均尝试失败。"

    def execute_stock_analysis_tool(self, stock_symbols: List[str], ):
        """
        个股分析工具，支持批量分析个股。

        Args:
            stock_symbols: 股票代码列表（如 ["290012", "485119"]）

        Returns:
            整合后的股票分析报告，包含每只股票的市场、基本面等分析内容
        """
        llm_provider = st.session_state.llm_config.get('llm_provider', 'dashscope')
        llm_model = st.session_state.llm_config.get('llm_model', 'qwen-plus')

        all_analysis = []
        for code in stock_symbols:
            try:
                analysis_result = run_stock_analysis(
                    stock_symbol=code,
                    analysis_date=str(datetime.date.today()),
                    analysts=['fundamentals'],
                    research_depth=1,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    market_type='A股',
                )
            except Exception as e:
                all_analysis.append(f"### 个股分析: {code}\n分析失败：{str(e)}")
                continue

            raw_reports = []
            if 'state' in analysis_result:
                state = analysis_result['state']
                report_types = [
                    'market_report', 'fundamentals_report',
                    'sentiment_report', 'news_report',
                ]
                for report_type in report_types:
                    if report_type in state:
                        raw_reports.append(
                            f"#### {report_type.replace('_', ' ').title()}\n{state[report_type]}")

            decision_reasoning = ""
            if 'decision' in analysis_result and 'reasoning' in analysis_result['decision']:
                decision_reasoning = f"#### 核心决策结论\n{analysis_result['decision']['reasoning']}"

            full_raw_report = "\n\n".join(raw_reports + [decision_reasoning])
            all_analysis.append(
                f"### 个股分析: {code}\n{full_raw_report if full_raw_report else '无分析结果'}")

        return "\n\n".join(all_analysis)

    def get_fund_data(self, fund_symbol: str) -> str:
        """
        基金数据获取工具，用于获取基金的各类原始数据。

        Args:
            fund_symbol: 基金代码（如 "290012"）

        Returns:
            包含基金各类原始数据的文本，包括基本数据、基金评级、业绩表现等
        """
        # 构建报告头
        result = f"【基金代码】: {fund_symbol}\n"

        # 1. 基本数据
        try:
            basic_info = ak.fund_individual_basic_info_xq(symbol=fund_symbol)
            result += "【基本数据】:\n" + basic_info.to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【基本数据】获取失败: {str(e)}\n\n"

        # 2. 基金评级
        try:
            fund_rating_all_df = ak.fund_rating_all()
            result += "【基金评级】:\n" + fund_rating_all_df[
                fund_rating_all_df['代码'] == fund_symbol
                ].to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【基金评级】获取失败: {str(e)}\n\n"

        # 3. 业绩表现（前5条）
        try:
            achievement = ak.fund_individual_achievement_xq(symbol=fund_symbol)
            result += "【业绩表现】:\n" + achievement.head(5).to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【业绩表现】获取失败: {str(e)}\n\n"

        # 4. 净值估算（特殊处理全量请求）
        try:
            fund_value_df = ak.fund_value_estimation_em(symbol="全部")
            result += "【净值估算】:\n" + fund_value_df[
                fund_value_df['基金代码'] == fund_symbol
                ].to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【净值估算】获取失败: {str(e)}\n\n"

        # 5. 数据分析
        try:
            analysis = ak.fund_individual_analysis_xq(symbol=fund_symbol)
            result += "【数据分析】:\n" + analysis.to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【数据分析】获取失败: {str(e)}\n\n"

        # 6. 盈利概率
        try:
            profit_prob = ak.fund_individual_profit_probability_xq(symbol=fund_symbol)
            result += "【盈利概率】:\n" + profit_prob.to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【盈利概率】获取失败: {str(e)}\n\n"

        # 7. 持仓资产比例
        try:
            detail_hold = ak.fund_individual_detail_hold_xq(symbol=fund_symbol)
            result += "【持仓资产比例】:\n" + detail_hold.to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【持仓资产比例】获取失败: {str(e)}\n\n"

        # 8. 行业配置（2025年数据）
        try:
            industry_alloc = ak.fund_portfolio_industry_allocation_em(symbol=fund_symbol, date="2025")
            result += "【行业配置】:\n" + industry_alloc.to_string(index=False) + "\n\n"
            time.sleep(1)
        except Exception as e:
            result += f"【行业配置】获取失败: {str(e)}\n\n"

        # 9. 基金持仓（2025年数据）
        try:
            portfolio_hold = ak.fund_portfolio_hold_em(symbol=fund_symbol, date="2025")
            result += "【基金持仓】:\n" + portfolio_hold.to_string(index=False) + "\n"
            time.sleep(1)
        except Exception as e:
            result += f"【基金持仓】获取失败: {str(e)}\n"

        print(result)
        return result

    def get_fund_historical_data(self, fund_symbol: str, indicator: str = "单位净值走势",
                                 period: str = "成立来") -> str:
        """
        基金历史行情数据获取工具，用于获取开放式基金的各类历史数据。

        Args:
            fund_symbol: 基金代码（如 "710001"）
            indicator: 要获取的指标类型，可选值包括：
                "单位净值走势"、"累计净值走势"、"累计收益率走势"、
                "同类排名走势"、"同类排名百分比"、"分红送配详情"、"拆分详情"
            period: 时间段参数，仅对"累计收益率走势"有效，可选值包括：
                "1月", "3月", "6月", "1年", "3年", "5年", "今年来", "成立来"

        Returns:
            包含基金指定历史数据的文本
        """
        # 构建报告头
        result = f"【基金代码】: {fund_symbol}\n【指标类型】: {indicator}\n"
        if indicator == "累计收益率走势":
            result += f"【时间段】: {period}\n"

        try:
            # 使用akshare获取基金历史数据
            fund_data = ak.fund_open_fund_info_em(
                symbol=fund_symbol,
                indicator=indicator,
                period=period
            )
            result += f"【历史数据】:\n{fund_data.to_string(index=False)}"
        except Exception as e:
            result += f"【数据获取失败】: {str(e)}"

        return result

    def _run_fund_analysis(self, fund_symbol):
        # 调用新的基金数据获取工具获取数据
        result = self.get_fund_data(fund_symbol)

        system_message = (
            f"你是一位专业的基金基本面分析师。\n"
            f"任务：对（基金代码：{fund_symbol}）进行全面基本面分析\n"
            "📊 **强制要求：**\n"
            "按以下框架输出结构化报告：\n\n"

            "### 一、基金产品基础分析\n"
            "- **基金公司实力**：管理规模排名、权益投资能力评级、风控体系完善度\n"
            "- **基金经理**：从业年限、历史年化回报、最大回撤控制能力（近3年）、投资风格稳定性\n"
            "- **产品特性**：基金类型(股票/混合/债券)、运作方式(开放式/封闭式)、规模变动趋势(警惕＜1亿清盘风险)\n"
            "- **费率结构**：管理费+托管费总成本、浮动费率机制(如有)、申购赎回费率\n\n"

            "### 二、风险收益特征分析\n"
            "- **核心指标**：\n"
            "  • 夏普比率(＞1为优)、卡玛比率(年化收益/最大回撤，＞0.5合格)\n"
            "  • 波动率(同类排名后30%为佳)、下行捕获率(＜100%表明抗跌)\n"
            "- **极端风险控制**：\n"
            "  • 最大回撤率(数值绝对值越小越好)及修复时长\n"
            "  • 股灾/熊市期间表现(如2022年回撤幅度 vs 沪深300)\n\n"

            "### 三、长期业绩评估\n"
            "- **收益维度**：\n"
            "  • 3年/5年年化收益率(需扣除费率)、超额收益(Alpha)\n"
            "  • 业绩持续性：每年排名同类前50%的年份占比\n"
            "- **基准对比**：\n"
            "  • 滚动3年跑赢业绩比较基准的概率\n"
            "  • 不同市场环境适应性(如2023成长牛 vs 2024价值修复行情表现)\n\n"

            "### 四、综合价值评估\n"
            "- **持仓穿透估值**：\n"
            "  • 股票部分：前十大重仓股PE/PB分位数(行业调整后)\n"
            "  • 债券部分：信用债利差水平、利率债久期风险\n"
            "- **组合性价比**：\n"
            "  • 股债净资产比价(E/P - 10年国债收益率)\n"
            "  • 场内基金需分析折溢价率(＞1%警惕高估)\n"
            f"- **绝对价值锚点**：给出合理净值区间依据：\n"
            "  当前净值水平 vs 历史波动区间(30%分位以下为低估)\n\n"

            "### 五、投资决策建议\n"
            "- **建议逻辑**：\n"
            "  • 综合夏普比率＞1.2+卡玛比率＞0.7+净值处30%分位→'买入'\n"
            "  • 规模激增(＞100亿)+重仓股估值＞70%分位→'减持'\n"
            "- **强制输出**：中文操作建议(买入/增持/持有/减持/卖出)\n"

            "🚫 **禁止事项**：\n"
            "- 禁止假设数据\n"
            "- 禁止使用英文建议(buy/sell/hold)\n"
        )

        user_prompt = (f"你现在拥有以下基金的真实数据，请严格依赖真实数据（注意！每条数据必须强制利用到来进行分析），"
                       f"绝不编造其他数据，对（基金代码：{fund_symbol}）进行全面分析，给出非常详细格式化的报告:\n")
        user_prompt += result

        messages = [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': user_prompt}
        ]
        # 使用volcenginesdkarkruntime的Ark客户端调用模型
        client = Ark(api_key=ARK_API_KEY)
        completion = client.chat.completions.create(
            model=MULTIMODAL_MODEL,
            messages=messages
        )

        # 获取并返回模型响应
        response_content = completion.choices[0].message.content
        print(response_content)

        return response_content

    def execute_fund_analysis_tool(self, fund_symbols: List[str]):
        """
        基金分析工具，支持批量分析基金。

        Args:
            fund_symbols: 基金代码列表（如 ["290012", "485119"]）

        Returns:
            整合后的基金分析报告，包含每只基金的市场、基本面等分析内容。
        """
        all_analysis = []

        for i, code in enumerate(fund_symbols, 1):
            try:
                # 执行基金分析
                analysis_result = self._run_fund_analysis(
                    fund_symbol=code)
            except Exception as e:
                all_analysis.append(f"### 基金分析: {code}\n分析失败：{str(e)}")
                continue

            all_analysis.append(
                f"### 基金分析: {code}\n{analysis_result if analysis_result else '无分析结果'}")

        return "\n\n".join(all_analysis)

    def _format_row(self, row: dict) -> str:
        return (
            f"{row['机构']} 在 {row['指标日期']} "
            f"的 {row['指标名']}（指标ID={row['指标ID']}）"
            f" 余额为 {row['指标值']} 元"
        )

    async def deposit_analyze(self, deposit_id: str) -> str:
        """
           这是一个专门分析机构运营情况的工具，可以根据机构名称查询机构其他指标信息分析机构运营情况。
           Args:
                deposit_id: 机构名称
           Returns:
               str: 包含机构运营情况分析结果的格式化报告
        """
        if deposit_id is None:
            return "机构名称为空"

        try:
            # 注意：此处使用了硬编码的MCP地址，如需统一管理可改为从可用服务器列表中选择
            async with McpClient("http://localhost:3000/sse") as mcp:
                ark = Ark(api_key=ARK_API_KEY)
                PROMPT = (
                    "你是一位专业的机构情况分析师，擅长提炼、总结、分析机构金融业务的关键信息。"
                    "任务：分析机构情况记录（{data}）。"
                    "要求输出一份报告，分为三部分：整体经营情况、具体分析、存在问题和建议。"
                    "具体分析需进行数据对比，可从下辖机构、较同期、较上月、较上日等角度进行。"
                    "必须严格依据数据中的信息进行分析，明确引用数据，确保真实性和准确性。"
                    "逻辑清晰，语句通顺，用词专业，客观中立，使用中文。"
                )
                raw = await mcp.call_tool("get_deposit_by_id", {"deposit_id": deposit_id})
                rows = json.loads(raw.content[0].text)["results"]

                for r in rows:
                    if isinstance(r.get("存款数"), Decimal):
                        r["存款数"] = float(r["存款数"])

                data_summary = "\n".join(self._format_row(r) for r in rows)
                resp = ark.chat.completions.create(
                    model=MULTIMODAL_MODEL,
                    messages=[{"role": "user", "content": PROMPT.format(data=data_summary)}],
                    temperature=0.1
                )
                return resp.choices[0].message.content or "分析失败"
        except Exception as e:
            print("Error while using mcp:", e)
            return f"分析失败: {str(e)}"
