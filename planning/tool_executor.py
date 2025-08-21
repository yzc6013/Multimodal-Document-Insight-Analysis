import asyncio
import re
import datetime
import inspect
from docstring_parser import parse
from typing import List, Optional, Dict, Callable, Annotated
import datetime
import json
import time
import os
from decimal import Decimal
from fastmcp import Client as McpClient
import dashscope
from web.utils.analysis_runner import run_stock_analysis
import streamlit as st


class ToolExecutor:
    """工具执行器，用于管理和执行各种分析工具"""

    def __init__(self):
        """初始化工具执行器，注册所有可用工具"""
        # 工具注册表，键为工具名称，值为对应的执行方法
        self.tools = {
            '个股股票分析工具': self.execute_stock_analysis_tool,
            '机构经营情况分析工具': self.deposit_analyze
            # 在这里添加新工具，格式: '工具名称': 执行方法
        }

    def get_available_tools(self):
        """获取所有可用工具的列表"""
        return list(self.tools.keys())

    @staticmethod
    def get_tool_metadata(tool_func):
        """提取工具函数的元信息（名称、描述、参数列表）"""
        # 1. 基础信息：函数名和 docstring 摘要
        tool_name = tool_func.__name__
        docstring = inspect.getdoc(tool_func) or ""
        parsed_doc = parse(docstring)  # 解析docstring
        tool_description = parsed_doc.short_description or "无描述"

        # 2. 提取参数信息：结合函数签名和docstring参数描述
        sig = inspect.signature(tool_func)  # 获取函数签名
        parameters = []
        for param_name, param in sig.parameters.items():
            # 从签名中获取参数类型、默认值
            param_type = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "未指定"
            default_value = param.default if param.default != inspect.Parameter.empty else "必填"

            # 从docstring中获取参数描述（适配Google风格的Args）
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

    def generate_available_tools(self):
        """生成包含参数信息的可用工具列表"""
        # 修复：获取工具函数而不是工具名称字符串
        tool_list = []

        # 枚举所有工具（名称和对应的函数）
        for idx, (tool_display_name, tool_func) in enumerate(self.tools.items(), 1):
            metadata = ToolExecutor.get_tool_metadata(tool_func)
            # 格式化工具基本信息
            tool_info = [
                f"{idx}. 工具名称：{tool_display_name}",  # 使用显示名称
                f"   工具描述：{metadata['description']}",
                "   参数列表："
            ]
            # 格式化参数信息
            for param in metadata["parameters"]:
                param_line = (
                    f"   - {param['name']}（类型：{param['type']}，"
                    f"默认值：{param['default']}）：{param['description']}"
                )
                tool_info.append(param_line)
            tool_list.append("\n".join(tool_info))

        return "# 可用工具列表（含参数说明）\n" + "\n\n".join(tool_list)

    def execute(self, tool_name, parameters):
        """
        执行指定的工具

        Args:
            tool_name: 工具名称
            parameters: 工具参数

        Returns:
            工具执行结果报告
        """
        if tool_name not in self.tools:
            return f"错误：未知工具 '{tool_name}'，无法执行。可用工具：{', '.join(self.get_available_tools())}"

        tool_parameters = parameters.get('tool_parameters', None)
        step_content = parameters.get('step_content', '')
        progress_callback = parameters.get('progress_callback', None)

        tool_func = self.tools[tool_name]
        # 调用对应的工具执行方法
        try:
            # 检查工具函数是否为异步函数
            if inspect.iscoroutinefunction(tool_func):
                # 为异步函数创建事件循环并执行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        tool_func(tool_parameters, step_content, progress_callback)
                    )
                finally:
                    loop.close()
                return result
            else:
                # 同步函数直接调用
                return tool_func(tool_parameters, step_content, progress_callback)
        except Exception as e:
            return f"执行工具 '{tool_name}' 时发生错误: {str(e)}"

    def _extract_stock_symbols(self, parameters: List, step_content: str) -> List[str]:
        """从参数或步骤文本中提取6位数字的股票代码"""
        candidates = []

        if parameters is None:
            parameters = []

        # 1. 从parameters中提取（优先）
        if isinstance(parameters, list):
            candidates.extend([str(code) for code in parameters])
        else:
            candidates.append(str(parameters))  # 支持单个代码的情况

        # 2. 从step_content中提取（补充）
        if not candidates and step_content:
            candidates.append(step_content)

        # 3. 过滤有效代码（6位数字）
        valid_codes = list(set(re.findall(r"\b\d{6}\b", ",".join(candidates))))  # 去重+匹配6位数字
        return sorted(valid_codes)  # 排序后返回

    def execute_stock_analysis_tool(
            self,
            tool_parameters: List[str],
            step_content: str,
            progress_callback: Optional[Callable[[str, float], None]] = None
    ):
        """
        个股股票分析工具，支持批量分析股票。

        Args:
            tool_parameters: 股票代码列表（如 ["600000", "600036"]）
            step_content: 步骤描述文本，若parameters中无股票代码，将从文本中提取6位数字代码
            progress_callback: 进度回调函数，接收两个参数：进度信息（str）和进度值（0-1的float）

        Returns:
            整合后的股票分析报告，包含每只股票的市场、基本面等分析内容
        """
        # 提取股票代码
        stock_symbols = self._extract_stock_symbols(tool_parameters, step_content)
        if not stock_symbols:
            return "错误：未找到有效的A股股票代码（需为6位数字），无法执行分析。"

        # 获取LLM配置
        llm_provider = st.session_state.llm_config.get('llm_provider', 'dashscope')
        llm_model = st.session_state.llm_config.get('llm_model', 'qwen-plus')

        all_analysis = []
        total = len(stock_symbols)

        for i, code in enumerate(stock_symbols, 1):
            # 进度反馈
            if progress_callback:
                progress = i / total
                progress_callback(f"正在分析股票 {code}（{i}/{total}）", progress)

            try:
                # 执行股票分析
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

            # 处理分析结果
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

            # 添加决策推理
            decision_reasoning = ""
            if 'decision' in analysis_result and 'reasoning' in analysis_result['decision']:
                decision_reasoning = f"#### 核心决策结论\n{analysis_result['decision']['reasoning']}"

            # 整合报告
            full_raw_report = "\n\n".join(raw_reports + [decision_reasoning])
            all_analysis.append(
                f"### 个股分析: {code}\n{full_raw_report if full_raw_report else '无分析结果'}")

        return "\n\n".join(all_analysis)

    def _format_row(self, row: dict) -> str:
        """把单条记录格式化成一句话"""
        return (
            f"{row['机构']} 在 {row['指标日期']} "
            f"的 {row['指标名']}（指标ID={row['指标ID']}）"
            f" 余额为 {row['指标值']} 元"
        )

    async def deposit_analyze(
            self,
            tool_parameters: str,
            step_content: str,
            progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """
           这是一个专门分析机构运营情况的工具，可以根据机构名称查询机构其他指标信息分析机构运营情况。
           Args:
                tool_parameters: 机构名称
                step_content: 步骤描述文本，若parameters中无机构名称，将从文本中提取其他名称
                progress_callback: 进度回调函数，接收两个参数：进度信息（str）和进度值（0-1的float）
           Returns:
               str: 包含机构运营情况分析结果的格式化报告
           """
        if tool_parameters is None:
            return "机构名称为空"

        try:
            async with McpClient("http://localhost:3000/sse") as mcp:
                MODEL = "doubao-seed-1-6-flash-250715"
                ARK_API_KEY = "ebf28261-9b79-4a01-b4d6-62548914852d"

                PROMPT = (
                    "你是一位专业的机构情况分析师，你很擅长:提炼、总结、分析机构金融业务的关键信息，掌握代发指标的分析逻辑，并结合指标数据，公正客观的描述。"
                    "任务：分析机构情况记录（{data}）。🔴立即调用 get_deposit_by_id 工具。"
                    "整体经营情况;从指标日期、指标值等说明本机构整体经营情况。"
                    "📊要求输出一份报告，报告分为三部分，包括整体经营情况、具体分析、存在问题和建议。"
                    "具体分析进行数据对比，可以根据数据从下辖机构、较同期、较上月、较上日等角度进行对比。"
                    "存在问题和建议:针对上述分析数据，如果有特别异常的数据可以说明，并给出可行的建议。"
                    "必须严格依据数据中的信息进行分析，不能虚构或假设数据，必须明确引用数据中的信息，确保数据的真实性和准确性。"
                    "逻辑要清晰，语句要通顺，逐步思考，深度挖掘数据体现的企业经营能力，用词专业，客观中立。"
                    "🚫禁止假设、英文、编造；✅必须用中文。"
                )
                raw = await mcp.call_tool("get_deposit_by_id", {"deposit_id": tool_parameters})
                rows = json.loads(raw.content[0].text)["results"]
                print(rows)
                # 将 Decimal 转成 float，防止大模型解析报错
                for r in rows:
                    if isinstance(r.get("存款数"), Decimal):
                        r["存款数"] = float(r["存款数"])

                # 拼成多行文字
                data_summary = "\n".join(self._format_row(r) for r in rows)

                from volcenginesdkarkruntime import Ark
                ark = Ark(api_key=ARK_API_KEY)
                resp = ark.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": PROMPT.format(data=data_summary)}],
                    temperature=0.1
                )
                print(resp.choices[0].message.content)
                return resp.choices[0].message.content or "分析失败"
        except Exception as e:
            print("Error while using mcp:", e)
