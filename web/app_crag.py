#!/usr/bin/env python3
"""
TradingAgents-CN Streamlit Web界面
基于Streamlit的股票分析Web应用程序，添加了多模态图片、PDF和网页分析功能
"""

import streamlit as st
import os
import sys
from pathlib import Path
import datetime
import time
import re
import json
from dotenv import load_dotenv

# 多模态相关库
from PIL import Image
import io
import base64

# 网页截图相关库
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import numpy as np
from PIL import Image as PILImage

# 引入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger('web')

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env", override=True)

# 引入官方SDK
try:
    from volcenginesdkarkruntime import Ark

    has_ark_sdk = True
except ImportError:
    logger.warning("volcenginesdkarkruntime not installed, multimodal features will be disabled")
    has_ark_sdk = False

# 导入自定义组件
from components.sidebar import render_sidebar
from components.header import render_header
from components.analysis_form import render_analysis_form
from components.results_display import render_results
from utils.api_checker import check_api_keys
from utils.analysis_runner import run_stock_analysis, validate_analysis_params, format_analysis_results
from utils.progress_tracker import SmartStreamlitProgressDisplay, create_smart_progress_callback
from utils.async_progress_tracker import AsyncProgressTracker
from components.async_progress_display import display_unified_progress
from utils.smart_session_manager import get_persistent_analysis_id, set_persistent_analysis_id

# 设置页面配置
st.set_page_config(
    page_title="TradingAgents-CN 股票分析平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None
)

# 多模态模型配置 - 使用指定模型
MULTIMODAL_MODEL = "doubao-seed-1-6-thinking-250715"

# 自定义CSS样式
st.markdown("""
<style>
    /* 隐藏Streamlit顶部工具栏和Deploy按钮 - 多种选择器确保兼容性 */
    .stAppToolbar {
        display: none !important;
    }

    header[data-testid="stHeader"] {
        display: none !important;
    }

    .stDeployButton {
        display: none !important;
    }

    /* 新版本Streamlit的Deploy按钮选择器 */
    [data-testid="stToolbar"] {
        display: none !important;
    }

    [data-testid="stDecoration"] {
        display: none !important;
    }

    [data-testid="stStatusWidget"] {
        display: none !important;
    }

    /* 隐藏整个顶部区域 */
    .stApp > header {
        display: none !important;
    }

    .stApp > div[data-testid="stToolbar"] {
        display: none !important;
    }

    /* 隐藏主菜单按钮 */
    #MainMenu {
        visibility: hidden !important;
        display: none !important;
    }

    /* 隐藏页脚 */
    footer {
        visibility: hidden !important;
        display: none !important;
    }

    /* 隐藏"Made with Streamlit"标识 */
    .viewerBadge_container__1QSob {
        display: none !important;
    }

    /* 隐藏所有可能的工具栏元素 */
    div[data-testid="stToolbar"] {
        display: none !important;
    }

    /* 隐藏右上角的所有按钮 */
    .stApp > div > div > div > div > section > div {
        padding-top: 0 !important;
    }

    /* 应用样式 */
    .main-header {
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }

    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }

    .analysis-section {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }

    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }

    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }

    .error-box {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }

    /* 图片分析区域样式 */
    .image-analysis-container {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #e9ecef;
    }

    .image-preview {
        max-width: 100%;
        border-radius: 5px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """初始化会话状态，添加多模态相关状态变量"""
    if 'analysis_results' not in st.session_state:
        st.session_state.analysis_results = None
    if 'analysis_running' not in st.session_state:
        st.session_state.analysis_running = False
    if 'last_analysis_time' not in st.session_state:
        st.session_state.last_analysis_time = None
    if 'current_analysis_id' not in st.session_state:
        st.session_state.current_analysis_id = None
    if 'form_config' not in st.session_state:
        st.session_state.form_config = None

    # 多模态分析相关状态变量
    if 'image_analysis_report' not in st.session_state:
        st.session_state.image_analysis_report = ""
    if 'crag_analysis_report' not in st.session_state:
        st.session_state.crag_analysis_report = ""
    if 'extracted_tickers' not in st.session_state:
        st.session_state.extracted_tickers = []
    if 'extracted_companies' not in st.session_state:
        st.session_state.extracted_companies = []
    if 'final_synthesis_report' not in st.session_state:
        st.session_state.final_synthesis_report = ""
    if 'selected_ticker_from_image' not in st.session_state:
        st.session_state.selected_ticker_from_image = None
    # 新增状态变量：标记图片分析是否已完成
    if 'image_analysis_completed' not in st.session_state:
        st.session_state.image_analysis_completed = False

    # 网页截图相关状态变量
    if 'web_screenshot' not in st.session_state:
        st.session_state.web_screenshot = None
    if 'web_screenshot_url' not in st.session_state:
        st.session_state.web_screenshot_url = ""

    # 尝试从最新完成的分析中恢复结果
    if not st.session_state.analysis_results:
        try:
            from utils.async_progress_tracker import get_latest_analysis_id, get_progress_by_id
            from utils.analysis_runner import format_analysis_results

            latest_id = get_latest_analysis_id()
            if latest_id:
                progress_data = get_progress_by_id(latest_id)
                if (progress_data and
                        progress_data.get('status') == 'completed' and
                        'raw_results' in progress_data):

                    # 恢复分析结果
                    raw_results = progress_data['raw_results']
                    formatted_results = format_analysis_results(raw_results)

                    if formatted_results:
                        st.session_state.analysis_results = formatted_results
                        st.session_state.current_analysis_id = latest_id
                        # 检查分析状态
                        analysis_status = progress_data.get('status', 'completed')
                        st.session_state.analysis_running = (analysis_status == 'running')
                        # 恢复股票信息
                        if 'stock_symbol' in raw_results:
                            st.session_state.last_stock_symbol = raw_results.get('stock_symbol', '')
                        if 'market_type' in raw_results:
                            st.session_state.last_market_type = raw_results.get('market_type', '')
                        logger.info(f"📊 [结果恢复] 从分析 {latest_id} 恢复结果，状态: {analysis_status}")

        except Exception as e:
            logger.warning(f"⚠️ [结果恢复] 恢复失败: {e}")

    # 使用cookie管理器恢复分析ID（优先级：session state > cookie > Redis/文件）
    try:
        persistent_analysis_id = get_persistent_analysis_id()
        if persistent_analysis_id:
            # 使用线程检测来检查分析状态
            from utils.thread_tracker import check_analysis_status
            actual_status = check_analysis_status(persistent_analysis_id)

            # 只在状态变化时记录日志，避免重复
            current_session_status = st.session_state.get('last_logged_status')
            if current_session_status != actual_status:
                logger.info(f"📊 [状态检查] 分析 {persistent_analysis_id} 实际状态: {actual_status}")
                st.session_state.last_logged_status = actual_status

            if actual_status == 'running':
                st.session_state.analysis_running = True
                st.session_state.current_analysis_id = persistent_analysis_id
            elif actual_status in ['completed', 'failed']:
                st.session_state.analysis_running = False
                st.session_state.current_analysis_id = persistent_analysis_id
            else:  # not_found
                logger.warning(f"📊 [状态检查] 分析 {persistent_analysis_id} 未找到，清理状态")
                st.session_state.analysis_running = False
                st.session_state.current_analysis_id = None
    except Exception as e:
        # 如果恢复失败，保持默认值
        logger.warning(f"⚠️ [状态恢复] 恢复分析状态失败: {e}")
        st.session_state.analysis_running = False
        st.session_state.current_analysis_id = None

    # 恢复表单配置
    try:
        from utils.smart_session_manager import smart_session_manager
        session_data = smart_session_manager.load_analysis_state()

        if session_data and 'form_config' in session_data:
            st.session_state.form_config = session_data['form_config']
            # 只在没有分析运行时记录日志，避免重复
            if not st.session_state.get('analysis_running', False):
                logger.info("📊 [配置恢复] 表单配置已恢复")
    except Exception as e:
        logger.warning(f"⚠️ [配置恢复] 表单配置恢复失败: {e}")


def capture_screenshot(url):
    """
    使用Selenium捕获完整网页截图
    :param url: 要截图的网页URL
    :return: PIL Image对象，完整的网页截图
    """
    try:
        # 配置Chrome浏览器选项
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # 无头模式
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        # 禁用自动化控制特征，避免被网站检测
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        # 初始化WebDriver
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        # 执行JavaScript以移除webdriver标记
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        # 打开目标URL
        driver.get(url)

        # 等待页面加载完成（最多等待10秒）
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # 等待额外时间确保页面完全加载
        time.sleep(3)

        # 获取页面总高度
        total_height = driver.execute_script("return document.body.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")

        # 计算需要滚动的次数
        num_scrolls = (total_height + viewport_height - 1) // viewport_height

        # 存储每个视口的截图
        screenshots = []

        # 初始滚动位置
        scroll_position = 0

        for i in range(num_scrolls):
            # 截取当前视口
            screenshot = driver.get_screenshot_as_png()
            img = PILImage.open(io.BytesIO(screenshot))
            screenshots.append(img)

            # 计算下一个滚动位置
            scroll_position += viewport_height
            if scroll_position >= total_height:
                break

            # 滚动到下一个位置
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(1)  # 等待页面加载

        # 关闭浏览器
        driver.quit()

        # 如果只有一个截图，直接返回
        if len(screenshots) == 1:
            return screenshots[0]

        # 拼接多个截图
        widths, heights = zip(*(i.size for i in screenshots))

        # 计算总宽度和高度
        total_width = max(widths)
        total_height = sum(heights)

        # 创建新的空白图像
        combined = PILImage.new('RGB', (total_width, total_height))

        # 拼接图像
        y_offset = 0
        for img in screenshots:
            combined.paste(img, (0, y_offset))
            y_offset += img.size[1]

        return combined

    except Exception as e:
        logger.error(f"网页截图失败: {str(e)}")
        st.error(f"网页截图失败: {str(e)}")
        return None


# 多模态图片解析函数 - 分析图片并提取个股股票代码
def analyze_image_with_multimodal(image):
    """
    使用指定的多模态模型分析图片
    提供完整图像分析报告，同时重点提取个股股票代码（去重）和相关公司信息
    """
    # 检查是否安装了必要的SDK
    if not has_ark_sdk:
        st.error("volcenginesdkarkruntime not installed. Please install it to use multimodal features.")
        return {"tickers": [], "companies": [], "report": ""}

    # 获取API密钥
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        st.error("API key not configured. Please set ARK_API_KEY environment variable.")
        return {"tickers": [], "companies": [], "report": ""}

    try:
        # 初始化客户端
        client = Ark(api_key=api_key)
    except Exception as e:
        st.error(f"Failed to initialize SDK client: {str(e)}")
        return {"tickers": [], "companies": [], "report": ""}

    try:
        # 显示图片预览
        st.image(image, caption="分析的图像", use_container_width=True, output_format="PNG")

        # 将图片转换为base64编码
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        image_url = f"data:image/png;base64,{img_str}"

        # 构建提示词，要求完整分析同时专门提取个股股票代码
        prompt = """
        请全面分析这张图片，包括所有财务信息、图表、表格、文本内容和市场数据。然后，特别识别：

        1. 仅存在于图片中的个股股票代码（不是指数、ETF或其他金融工具）
           请提供清晰的列表，不要有重复。
        2. 每个识别出的股票代码对应的公司名称。
        3. 与这些个股相关的关键财务指标或见解。

        请按以下结构组织您的回答：
        - 对整个图像内容的详细整体分析
        - 明确的"个股股票代码"部分（仅个股，无重复）
        - 与每个股票代码对应的"公司名称"部分
        - 已识别股票的相关财务背景

        确保您的分析全面，涵盖图像中所有重要信息，
        同时使股票代码的提取精确且专注于个股。
        """

        # 按照官方参考代码格式构建消息
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        # 构建提示词，要求从源文件中提取指标
        crag_prompt = """
        你是一名专业的金融数据分析专家。你将接收到一张包含图表或报表的图像。
        请根据图像中的内容，提取出所有可识别的关键指标，并按照以下格式输出：

        指标名称（如：营收、净利润、毛利率等）
        对应的数值
        所属时间或区间（如有）

        请确保尽可能提取全面，忽略与指标无关的装饰性元素。
        如果图像中存在多个表格或子图，请分别标注提取结果所属部分。
        """

        # 按照官方参考代码格式构建消息
        crag_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": crag_prompt}
                ]
            }
        ]

        # 发送请求到API
        with st.spinner(f"使用 {MULTIMODAL_MODEL} 多模态模型分析图像中..."):
            try:
                resp = client.chat.completions.create(
                    model=MULTIMODAL_MODEL,
                    messages=messages
                )

                crag_resp = client.chat.completions.create(
                    model=MULTIMODAL_MODEL,
                    messages=crag_messages
                )

                from crag.crag_server import CRAGServer
                crag_server = CRAGServer(
                    doc_dir="./document",
                    collection_name="rag-chroma",
                )
                crag_document = crag_server.graph.invoke({"question": crag_resp.choices[0].message.content})
                crag_report = crag_document["generation"]

                # 显示API调试信息（仅在调试模式）
                if os.getenv('DEBUG_MODE') == 'true':
                    with st.expander("查看API调试信息"):
                        st.write(f"使用的模型: {MULTIMODAL_MODEL}")
                        st.write(f"消息结构: {json.dumps(messages, indent=2)}")
                        st.write(f"API响应: {resp}")

                # 提取模型返回的内容
                if resp.choices and len(resp.choices) > 0:
                    report = resp.choices[0].message.content
                    st.success("图像分析成功完成")

                    # 从模型响应中提取股票代码和公司信息
                    extracted_tickers = extract_tickers_from_text(report)
                    # 对提取的股票代码进行去重处理
                    extracted_tickers = list(dict.fromkeys(extracted_tickers))

                    extracted_companies = extract_companies_from_text(report)
                    # 确保公司列表与去重后的股票代码长度匹配
                    if len(extracted_companies) > len(extracted_tickers):
                        extracted_companies = extracted_companies[:len(extracted_tickers)]
                    elif len(extracted_companies) < len(extracted_tickers):
                        extracted_companies += ["未知公司"] * (len(extracted_tickers) - len(extracted_companies))

                    # 保存到会话状态
                    st.session_state.image_analysis_report = report
                    st.session_state.crag_analysis_report = crag_report
                    st.session_state.extracted_tickers = extracted_tickers
                    st.session_state.extracted_companies = extracted_companies
                    st.session_state.image_analysis_completed = True  # 标记图像分析已完成

                    # 如果有提取到股票，默认选择第一个
                    if extracted_tickers:
                        st.session_state.selected_ticker_from_image = extracted_tickers[0]

                    return {
                        "tickers": extracted_tickers,
                        "companies": extracted_companies,
                        "report": report
                    }
                else:
                    st.warning("多模态模型未返回有效响应。")
                    return {"tickers": [], "companies": [], "report": ""}

            except Exception as e:
                st.error(f"API请求失败: {str(e)}")
                return {"tickers": [], "companies": [], "report": ""}

    except Exception as e:
        st.error(f"图像分析错误: {str(e)}")
        return {"tickers": [], "companies": [], "report": ""}


# 辅助函数：从文本中提取股票代码 - 精准版
def extract_tickers_from_text(text):
    """
    精准提取模型报告中"个股股票代码"部分明确列出的个股代码
    只提取模型明确标注的个股，不进行盲目的数字匹配
    """
    # 定位模型报告中明确标注个股代码的部分（支持中英文标记）
    start_markers = ["个股股票代码", "Individual Stock Codes"]
    end_markers = ["公司名称", "Company Names"]  # 下一个明确部分作为结束标记

    # 尝试所有可能的起始标记
    start_idx = -1
    for marker in start_markers:
        start_idx = text.find(marker)
        if start_idx != -1:
            break

    if start_idx == -1:
        # 如果没有明确标记，尝试直接提取6位数字（A股）或字母代码（美股等）
        logger.info("未找到明确的股票代码标记，尝试直接提取可能的代码")
        # 匹配6位数字（A股）或字母数字组合（美股等）
        pattern = r'\b(\d{6}|[A-Za-z0-9]{1,5})\b'
        tickers = re.findall(pattern, text)
        # 过滤掉明显不是股票代码的结果
        filtered = []
        for ticker in tickers:
            if len(ticker) >= 1 and len(ticker) <= 6:
                filtered.append(ticker)
        return list(dict.fromkeys(filtered))

    # 尝试所有可能的结束标记
    end_idx = len(text)
    for marker in end_markers:
        temp_idx = text.find(marker, start_idx)
        if temp_idx != -1:
            end_idx = temp_idx
            break

    # 提取从起始标记到结束标记之间的内容
    code_section = text[start_idx:end_idx].strip()

    # 从代码部分提取股票代码（6位数字的A股代码或字母数字组合的美股代码）
    pattern = r'\b(\d{6}|[A-Za-z0-9]{1,5})\b'
    tickers = re.findall(pattern, code_section)

    # 去重并返回
    return list(dict.fromkeys(tickers))


# 辅助函数：从文本中提取公司名称 - 精准版
def extract_companies_from_text(text):
    """精准提取模型报告中"公司名称"部分明确列出的公司名称"""
    start_markers = ["公司名称", "Company Names"]
    end_markers = ["相关财务背景", "Relevant Financial Context", "个股股票代码",
                   "Individual Stock Codes"]  # 下一个部分作为结束标记

    # 尝试所有可能的起始标记
    start_idx = -1
    for marker in start_markers:
        start_idx = text.find(marker)
        if start_idx != -1:
            break

    if start_idx == -1:
        return []

    # 尝试所有可能的结束标记
    end_idx = len(text)
    for marker in end_markers:
        temp_idx = text.find(marker, start_idx)
        if temp_idx != -1:
            end_idx = temp_idx
            break

    # 提取公司名称部分
    company_section = text[start_idx:end_idx].strip()

    # 提取公司名称（处理列表格式）
    companies = []
    # 按行分割
    lines = [line.strip() for line in company_section.split('\n') if line.strip()]

    for line in lines:
        # 过滤掉数字和空行
        if not line.isdigit() and len(line) > 3:
            # 移除可能的编号前缀（如1. 2. 等）
            cleaned_line = re.sub(r'^\d+\.\s*', '', line)
            # 移除可能包含的股票代码
            cleaned_line = re.sub(r'\b(\d{6}|[A-Za-z0-9]{1,5})\b', '', cleaned_line).strip()
            companies.append(cleaned_line)

    # 去重
    return list(dict.fromkeys(companies))


# 生成最终综合报告
def generate_final_synthesis_report(image_report, stock_report, crag_report):
    """
    将图片分析报告和股票分析报告结合，
    使用相同的大模型（仅文本功能）生成最终综合报告
    """
    # 检查是否安装了必要的SDK
    if not has_ark_sdk:
        return "volcenginesdkarkruntime not installed. Cannot generate synthesis report."

    # 获取API密钥
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        return "API key not configured. Cannot generate synthesis report."

    try:
        # 初始化客户端
        client = Ark(api_key=api_key)
    except Exception as e:
        return f"Failed to initialize SDK client: {str(e)}"

    # 构建综合提示词
    prompt = f"""
    作为资深金融分析师，请将以下两份报告综合成一份全面的投资分析报告：

    1. 图像分析报告（包含视觉财务信息）：
    {image_report}

    2. 详细股票分析报告：
    {stock_report}
    
    3. 关键指标分析报告：
    {crag_report}

    您的综合报告应包括：
    - 三份报告中的关键见解和发现
    - 视觉信息与股票表现之间的相关性
    - 基于所有可用信息的综合投资建议
    - 任一报告中强调的潜在风险
    - 结构清晰，逻辑流畅，并带有标题

    确保您的分析全面、平衡，并提供可操作的见解。
    """

    try:
        with st.spinner(f"使用 {MULTIMODAL_MODEL} 生成最终综合报告中..."):
            # 仅使用文本功能调用模型
            resp = client.chat.completions.create(
                model=MULTIMODAL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            )

            # 显示API调试信息（仅在调试模式）
            if os.getenv('DEBUG_MODE') == 'true':
                with st.expander("查看综合报告API调试信息"):
                    st.write(f"使用的模型: {MULTIMODAL_MODEL}")
                    st.write(f"提示词: {prompt}")
                    st.write(f"API响应: {resp}")

            if resp.choices and len(resp.choices) > 0:
                final_report = resp.choices[0].message.content
                st.session_state.final_synthesis_report = final_report
                return final_report
            else:
                return "模型未返回有效响应，无法生成综合报告"

    except Exception as e:
        return f"生成综合报告失败: {str(e)}"


def main():
    """主应用程序"""

    # 初始化会话状态
    initialize_session_state()

    # 自定义CSS - 调整侧边栏宽度
    st.markdown("""
    <style>
    /* 调整侧边栏宽度为260px，避免标题挤压 */
    section[data-testid="stSidebar"] {
        width: 260px !important;
        min-width: 260px !important;
        max-width: 260px !important;
    }

    /* 隐藏侧边栏的隐藏按钮 - 更全面的选择器 */
    button[kind="header"],
    button[data-testid="collapsedControl"],
    .css-1d391kg,
    .css-1rs6os,
    .css-17eq0hr,
    .css-1lcbmhc,
    .css-1y4p8pa,
    button[aria-label="Close sidebar"],
    button[aria-label="Open sidebar"],
    [data-testid="collapsedControl"],
    .stSidebar button[kind="header"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }

    /* 隐藏侧边栏顶部区域的特定按钮（更精确的选择器，避免影响表单按钮） */
    section[data-testid="stSidebar"] > div:first-child > button[kind="header"],
    section[data-testid="stSidebar"] > div:first-child > div > button[kind="header"],
    section[data-testid="stSidebar"] .css-1lcbmhc > button[kind="header"],
    section[data-testid="stSidebar"] .css-1y4p8pa > button[kind="header"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* 调整侧边栏内容的padding */
    section[data-testid="stSidebar"] > div {
        padding-top: 0.5rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }

    /* 调整主内容区域，设置8px边距 - 使用更强的选择器 */
    .main .block-container,
    section.main .block-container,
    div.main .block-container,
    .stApp .main .block-container {
        padding-left: 8px !important;
        padding-right: 8px !important;
        margin-left: 0px !important;
        margin-right: 0px !important;
        max-width: none !important;
        width: calc(100% - 16px) !important;
    }

    /* 确保内容不被滚动条遮挡 */
    .stApp > div {
        overflow-x: auto !important;
    }

    /* 调整详细分析报告的右边距 */
    .element-container {
        margin-right: 8px !important;
    }

    /* 优化侧边栏标题和元素间距 */
    .sidebar .sidebar-content {
        padding: 0.5rem 0.3rem !important;
    }

    /* 调整侧边栏内所有元素的间距 */
    section[data-testid="stSidebar"] .element-container {
        margin-bottom: 0.5rem !important;
    }

    /* 调整侧边栏分隔线的间距 */
    section[data-testid="stSidebar"] hr {
        margin: 0.8rem 0 !important;
    }

    /* 确保侧边栏标题不被挤压 */
    section[data-testid="stSidebar"] h1 {
        font-size: 1.2rem !important;
        line-height: 1.3 !important;
        margin-bottom: 1rem !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
    }

    /* 简化功能选择区域样式 */
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        font-size: 1.1rem !important;
        font-weight: 500 !important;
    }

    /* 调整选择框等组件的宽度 */
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        min-width: 220px !important;
        width: 100% !important;
    }

    /* 修复右侧内容被遮挡的问题 */
    .main {
        padding-right: 8px !important;
    }

    /* 确保页面内容有足够的右边距 */
    .stApp {
        margin-right: 0 !important;
        padding-right: 8px !important;
    }

    /* 特别处理展开的分析报告 */
    .streamlit-expanderContent {
        padding-right: 8px !important;
        margin-right: 8px !important;
    }

    /* 防止水平滚动条出现 */
    .main .block-container {
        overflow-x: visible !important;
    }

    /* 强制设置8px边距给所有可能的容器 */
    .stApp,
    .stApp > div,
    .stApp > div > div,
    .main,
    .main > div,
    .main > div > div,
    div[data-testid="stAppViewContainer"],
    div[data-testid="stAppViewContainer"] > div,
    section[data-testid="stMain"],
    section[data-testid="stMain"] > div {
        padding-left: 8px !important;
        padding-right: 8px !important;
        margin-left: 0px !important;
        margin-right: 0px !important;
    }

    /* 特别处理列容器 */
    div[data-testid="column"],
    .css-1d391kg,
    .css-1r6slb0,
    .css-12oz5g7,
    .css-1lcbmhc {
        padding-left: 8px !important;
        padding-right: 8px !important;
        margin-left: 0px !important;
        margin-right: 0px !important;
    }

    /* 强制设置容器宽度 */
    .main .block-container {
        width: calc(100vw - 276px) !important;
        max-width: calc(100vw - 276px) !important;
    }

    /* 优化使用指南区域的样式 */
    div[data-testid="column"]:last-child {
        background-color: #f8f9fa !important;
        border-radius: 8px !important;
        padding: 12px !important;
        margin-left: 8px !important;
        border: 1px solid #e9ecef !important;
    }

    /* 使用指南内的展开器样式 */
    div[data-testid="column"]:last-child .streamlit-expanderHeader {
        background-color: #ffffff !important;
        border-radius: 6px !important;
        border: 1px solid #dee2e6 !important;
        font-weight: 500 !important;
    }

    /* 使用指南内的文本样式 */
    div[data-testid="column"]:last-child .stMarkdown {
        font-size: 0.9rem !important;
        line-height: 1.5 !important;
    }

    /* 使用指南标题样式 */
    div[data-testid="column"]:last-child h1 {
        font-size: 1.3rem !important;
        color: #495057 !important;
        margin-bottom: 1rem !important;
    }
    </style>

    <script>
    // JavaScript来强制隐藏侧边栏按钮
    function hideSidebarButtons() {
        // 隐藏所有可能的侧边栏控制按钮
        const selectors = [
            'button[kind="header"]',
            'button[data-testid="collapsedControl"]',
            'button[aria-label="Close sidebar"]',
            'button[aria-label="Open sidebar"]',
            '[data-testid="collapsedControl"]',
            '.css-1d391kg',
            '.css-1rs6os',
            '.css-17eq0hr',
            '.css-1lcbmhc button',
            '.css-1y4p8pa button'
        ];

        selectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
                el.style.opacity = '0';
                el.style.pointerEvents = 'none';
            });
        });
    }

    // 页面加载后执行
    document.addEventListener('DOMContentLoaded', hideSidebarButtons);

    // 定期检查并隐藏按钮（防止动态生成）
    setInterval(hideSidebarButtons, 1000);

    // 强制修改页面边距为8px
    function forceOptimalPadding() {
        const selectors = [
            '.main .block-container',
            '.stApp',
            '.stApp > div',
            '.main',
            '.main > div',
            'div[data-testid="stAppViewContainer"]',
            'section[data-testid="stMain"]',
            'div[data-testid="column"]'
        ];

        selectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {
                el.style.paddingLeft = '8px';
                el.style.paddingRight = '8px';
                el.style.marginLeft = '0px';
                el.style.marginRight = '0px';
            });
        });

        // 特别处理主容器宽度
        const mainContainer = document.querySelector('.main .block-container');
        if (mainContainer) {
            mainContainer.style.width = 'calc(100vw - 276px)';
            mainContainer.style.maxWidth = 'calc(100vw - 276px)';
        }
    }

    // 页面加载后执行
    document.addEventListener('DOMContentLoaded', forceOptimalPadding);

    // 定期强制应用样式
    setInterval(forceOptimalPadding, 500);
    </script>
    """, unsafe_allow_html=True)

    # 添加调试按钮（仅在调试模式下显示）
    if os.getenv('DEBUG_MODE') == 'true':
        if st.button("🔄 清除会话状态"):
            st.session_state.clear()
            st.experimental_rerun()

    # 渲染页面头部
    render_header()

    # 页面导航
    st.sidebar.title("🤖 TradingAgents-CN")
    st.sidebar.markdown("---")

    # 添加功能切换标题
    st.sidebar.markdown("**🎯 功能导航**")

    page = st.sidebar.selectbox(
        "切换功能模块",
        ["📊 股票分析", "⚙️ 配置管理", "💾 缓存管理", "💰 Token统计", "📈 历史记录", "🔧 系统状态"],
        label_visibility="collapsed"
    )

    # 在功能选择和AI模型配置之间添加分隔线
    st.sidebar.markdown("---")

    # 根据选择的页面渲染不同内容
    if page == "⚙️ 配置管理":
        try:
            from modules.config_management import render_config_management
            render_config_management()
        except ImportError as e:
            st.error(f"配置管理模块加载失败: {e}")
            st.info("请确保已安装所有依赖包")
        return
    elif page == "💾 缓存管理":
        try:
            from modules.cache_management import main as cache_main
            cache_main()
        except ImportError as e:
            st.error(f"缓存管理页面加载失败: {e}")
        return
    elif page == "💰 Token统计":
        try:
            from modules.token_statistics import render_token_statistics
            render_token_statistics()
        except ImportError as e:
            st.error(f"Token统计页面加载失败: {e}")
            st.info("请确保已安装所有依赖包")
        return
    elif page == "📈 历史记录":
        st.header("📈 历史记录")
        st.info("历史记录功能开发中...")
        return
    elif page == "🔧 系统状态":
        st.header("🔧 系统状态")
        st.info("系统状态功能开发中...")
        return

    # 默认显示股票分析页面
    # 检查API密钥
    api_status = check_api_keys()

    # 额外检查多模态所需的API密钥
    if has_ark_sdk and not os.getenv("ARK_API_KEY"):
        api_status['all_configured'] = False
        if 'ARK_API_KEY' not in api_status['details']:
            api_status['details']['ARK_API_KEY'] = {
                'configured': False,
                'display': '多模态分析API密钥'
            }

    if not api_status['all_configured']:
        st.error("⚠️ API密钥配置不完整，请先配置必要的API密钥")

        with st.expander("📋 API密钥配置指南", expanded=True):
            st.markdown("""
            ### 🔑 必需的API密钥

            1. **阿里百炼API密钥** (DASHSCOPE_API_KEY)
               - 获取地址: https://dashscope.aliyun.com/
               - 用途: AI模型推理

            2. **金融数据API密钥** (FINNHUB_API_KEY)  
               - 获取地址: https://finnhub.io/
               - 用途: 获取股票数据

            3. **多模态分析API密钥** (ARK_API_KEY)
               - 用途: 图片分析和综合报告生成
               - 用于模型: doubao-seed-1-6-thinking-250715

            ### ⚙️ 配置方法

            1. 复制项目根目录的 `.env.example` 为 `.env`
            2. 编辑 `.env` 文件，填入您的真实API密钥
            3. 重启Web应用

            ```bash
            # .env 文件示例
            DASHSCOPE_API_KEY=sk-your-dashscope-key
            FINNHUB_API_KEY=your-finnhub-key
            ARK_API_KEY=your-ark-api-key
            ```
            """)

        # 显示当前API密钥状态
        st.subheader("🔍 当前API密钥状态")
        for key, status in api_status['details'].items():
            if status['configured']:
                st.success(f"✅ {key}: {status['display']}")
            else:
                st.error(f"❌ {key}: 未配置")

        return

    # 渲染侧边栏
    config = render_sidebar()

    # 添加使用指南显示切换
    show_guide = st.sidebar.checkbox("📖 显示使用指南", value=True, help="显示/隐藏右侧使用指南")

    # 添加状态清理按钮
    st.sidebar.markdown("---")
    if st.sidebar.button("🧹 清理分析状态", help="清理僵尸分析状态，解决页面持续刷新问题"):
        # 清理session state
        st.session_state.analysis_running = False
        st.session_state.current_analysis_id = None
        st.session_state.analysis_results = None
        # 清理多模态相关状态
        st.session_state.image_analysis_report = ""
        st.session_state.crag_analysis_report = ""
        st.session_state.extracted_tickers = []
        st.session_state.extracted_companies = []
        st.session_state.final_synthesis_report = ""
        st.session_state.selected_ticker_from_image = None
        st.session_state.image_analysis_completed = False  # 清理图像分析状态
        # 清理网页截图相关状态
        st.session_state.web_screenshot = None
        st.session_state.web_screenshot_url = ""

        # 清理所有自动刷新状态
        keys_to_remove = []
        for key in st.session_state.keys():
            if 'auto_refresh' in key:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del st.session_state[key]

        # 清理死亡线程
        from utils.thread_tracker import cleanup_dead_analysis_threads
        cleanup_dead_analysis_threads()

        st.sidebar.success("✅ 分析状态已清理")
        st.rerun()

    # 主内容区域 - 根据是否显示指南调整布局
    if show_guide:
        col1, col2 = st.columns([2, 1])  # 2:1比例，使用指南占三分之一
    else:
        col1 = st.container()
        col2 = None

    with col1:
        # 0. 多模态图像和网页分析区域
        st.header("🖼️ 图像与网页分析 (多模态)")
        with st.container():
            # 网页分析部分
            st.subheader("🌐 网页分析")
            web_url = st.text_input(
                "输入网页URL",
                value=st.session_state.web_screenshot_url,
                placeholder="例如: https://finance.yahoo.com/quote/AAPL",
                help="输入包含股票信息的网页URL进行分析"
            )

            # 保存URL到会话状态
            if web_url != st.session_state.web_screenshot_url:
                st.session_state.web_screenshot_url = web_url
                # 重置相关状态
                st.session_state.web_screenshot = None
                st.session_state.image_analysis_completed = False

            # 截取网页截图按钮
            if st.button("截取网页截图", disabled=not web_url):
                with st.spinner(f"正在截取网页: {web_url}..."):
                    screenshot = capture_screenshot(web_url)
                    if screenshot:
                        st.session_state.web_screenshot = screenshot
                        st.success("网页截图成功")
                        # 自动进行多模态分析
                        st.session_state.image_analysis_completed = False
                        extracted_info = analyze_image_with_multimodal(screenshot)

            # 显示已截取的网页截图
            if st.session_state.web_screenshot is not None:
                st.image(
                    st.session_state.web_screenshot,
                    caption=f"网页截图: {st.session_state.web_screenshot_url}",
                    use_container_width=True,
                    output_format="PNG"
                )

            # 图片上传部分
            st.subheader("📷 图片上传")
            uploaded_file = st.file_uploader(
                "上传包含股票信息的图片（图表、表格、财务数据等）",
                type=["jpg", "jpeg", "png", "pdf"]
            )

            if uploaded_file is not None and not st.session_state.image_analysis_completed:
                # 处理上传的图片
                try:
                    # 重置网页截图状态
                    st.session_state.web_screenshot = None
                    st.session_state.web_screenshot_url = ""

                    image = Image.open(uploaded_file)
                    # 使用指定的多模态模型分析图片
                    extracted_info = analyze_image_with_multimodal(image)

                except Exception as e:
                    st.error(f"图片处理错误: {str(e)}")
                    logger.error(f"图片处理错误: {str(e)}")

            # 显示图像分析结果（如果已完成）
            if st.session_state.image_analysis_completed:
                # 显示图像分析报告
                if st.session_state.image_analysis_report:
                    st.markdown("### 图像分析报告")
                    with st.expander("查看完整图像分析报告", expanded=False):
                        st.markdown(st.session_state.image_analysis_report)

                if st.session_state.crag_analysis_report:
                    st.markdown("### 知识库检索分析报告")
                    with st.expander("查看知识库检索分析报告", expanded=False):
                        st.markdown(st.session_state.crag_analysis_report)

                if st.session_state.extracted_tickers:
                    # 显示提取的股票信息
                    st.success(
                        f"成功从图像中提取到 {len(st.session_state.extracted_tickers)} 个独特的股票代码")

                    # 让用户选择要分析的股票
                    selected_ticker = st.selectbox(
                        "从提取结果中选择股票进行详细分析",
                        options=st.session_state.extracted_tickers,
                        index=0
                    )

                    # 保存选中的股票代码到会话状态
                    st.session_state.selected_ticker_from_image = selected_ticker
                else:
                    st.warning("未在图像中找到股票代码。请在下方手动输入股票代码进行分析。")
                    st.session_state.selected_ticker_from_image = None

            # 显示使用的模型信息
            st.info(f"使用的多模态模型: {MULTIMODAL_MODEL}")

        st.markdown("---")

        # 1. 分析配置区域
        st.header("⚙️ 分析配置")

        # 渲染分析表单，优先使用从图像提取的股票代码
        try:
            # 如果有从图像提取的股票代码，将其设为默认值
            default_stock = st.session_state.selected_ticker_from_image if st.session_state.selected_ticker_from_image else None
            form_data = render_analysis_form(default_stock=default_stock)

            # 验证表单数据格式
            if not isinstance(form_data, dict):
                st.error(f"⚠️ 表单数据格式异常: {type(form_data)}")
                form_data = {'submitted': False}

        except Exception as e:
            st.error(f"❌ 表单渲染失败: {e}")
            form_data = {'submitted': False}

        # 避免显示调试信息
        if form_data and form_data != {'submitted': False}:
            # 只在调试模式下显示表单数据
            if os.getenv('DEBUG_MODE') == 'true':
                st.write("Debug - Form data:", form_data)

        # 添加接收日志
        if form_data.get('submitted', False):
            logger.debug(f"🔍 [APP DEBUG] ===== 主应用接收表单数据 =====")
            logger.debug(f"🔍 [APP DEBUG] 接收到的form_data: {form_data}")
            logger.debug(f"🔍 [APP DEBUG] 股票代码: '{form_data['stock_symbol']}'")
            logger.debug(f"🔍 [APP DEBUG] 市场类型: '{form_data['market_type']}'")

        # 检查是否提交了表单
        if form_data.get('submitted', False) and not st.session_state.get('analysis_running', False):
            # 只有在没有分析运行时才处理新的提交
            # 验证分析参数
            is_valid, validation_errors = validate_analysis_params(
                stock_symbol=form_data['stock_symbol'],
                analysis_date=form_data['analysis_date'],
                analysts=form_data['analysts'],
                research_depth=form_data['research_depth'],
                market_type=form_data.get('market_type', '美股')
            )

            if not is_valid:
                # 显示验证错误
                for error in validation_errors:
                    st.error(error)
            else:
                # 执行专业股票分析（非多模态模型）
                st.session_state.analysis_running = True

                # 清空旧的分析结果和综合报告
                st.session_state.analysis_results = None
                st.session_state.final_synthesis_report = ""
                logger.info("🧹 [新分析] 清空旧的分析结果和综合报告")

                # 生成分析ID
                import uuid
                analysis_id = f"analysis_{uuid.uuid4().hex[:8]}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # 保存分析ID和表单配置到session state和cookie
                form_config = st.session_state.get('form_config', {})
                set_persistent_analysis_id(
                    analysis_id=analysis_id,
                    status="running",
                    stock_symbol=form_data['stock_symbol'],
                    market_type=form_data.get('market_type', '美股'),
                    form_config=form_config
                )

                # 创建异步进度跟踪器
                async_tracker = AsyncProgressTracker(
                    analysis_id=analysis_id,
                    analysts=form_data['analysts'],
                    research_depth=form_data['research_depth'],
                    llm_provider=config['llm_provider']
                )

                # 创建进度回调函数
                def progress_callback(message: str, step: int = None, total_steps: int = None):
                    async_tracker.update_progress(message, step)

                # 显示启动成功消息和加载动效
                st.success(f"🚀 专业股票分析已启动！分析ID: {analysis_id}")

                # 添加加载动效
                with st.spinner("🔄 正在初始化分析..."):
                    time.sleep(1.5)  # 让用户看到反馈

                st.info(f"📊 正在分析: {form_data.get('market_type', '美股')} {form_data['stock_symbol']}")
                st.info("""
                ⏱️ 页面将在6秒后自动刷新...

                📋 **查看分析进度：**
                刷新后请向下滚动到 "📊 股票分析" 部分查看实时进度
                """)

                # 确保AsyncProgressTracker已经保存初始状态
                time.sleep(0.1)  # 等待100毫秒确保数据已写入

                # 设置分析状态
                st.session_state.analysis_running = True
                st.session_state.current_analysis_id = analysis_id
                st.session_state.last_stock_symbol = form_data['stock_symbol']
                st.session_state.last_market_type = form_data.get('market_type', '美股')

                # 自动启用自动刷新选项（设置所有可能的key）
                auto_refresh_keys = [
                    f"auto_refresh_unified_{analysis_id}",
                    f"auto_refresh_unified_default_{analysis_id}",
                    f"auto_refresh_static_{analysis_id}",
                    f"auto_refresh_streamlit_{analysis_id}"
                ]
                for key in auto_refresh_keys:
                    st.session_state[key] = True

                # 在后台线程中运行专业股票分析（立即启动）
                import threading

                def run_analysis_in_background():
                    try:
                        # 使用专业股票分析模块，而非多模态模型
                        results = run_stock_analysis(
                            stock_symbol=form_data['stock_symbol'],
                            analysis_date=form_data['analysis_date'],
                            analysts=form_data['analysts'],
                            research_depth=form_data['research_depth'],
                            llm_provider=config['llm_provider'],
                            market_type=form_data.get('market_type', '美股'),
                            llm_model=config['llm_model'],
                            progress_callback=progress_callback
                        )

                        # 标记分析完成并保存结果
                        async_tracker.mark_completed("✅ 专业股票分析成功完成！", results=results)

                        logger.info(f"✅ [分析完成] 股票分析成功完成: {analysis_id}")

                    except Exception as e:
                        # 标记分析失败
                        async_tracker.mark_failed(str(e))
                        logger.error(f"❌ [分析失败] {analysis_id}: {e}")

                    finally:
                        # 分析结束后注销线程
                        from utils.thread_tracker import unregister_analysis_thread
                        unregister_analysis_thread(analysis_id)
                        logger.info(f"🧵 [线程清理] 分析线程已注销: {analysis_id}")

                # 启动后台分析线程
                analysis_thread = threading.Thread(target=run_analysis_in_background)
                analysis_thread.daemon = True  # 设置为守护线程
                analysis_thread.start()

                # 注册线程到跟踪器
                from utils.thread_tracker import register_analysis_thread
                register_analysis_thread(analysis_id, analysis_thread)

                logger.info(f"🧵 [后台分析] 专业股票分析线程已启动: {analysis_id}")

                # 显示启动信息
                st.success("🚀 专业股票分析已启动！正在后台运行...")

                # 等待2秒让用户看到启动信息，然后刷新页面
                time.sleep(2)
                st.rerun()

        # 2. 股票分析区域（只有在有分析ID时才显示）
        current_analysis_id = st.session_state.get('current_analysis_id')
        if current_analysis_id:
            st.markdown("---")

            st.header("📊 股票分析")

            # 使用线程检测来获取真实状态
            from utils.thread_tracker import check_analysis_status
            actual_status = check_analysis_status(current_analysis_id)
            is_running = (actual_status == 'running')

            # 同步session state状态
            if st.session_state.get('analysis_running', False) != is_running:
                st.session_state.analysis_running = is_running
                logger.info(f"🔄 [状态同步] 更新分析状态: {is_running} (基于线程检测: {actual_status})")

            # 获取进度数据用于显示
            from utils.async_progress_tracker import get_progress_by_id
            progress_data = get_progress_by_id(current_analysis_id)

            # 显示分析信息
            if is_running:
                st.info(f"🔄 正在分析: {current_analysis_id}")
            else:
                if actual_status == 'completed':
                    st.success(f"✅ 分析完成: {current_analysis_id}")

                elif actual_status == 'failed':
                    st.error(f"❌ 分析失败: {current_analysis_id}")
                else:
                    st.warning(f"⚠️ 分析状态未知: {current_analysis_id}")

            # 显示进度（根据状态决定是否显示刷新控件）
            progress_col1, progress_col2 = st.columns([4, 1])
            with progress_col1:
                st.markdown("### 📊 分析进度")

            is_completed = display_unified_progress(current_analysis_id, show_refresh_controls=is_running)

            # 如果分析正在进行，显示提示信息
            if is_running:
                st.info("⏱️ 分析正在进行中，可以使用下方的自动刷新功能查看进度更新...")

            # 如果分析刚完成，尝试恢复结果
            if is_completed and not st.session_state.get('analysis_results') and progress_data:
                if 'raw_results' in progress_data:
                    try:
                        from utils.analysis_runner import format_analysis_results
                        raw_results = progress_data['raw_results']
                        formatted_results = format_analysis_results(raw_results)
                        if formatted_results:
                            st.session_state.analysis_results = formatted_results
                            st.session_state.analysis_running = False
                            logger.info(f"📊 [结果同步] 恢复分析结果: {current_analysis_id}")

                            # 检查是否已经刷新过，避免重复刷新
                            refresh_key = f"results_refreshed_{current_analysis_id}"
                            if not st.session_state.get(refresh_key, False):
                                st.session_state[refresh_key] = True
                                st.success("📊 分析结果已恢复，正在刷新页面...")
                                # 使用st.rerun()代替meta refresh，保持侧边栏状态
                                time.sleep(1)
                                st.rerun()
                            else:
                                # 已经刷新过，不再刷新
                                st.success("📊 分析结果已恢复！")
                    except Exception as e:
                        logger.warning(f"⚠️ [结果同步] 恢复失败: {e}")

            if is_completed and st.session_state.get('analysis_running', False):
                # 分析刚完成，更新状态
                st.session_state.analysis_running = False
                st.success("🎉 分析完成！正在刷新页面显示报告...")

                # 使用st.rerun()代替meta refresh，保持侧边栏状态
                time.sleep(1)
                st.rerun()

        # 3. 分析报告区域（只有在有结果且分析完成时才显示）
        current_analysis_id = st.session_state.get('current_analysis_id')
        analysis_results = st.session_state.get('analysis_results')
        analysis_running = st.session_state.get('analysis_running', False)
        image_analysis_report = st.session_state.get('image_analysis_report', '')
        crag_analysis_report = st.session_state.get('crag_analysis_report', '')

        # 检查是否应该显示分析报告
        # 1. 有分析结果且不在运行中
        # 2. 或者用户点击了"查看报告"按钮
        show_results_button_clicked = st.session_state.get('show_analysis_results', False)

        should_show_results = (
                (analysis_results and not analysis_running and current_analysis_id) or
                (show_results_button_clicked and analysis_results)
        )

        # 调试日志
        logger.info(f"🔍 [布局调试] 分析报告显示检查:")
        logger.info(f"  - analysis_results存在: {bool(analysis_results)}")
        logger.info(f"  - analysis_running: {analysis_running}")
        logger.info(f"  - current_analysis_id: {current_analysis_id}")
        logger.info(f"  - show_results_button_clicked: {show_results_button_clicked}")
        logger.info(f"  - should_show_results: {should_show_results}")

        if should_show_results:
            st.markdown("---")
            st.header("📋 专业股票分析报告")
            render_results(analysis_results)
            logger.info(f"✅ [布局] 专业股票分析报告已显示")

            # 清除查看报告按钮状态，避免重复触发
            if show_results_button_clicked:
                st.session_state.show_analysis_results = False

            # 4. 生成最终综合报告（如果有图像分析报告）
            if image_analysis_report and crag_analysis_report and not st.session_state.final_synthesis_report:
                st.markdown("---")
                st.header("📝 生成最终综合分析报告")

                # 只有当用户点击按钮时才生成综合报告
                if st.button("📊 结合图像分析和股票分析生成最终报告"):
                    # 将图像分析报告和股票分析报告转换为文本格式
                    def convert_report_to_text(report):
                        """将结构化报告转换为纯文本"""
                        if not report:
                            return ""

                        text_parts = []

                        # 处理股票分析报告
                        if isinstance(report, dict):
                            # 市场概览
                            if "market_overview" in report:
                                text_parts.append("## 市场概览")
                                text_parts.append(report["market_overview"])

                            # 分析师报告
                            if "analyst_reports" in report:
                                text_parts.append("## 分析师报告")
                                for analyst, content in report["analyst_reports"].items():
                                    text_parts.append(f"### {analyst}")
                                    text_parts.append(content)

                            # 投资辩论
                            if "investment_debate" in report:
                                text_parts.append("## 投资辩论")
                                text_parts.append(report["investment_debate"])

                            # 交易计划
                            if "trading_plan" in report:
                                text_parts.append("## 交易计划")
                                text_parts.append(report["trading_plan"])

                            # 风险分析
                            if "risk_analysis" in report:
                                text_parts.append("## 风险分析")
                                text_parts.append(report["risk_analysis"])

                            # 最终决策
                            if "final_decision" in report:
                                text_parts.append("## 最终决策")
                                text_parts.append(report["final_decision"])
                        else:
                            # 如果不是字典，直接使用文本
                            text_parts.append(str(report))

                        return "\n\n".join(text_parts)

                    # 转换报告格式
                    stock_report_text = convert_report_to_text(analysis_results)

                    # 生成最终综合报告
                    with st.spinner("正在生成最终综合分析报告..."):
                        final_report = generate_final_synthesis_report(
                            image_analysis_report,
                            stock_report_text,
                            crag_analysis_report
                        )
                        st.session_state.final_synthesis_report = final_report

            # 显示最终综合报告（如果已生成）
            if st.session_state.final_synthesis_report:
                st.markdown("---")
                st.header("📝 最终综合分析报告")
                with st.expander("查看最终综合分析报告", expanded=True):
                    st.markdown(st.session_state.final_synthesis_report)

    # 只有在显示指南时才渲染右侧内容
    if show_guide and col2 is not None:
        with col2:
            st.markdown("### ℹ️ 使用指南")

            # 快速开始指南（更新以包含网页分析）
            with st.expander("🎯 快速开始", expanded=True):
                st.markdown("""
                ### 📋 操作步骤

                1. **图像/网页分析（可选）**
                   - **网页分析**: 输入URL并点击"截取网页截图"
                   - **图片分析**: 上传包含股票信息的图片（图表、表格等）
                   - 系统会自动分析并提取股票代码
                   - 从提取的股票代码中选择要分析的股票

                2. **输入股票代码**
                   - A股示例: `000001` (平安银行), `600519` (贵州茅台)
                   - 美股示例: `AAPL` (苹果), `TSLA` (特斯拉)
                   - 港股示例: `00700` (腾讯), `09988` (阿里巴巴)

                   ⚠️ **重要提示**: 输入股票代码后，请按 **回车键** 确认输入！

                3. **选择分析日期**
                   - 默认为今天
                   - 可选择历史日期进行回测分析

                4. **选择分析师团队**
                   - 至少选择一个分析师
                   - 建议选择多个分析师获得全面分析

                5. **设置研究深度**
                   - 1-2级: 快速概览
                   - 3级: 标准分析 (推荐)
                   - 4-5级: 深度研究

                6. **点击开始分析**
                   - 等待专业股票分析完成
                   - 查看详细分析报告
                   - （可选）生成结合图像/网页分析的最终综合报告

                ### 💡 使用技巧

                - **网页分析**: 可分析财经新闻、股票行情、公司财报等网页
                - **图片分析**: 可上传包含股票代码的截图、财报图表等
                - **A股默认**: 系统默认分析A股，无需特殊设置
                - **代码格式**: A股使用6位数字代码 (如 `000001`)
                - **实时数据**: 获取最新的市场数据和新闻
                - **多维分析**: 结合技术面、基本面、情绪面分析
                """)

            # 分析师说明
            with st.expander("👥 分析师团队说明"):
                st.markdown("""
                ### 🎯 专业分析师团队

                - **📈 市场分析师**:
                  - 技术指标分析 (K线、均线、MACD等)
                  - 价格趋势预测
                  - 支撑阻力位分析

                - **💭 社交媒体分析师**:
                  - 投资者情绪监测
                  - 社交媒体热度分析
                  - 市场情绪指标

                - **📰 新闻分析师**:
                  - 重大新闻事件影响
                  - 政策解读分析
                  - 行业动态跟踪

                - **💰 基本面分析师**:
                  - 财务报表分析
                  - 估值模型计算
                  - 行业对比分析
                  - 盈利能力评估

                💡 **建议**: 选择多个分析师可获得更全面的投资建议
                """)

            # 模型选择说明（更新以包含多模态模型）
            with st.expander("🧠 AI模型说明"):
                st.markdown("""
                ### 🤖 智能模型选择

                - **多模态模型**: `doubao-seed-1-6-thinking-250715`
                  - 用于图片/网页分析和最终综合报告生成
                  - 支持图文混合分析
                  - 理解复杂金融图表和表格

                - **qwen-turbo**:
                  - 快速响应，适合快速查询
                  - 成本较低，适合频繁使用
                  - 响应时间: 2-5秒

                - **qwen-plus**:
                  - 平衡性能，推荐日常使用 ⭐
                  - 准确性与速度兼顾
                  - 响应时间: 5-10秒

                - **qwen-max**:
                  - 最强性能，适合深度分析
                  - 最高准确性和分析深度
                  - 响应时间: 10-20秒

                💡 **推荐**: 日常分析使用 `qwen-plus`，重要决策使用 `qwen-max`
                """)

            # 常见问题（更新以包含网页分析相关问题）
            with st.expander("❓ 常见问题"):
                st.markdown("""
                ### 🔍 常见问题解答

                **Q: 网页分析支持哪些类型的网页？**
                A: 支持财经新闻、股票行情、公司财报、金融数据等各类包含股票信息的网页。

                **Q: 为什么网页截图失败？**
                A: 可能原因包括：URL无效、网络连接问题、网站有反爬虫机制、浏览器驱动未正确安装。

                **Q: 图片分析支持哪些类型的图片？**
                A: 支持包含股票代码、财务图表、表格和金融数据的图片，如截图、照片等。

                **Q: 为什么图片/网页分析没有提取到股票代码？**
                A: 可能原因包括：质量太低、股票代码不清晰、内容中没有个股代码。

                **Q: 为什么输入股票代码没有反应？**
                A: 请确保输入代码后按 **回车键** 确认，这是Streamlit的默认行为。

                **Q: A股代码格式是什么？**
                A: A股使用6位数字代码，如 `000001`、`600519`、`000858` 等。

                **Q: 分析需要多长时间？**
                A: 根据研究深度和模型选择，通常需要30秒到2分钟不等。

                **Q: 可以分析港股吗？**
                A: 可以，输入5位港股代码，如 `00700`、`09988` 等。

                **Q: 历史数据可以追溯多久？**
                A: 通常可以获取近5年的历史数据进行分析。
                """)

            # 风险提示
            st.warning("""
            ⚠️ **投资风险提示**

            - 本系统提供的分析结果仅供参考，不构成投资建议
            - 投资有风险，入市需谨慎，请理性投资
            - 请结合多方信息和专业建议进行投资决策
            - 重大投资决策建议咨询专业的投资顾问
            - AI分析存在局限性，市场变化难以完全预测
            """)

        # 显示系统状态
        if st.session_state.last_analysis_time:
            st.info(f"🕒 上次分析时间: {st.session_state.last_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
