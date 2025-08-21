import streamlit as st
import os
import sys
from pathlib import Path
import datetime
import time
import re
import json
from dotenv import load_dotenv
import base64

# 多模态相关库
from PIL import Image
import io

# PDF处理相关库
from pdf2image import convert_from_bytes, convert_from_path
import tempfile

# 网页截图相关库
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 引入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger('web')

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
from components.results_display import render_results
from utils.api_checker import check_api_keys
from utils.analysis_runner import run_stock_analysis, validate_analysis_params, format_analysis_results
from utils.progress_tracker import SmartStreamlitProgressDisplay, create_smart_progress_callback
from utils.async_progress_tracker import AsyncProgressTracker
from components.async_progress_display import display_unified_progress
from utils.smart_session_manager import get_persistent_analysis_id, set_persistent_analysis_id

# 导入新的工具执行器
from planning.tool_executor_with_mcp import ToolExecutor

# 设置页面配置
st.set_page_config(
    page_title="多模态文档洞察分析平台",
    page_icon="🤖",
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
    background-image: url("https://raw.githubusercontent.com/gyz-star/test/main/gi.gif");
    background-size: cover;
    background-position: center;
    padding: 1rem;
    border-radius: 10px;
    margin-bottom: 2rem;
    color: white;
    text-align: center;
    position: relative;
    overflow: hidden;
    margin-top: -100px;
    padding-top: 0;
}

    .metric-card {
    /* 金属渐变背景（银灰→亮银→银灰） */
    background: linear-gradient(
        135deg,
        #e0e5ec 0%,
        #ffffff 40%,
        #d0d9e4 60%,
        #e0e5ec 100%
    );

    /* 让渐变更“拉丝” */
    background-size: 120% 120%;
    animation: metalShine 6s linear infinite;

    /* 内阴影营造厚度 */
    box-shadow:
        inset 1px 1px 2px rgba(255,255,255,0.7),   /* 高光 */
        inset -1px -1px 2px rgba(0,0,0,0.2);     /* 暗部 */

    padding: 1rem;
    border-radius: 10px;
    border-left: 4px solid #1f77b4;
    margin: 0.5rem 0;
}

/* 缓慢移动渐变，制造光泽流动 */
@keyframes metalShine {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
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

    /* 图片、PDF和网页分析区域样式 */
    .document-analysis-container {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #e9ecef;
    }

    .document-preview {
        max-width: 100%;
        border-radius: 5px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    /* PDF页面导航样式 */
    .pdf-navigation {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 1rem 0;
        gap: 1rem;
    }

    .pdf-page-indicator {
        font-weight: bold;
        color: #1f77b4;
    }

    /* 任务流程样式 */
    .task-step {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
    }

    .task-step.active {
        background: #e3f2fd;
        border-left-color: #2196f3;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }

    .task-step.completed {
        border-left-color: #4caf50;
    }

    .task-step.failed {
        border-left-color: #f44336;
    }

    /* 执行计划样式优化 */
    .execution-plan-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        border: 1px solid #e9ecef;
    }

    .plan-module {
        background-color: white;
        border-radius: 6px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    .plan-module-title {
        font-weight: 600;
        color: #2c3e50;
        margin-bottom: 0.8rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #eee;
    }

    .plan-step {
        margin-left: 1rem;
        margin-bottom: 1rem;
        padding-left: 0.8rem;
        border-left: 2px solid #3498db;
    }

    .plan-step-title {
        font-weight: 500;
        color: #34495e;
        margin-bottom: 0.3rem;
    }

    .plan-step-details {
        font-size: 0.9rem;
        color: #7f8c8d;
        margin-bottom: 0.3rem;
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
    if 'extracted_tickers' not in st.session_state:
        st.session_state.extracted_tickers = []
    if 'extracted_companies' not in st.session_state:
        st.session_state.extracted_companies = []
    if 'final_synthesis_report' not in st.session_state:
        st.session_state.final_synthesis_report = ""
    if 'selected_ticker_from_image' not in st.session_state:
        st.session_state.selected_ticker_from_image = None
    if 'image_analysis_completed' not in st.session_state:
        st.session_state.image_analysis_completed = False

    # 新增任务流程相关状态
    if 'task_progress' not in st.session_state:
        st.session_state.task_progress = {
            'stage': 'initial',  # initial, document_analysis, plan_generation, plan_execution, final_report
            'completed_stages': [],  # 新增：跟踪已完成的阶段
            'steps': [],
            'current_step': 0,
            'completed_steps': 0,
            'total_steps': 0,
            'execution_reports': []
        }
    if 'execution_plan' not in st.session_state:
        st.session_state.execution_plan = ""
    if 'module_analysis_reports' not in st.session_state:
        st.session_state.module_analysis_reports = {}

    # PDF分析相关状态变量
    if 'pdf_pages' not in st.session_state:
        st.session_state.pdf_pages = []  # 存储PDF转换的图片
    if 'current_pdf_page' not in st.session_state:
        st.session_state.current_pdf_page = 0  # 当前显示的PDF页码
    if 'pdf_analysis_reports' not in st.session_state:
        st.session_state.pdf_analysis_reports = []  # 存储每一页的分析报告
    if 'pdf_analysis_completed' not in st.session_state:
        st.session_state.pdf_analysis_completed = False  # PDF整体分析是否完成

    # 网页截图相关状态变量
    if 'web_screenshot' not in st.session_state:
        st.session_state.web_screenshot = None  # 存储网页截图
    if 'web_analysis_completed' not in st.session_state:
        st.session_state.web_analysis_completed = False  # 网页分析是否完成

    # 模型配置相关状态
    if 'llm_config' not in st.session_state:
        st.session_state.llm_config = {
            'llm_provider': 'dashscope',
            'llm_model': 'qwen-plus'
        }

    # 工具相关状态
    if 'tool_executor' not in st.session_state:
        st.session_state.tool_executor = None

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
    if 'initial' not in st.session_state.task_progress['completed_stages']:
        st.session_state.task_progress['completed_stages'].append('initial')


def convert_pdf_to_images(pdf_file):
    """将PDF文件转换为图片列表"""
    try:
        # 使用pdf2image将PDF转换为图片
        with st.spinner("正在将PDF转换为图片..."):
            # 转换PDF的每一页为图片
            pages = convert_from_bytes(pdf_file.read(), 300)  # 300 DPI保证清晰度

            # 存储图片的字节流
            image_list = []
            for i, page in enumerate(pages):
                # 将PIL图像转换为字节流
                img_byte_arr = io.BytesIO()
                page.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()

                # 存储图片和页码信息
                image_list.append({
                    'image': page,
                    'bytes': img_byte_arr,
                    'page_number': i + 1
                })

                # 显示进度
                progress = (i + 1) / len(pages)
                st.progress(progress, text=f"转换第 {i + 1}/{len(pages)} 页")

            st.success(f"PDF转换完成，共 {len(image_list)} 页")
            return image_list
    except Exception as e:
        st.error(f"PDF转换失败: {str(e)}")
        logger.error(f"PDF转换错误: {str(e)}")
        return []


def capture_screenshot(url):
    """使用Selenium捕获完整网页截图"""
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

        # 执行JavaScript以隐藏自动化控制特征
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        # 打开目标URL
        with st.spinner(f"正在加载网页: {url}"):
            driver.get(url)

            # 等待页面加载完成
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # 等待额外时间确保JavaScript渲染完成
            time.sleep(3)

        # 获取页面总高度和视口高度
        total_height = driver.execute_script("return document.body.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")

        st.info(f"网页高度: {total_height}px，正在截取完整网页...")

        # 计算需要滚动的次数
        num_scrolls = (total_height + viewport_height - 1) // viewport_height
        screenshots = []

        # 截取每个视口的截图
        for i in range(num_scrolls):
            # 滚动到当前位置
            scroll_position = i * viewport_height
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(1)  # 等待页面稳定

            # 截取当前视口
            screenshot = driver.get_screenshot_as_png()
            img = Image.open(io.BytesIO(screenshot))
            screenshots.append(img)

            # 显示进度
            progress = (i + 1) / num_scrolls
            st.progress(progress, text=f"截取网页部分 {i + 1}/{num_scrolls}")

        # 关闭浏览器
        driver.quit()

        # 拼接所有截图
        if not screenshots:
            st.error("未能捕获到网页截图")
            return None

        # 创建完整截图的画布
        full_image = Image.new('RGB', (screenshots[0].width, total_height))

        # 拼接各个部分
        y_offset = 0
        for img in screenshots:
            full_image.paste(img, (0, y_offset))
            y_offset += img.height

            # 防止超出总高度
            if y_offset > total_height:
                break

        # 裁剪到精确的总高度
        full_image = full_image.crop((0, 0, full_image.width, total_height))

        st.success("网页截图已完成")
        return full_image

    except Exception as e:
        st.error(f"网页截图失败: {str(e)}")
        logger.error(f"网页截图错误: {str(e)}")
        return None


# 多模态文档解析函数 - 第一阶段：分析文档并划分为多个模块
def analyze_document_with_multimodal(document, doc_type="image"):
    """
    使用指定的多模态模型分析图片、PDF文档或网页截图
    提供完整文档分析报告，将内容分为多个模块，并提取个股股票代码
    """
    # 检查是否安装了必要的SDK
    if not has_ark_sdk:
        st.error("volcenginesdkarkruntime not installed. Please install it to use multimodal features.")
        return {"tickers": [], "companies": [], "report": "", "modules": []}

    # 获取API密钥
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        st.error("API key not configured. Please set ARK_API_KEY environment variable.")
        return {"tickers": [], "companies": [], "report": "", "modules": []}

    try:
        # 初始化客户端
        client = Ark(api_key=api_key)
    except Exception as e:
        st.error(f"Failed to initialize SDK client: {str(e)}")
        return {"tickers": [], "companies": [], "report": "", "modules": []}

    try:
        all_tickers = []
        all_companies = []
        all_reports = []
        modules = []

        # 处理PDF文档
        if doc_type == "pdf" and document:
            total_pages = len(document)
            st.info(f"开始分析PDF文档，共 {total_pages} 页...")

            # 为每一页创建进度条
            progress_bar = st.progress(0)

            for i, page_data in enumerate(document):
                page_num = page_data['page_number']
                image = page_data['image']
                img_bytes = page_data['bytes']

                # 更新进度
                progress = (i + 1) / total_pages
                progress_bar.progress(progress, text=f"分析第 {page_num}/{total_pages} 页")

                # 显示当前页图片预览
                with st.expander(f"查看第 {page_num} 页内容", expanded=False):
                    st.image(image, caption=f"PDF第 {page_num} 页", use_container_width=True)

                # 将图片转换为base64编码
                img_str = base64.b64encode(img_bytes).decode()
                image_url = f"data:image/png;base64,{img_str}"

                # 构建提示词，要求完整分析同时专门提取个股股票代码
                prompt = f"""
                请全面分析这张PDF第 {page_num} 页的内容，包括所有财务信息、图表、表格、文本内容和市场数据。

                您的任务是：
                1. 详细解析本页内容，识别所有相关的信息
                2. 将内容划分为有逻辑的模块（例如：行业分析、个股分析、市场趋势等），最多分三个模块，最多只能分为三个模块，必须遵守这条规则
                3. 为每个模块提供详细分析
                4. 不要分析UI界面的交互逻辑，只需要分析内容和数据就行。不要分析UI界面，只需要分析内容和数据就行。不要分析任何与数据和内容无关的东西，不要分析网页界面中的任何模块，是要针对金融领域的内容和数据进行分析。必须遵守这条规则
                5. 必须要提取所有的数据和内容，任何数据都不能省略，必须要保留所有的数据。但是不要分析UI界面中的任何像按钮、筛选、下拉框这些东西。必须遵守这条规则
                6. 如果有数据表必须要保留全部数据，不能有任何省略。但是不要分析UI界面中的任何像按钮、筛选、下拉框这些东西。必须遵守这条规则

                请按以下结构组织您的回答：
                - 总体概述：本页内容的简要总结
                - 模块划分：列出识别出的内容模块
                - 模块分析：对每个模块进行详细分析
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

                # 发送请求到API
                with st.spinner(f"使用 {MULTIMODAL_MODEL} 分析第 {page_num} 页..."):
                    try:
                        resp = client.chat.completions.create(
                            model=MULTIMODAL_MODEL,
                            messages=messages
                        )

                        # 提取模型返回的内容
                        if resp.choices and len(resp.choices) > 0:
                            report = resp.choices[0].message.content
                            all_reports.append(f"## 第 {page_num} 页分析\n{report}")

                            # 从模型响应中提取股票代码和公司信息
                            page_tickers = extract_tickers_from_text(report)
                            page_companies = extract_companies_from_text(report)
                            page_modules = extract_modules_from_text(report)

                            # 添加到总列表
                            all_tickers.extend(page_tickers)
                            all_companies.extend(page_companies)
                            modules.extend(page_modules)

                            st.success(f"第 {page_num} 页分析完成")
                        else:
                            st.warning(f"第 {page_num} 页未返回有效响应")
                            all_reports.append(f"## 第 {page_num} 页分析\n未返回有效响应")

                    except Exception as e:
                        st.error(f"第 {page_num} 页分析失败: {str(e)}")
                        all_reports.append(f"## 第 {page_num} 页分析\n分析失败: {str(e)}")

            # 合并所有报告
            full_report = "\n\n".join(all_reports)

            # 去重处理
            unique_tickers = list(dict.fromkeys(all_tickers))
            # 处理公司名称列表，使其与股票代码列表长度匹配
            unique_companies = []
            seen = set()
            for ticker, company in zip(all_tickers, all_companies):
                if ticker not in seen:
                    seen.add(ticker)
                    unique_companies.append(company)

            # 去重模块
            unique_modules = []
            seen_modules = set()
            for module in modules:
                if module not in seen_modules:
                    seen_modules.add(module)
                    unique_modules.append(module)

            # 保存到会话状态
            st.session_state.image_analysis_report = full_report
            st.session_state.extracted_tickers = unique_tickers
            st.session_state.extracted_companies = unique_companies
            st.session_state.pdf_analysis_completed = True
            st.session_state.image_analysis_completed = True
            st.session_state.web_analysis_completed = False

            # 更新任务进度
            st.session_state.task_progress['stage'] = 'document_analysis'
            st.session_state.task_progress['modules'] = unique_modules
            # 标记当前阶段为已完成
            if 'document_analysis' not in st.session_state.task_progress['completed_stages']:
                st.session_state.task_progress['completed_stages'].append('document_analysis')

            # 如果有提取到股票，默认选择第一个
            if unique_tickers:
                st.session_state.selected_ticker_from_image = unique_tickers[0]

            return {
                "tickers": unique_tickers,
                "companies": unique_companies,
                "report": full_report,
                "modules": unique_modules
            }

        # 处理图片文件或网页截图
        elif doc_type in ["image", "web"] and document:
            # 显示图片预览
            st.image(document, caption="网页截图" if doc_type == "web" else "上传的图片", use_container_width=True,
                     output_format="PNG")

            # 将图片转换为base64编码
            buffered = io.BytesIO()
            document.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            image_url = f"data:image/png;base64,{img_str}"

            # 根据文档类型调整提示词
            content_type = "网页" if doc_type == "web" else "图片"

            prompt = f"""
            请全面分析这张{content_type}中的内容，包括所有财务信息、图表、表格、文本内容和市场数据。

            您的任务是：
            1. 详细解析{content_type}内容，识别所有相关的信息
            2. 将内容划分为有逻辑的模块（例如：行业分析、个股分析、市场趋势等）
            3. 为每个模块提供详细分析
            4. 不要分析UI界面的交互逻辑，只需要分析内容和数据就行。不要分析UI界面，只需要分析内容和数据就行。不要分析任何与数据和内容无关的东西，不要分析网页界面中的任何模块，是要针对金融领域的内容和数据进行分析。必须遵守这条规则
            5. 必须要提取所有的数据和内容，任何数据都不能省略，必须要保留所有的数据。但是不要分析UI界面中的任何像按钮、筛选、下拉框这些东西。必须遵守这条规则
            6. 如果有数据表必须要保留全部数据，不能有任何省略。但是不要分析UI界面中的任何像按钮、筛选、下拉框这些东西。必须遵守这条规则

            请按以下结构组织您的回答：
            - 总体概述：{content_type}内容的简要总结
            - 模块划分：列出识别出的内容模块
            - 模块分析：对每个模块进行详细分析

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

            # 发送请求到API
            with st.spinner(f"使用 {MULTIMODAL_MODEL} 多模态模型分析{content_type}中..."):
                try:
                    resp = client.chat.completions.create(
                        model=MULTIMODAL_MODEL,
                        messages=messages
                    )

                    # 提取模型返回的内容
                    if resp.choices and len(resp.choices) > 0:
                        report = resp.choices[0].message.content
                        st.success(f"{content_type}分析成功完成")

                        # 从模型响应中提取股票代码、公司信息和模块
                        extracted_tickers = extract_tickers_from_text(report)
                        extracted_tickers = list(dict.fromkeys(extracted_tickers))

                        extracted_companies = extract_companies_from_text(report)
                        if len(extracted_companies) > len(extracted_tickers):
                            extracted_companies = extracted_companies[:len(extracted_tickers)]
                        elif len(extracted_companies) < len(extracted_tickers):
                            extracted_companies += ["未知公司"] * (len(extracted_tickers) - len(extracted_companies))

                        modules = extract_modules_from_text(report)
                        unique_modules = list(dict.fromkeys(modules))

                        # 保存到会话状态
                        st.session_state.image_analysis_report = report
                        st.session_state.extracted_tickers = extracted_tickers
                        st.session_state.extracted_companies = extracted_companies

                        # 根据文档类型设置相应的完成状态
                        if doc_type == "web":
                            st.session_state.web_analysis_completed = True
                            st.session_state.image_analysis_completed = False
                            st.session_state.pdf_analysis_completed = False
                        else:
                            st.session_state.image_analysis_completed = True
                            st.session_state.pdf_analysis_completed = False
                            st.session_state.web_analysis_completed = False

                        # 更新任务进度
                        st.session_state.task_progress['stage'] = 'document_analysis'
                        st.session_state.task_progress['modules'] = unique_modules
                        # 标记当前阶段为已完成
                        if 'document_analysis' not in st.session_state.task_progress['completed_stages']:
                            st.session_state.task_progress['completed_stages'].append('document_analysis')

                        # 如果有提取到股票，默认选择第一个
                        if extracted_tickers:
                            st.session_state.selected_ticker_from_image = extracted_tickers[0]

                        return {
                            "tickers": extracted_tickers,
                            "companies": extracted_companies,
                            "report": report,
                            "modules": unique_modules
                        }
                    else:
                        st.warning(f"{content_type}模型未返回有效响应。")
                        return {"tickers": [], "companies": [], "report": "", "modules": []}

                except Exception as e:
                    st.error(f"API请求失败: {str(e)}")
                    return {"tickers": [], "companies": [], "report": "", "modules": []}

        else:
            st.warning("未提供有效的文档进行分析")
            return {"tickers": [], "companies": [], "report": "", "modules": []}

    except Exception as e:
        st.error(f"文档分析错误: {str(e)}")
        return {"tickers": [], "companies": [], "report": "", "modules": []}


# 生成执行计划 - 第二阶段
def generate_execution_plan(document_report, modules):
    """根据初步分析报告和模块生成详细的多层级执行计划，明确步骤间依赖关系"""
    if not has_ark_sdk:
        return "volcenginesdkarkruntime not installed. Cannot generate execution plan."

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        return "API key not configured. Cannot generate execution plan."

    try:
        client = Ark(api_key=api_key)
    except Exception as e:
        return f"Failed to initialize SDK client: {str(e)}"

    tool_executor = ToolExecutor()
    AVAILABLE_TOOLS = ToolExecutor.generate_available_tools(tool_executor)

    # 改进的提示词：明确要求标注步骤间依赖关系
    prompt = f"""
    根据以下文档分析报告和识别出的内容模块，为接下来的深度解析生成详细的多层级执行计划。
    执行计划应具有视觉吸引力，层次分明，易于阅读和理解。
    绝对强制要求：计划中不需要验证信息准确性与完整性和一致性什么的，步骤中不允许出现对信息准确性、完整性和一致性的验证。不允许出现任何验证计划，不允许验证，不需要验证任何数据和内容
    {AVAILABLE_TOOLS}

    文档分析报告:
    {document_report}

    识别出的内容模块:
    {', '.join(modules)}

    您的任务是:
    1. 为每个模块设计1-2个详细的分析步骤，形成清晰的层级结构
    2. 绝对强制要求：计划中不需要验证信息准确性与完整性和一致性什么的，步骤中不允许出现对信息准确性、完整性和一致性的验证。不允许出现任何验证计划，不允许验证，不需要验证任何数据和内容
    3. 每个步骤必须有明确的目标和预期输出
    4. 明确每个步骤是否需要使用工具，如需要，说明工具名称和参数
    5. 使用的工具必须是工具列表中存在的工具，严格禁止使用工具列表中不存在的工具
    6. 使用的工具必须和内容相关，不允许在不存在工具参数的时候使用工具
    7. 必须严格基于报告生成工具调用参数，绝对不允许编造参数
    8. 绝对强制要求：计划中不需要验证信息准确性与完整性，步骤中不允许出现对信息准确性和完整性的验证
    9. 如果工具和当前步骤高度相关，但工具所需必要参数难以从报告中提取，则不选择调用该工具
       - 当前日期为 {str(datetime.date.today())}
       - 如果工具需要日期参数但报告中未明确指出报告日期，则对于需要给出单个日期的工具选择当前日期作为输入参数，对于需要给出范围日期的工具选择最近一周作为输入参数，绝对不允许自行假设日期参数
    10. 确保计划逻辑清晰，按合理顺序排列
    11. **关键要求：明确步骤间依赖关系**  
       - 如果步骤B需要使用步骤A的输出结果，则必须在步骤B中注明“依赖步骤：A的ID”  
       - 例如：步骤1.b依赖步骤1.a的结果，则在步骤1.b中添加“依赖步骤：1.a”  
    12. 使用清晰的标题和格式，使计划易于阅读和理解
    13. 绝对强制要求：必须基于真实的内容设计计划，不允许任何假设或编造！
    14. 每个步骤只能选择一个工具调用
    15. 计划中不需要验证信息准确性与完整性。不允许出现任何验证计划，不允许验证，不需要验证任何数据和内容
    16. 计划主要应该是解决文档分析中对文档内容分析为什么，怎么做的问题
    17. 工具参数即使有默认值也必须要显式给出参数值  

    执行计划必须采用以下严格格式，使用数字和字母编号区分模块和步骤：
    # 总体分析目标
    [简要描述整体分析目标]

    # 模块分析计划
    ## 1. [模块名称1]
       ### a. 步骤1: [步骤名称]
          - 分析内容: [详细描述需要分析的内容]
          - 使用工具: [是/否，如果是，说明工具名称]
          - 参数: [如使用工具，列出所需参数]
          - 预期输出: [描述该步骤的预期结果]
          - 依赖步骤: [如果有依赖，填写依赖的步骤ID，如"1.a"；无依赖则填"无"]
       ### b. 步骤2: [步骤名称]
          - 分析内容: [详细描述需要分析的内容]
          - 使用工具: [是/否，如果是，说明工具名称]
          - 参数: [如使用工具，列出所需参数]
          - 预期输出: [描述该步骤的预期结果]
          - 依赖步骤: [如果有依赖，填写依赖的步骤ID，如"1.a"；无依赖则填"无"]
       ...
    ## 2. [模块名称2]
       ### a. 步骤1: [步骤名称]
          - 分析内容: [详细描述需要分析的内容]
          - 使用工具: [是/否，如果是，说明工具名称]
          - 参数: [如使用工具，列出所需参数]
          - 预期输出: [描述该步骤的预期结果]
          - 依赖步骤: [如果有依赖，填写依赖的步骤ID，如"1.b"；无依赖则填"无"]
       ...

    # 计划执行顺序
    [说明模块和步骤的执行顺序，如：1.a → 1.b → 2.a → ...]
    """

    try:
        with st.spinner(f"使用 {MULTIMODAL_MODEL} 生成执行计划中..."):
            resp = client.chat.completions.create(
                model=MULTIMODAL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            )

            if resp.choices and len(resp.choices) > 0:
                plan = resp.choices[0].message.content
                st.session_state.execution_plan = plan
                st.session_state.task_progress['stage'] = 'plan_generation'
                if 'plan_generation' not in st.session_state.task_progress['completed_stages']:
                    st.session_state.task_progress['completed_stages'].append('plan_generation')

                # 解析计划步骤并更新任务进度
                steps = extract_steps_from_plan(plan)
                st.session_state.task_progress['steps'] = steps
                st.session_state.task_progress['total_steps'] = len(steps)
                st.session_state.task_progress['current_step'] = 0
                st.session_state.task_progress['completed_steps'] = 0

                return plan
            else:
                return "模型未返回有效响应，无法生成执行计划"

    except Exception as e:
        return f"生成执行计划失败: {str(e)}"


# 新增：验证工具输出是否符合步骤要求
def validate_tool_output(step, tool_output):
    """使用大模型验证工具输出是否符合步骤要求"""
    if not has_ark_sdk:
        return {"matches": False, "reason": "volcenginesdkarkruntime not installed"}

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        return {"matches": False, "reason": "API key not configured"}

    try:
        client = Ark(api_key=api_key)
    except Exception as e:
        return {"matches": False, "reason": f"Failed to initialize SDK client: {str(e)}"}

    prompt = f"""
    请判断以下工具执行结果是否符合步骤要求：

    步骤信息：
    - 步骤名称: {step.get('name', '未命名步骤')}
    - 分析内容: {step.get('content', '无内容')}
    - 预期输出: {step.get('expected_output', '无预期输出')}
    - 使用工具: {step.get('tool', '无工具')}
    - 请求参数: {json.dumps(step.get('parameters', {}), ensure_ascii=False)}

    工具执行结果：
    {tool_output}

    您的判断标准：
    1. 工具返回的数据是否能够满足该步骤的分析需求
    2. 返回的数据是否与请求参数相关
    3. 数据是否完整到可以基于此进行下一步分析

    请返回一个JSON对象，包含：
    - "matches": 布尔值，表示结果是否符合要求
    - "reason": 字符串，说明判断理由
    - "missing_info": 字符串数组，列出缺失的关键信息（如无缺失则为空数组）
    """

    try:
        resp = client.chat.completions.create(
            model=MULTIMODAL_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ]
        )

        if resp.choices and len(resp.choices) > 0:
            result_text = resp.choices[0].message.content
            # 清理可能的格式问题
            result_text = result_text.strip()
            if result_text.startswith('```json'):
                result_text = result_text[7:-3].strip()
            elif result_text.startswith('```'):
                result_text = result_text[3:-3].strip()

            return json.loads(result_text)
        else:
            return {
                "matches": False,
                "reason": "模型未返回有效响应",
                "missing_info": []
            }

    except json.JSONDecodeError as e:
        return {
            "matches": False,
            "reason": f"解析验证结果失败: {str(e)}",
            "missing_info": []
        }
    except Exception as e:
        return {
            "matches": False,
            "reason": f"验证工具输出失败: {str(e)}",
            "missing_info": []
        }


# 新增：根据工具输出调整步骤
def adjust_step_based_on_output(current_step, tool_output, validation_result, all_steps, completed_steps):
    """根据工具输出和验证结果调整步骤"""
    if not has_ark_sdk:
        return None, "volcenginesdkarkruntime not installed"

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        return None, "API key not configured"

    try:
        client = Ark(api_key=api_key)
    except Exception as e:
        return None, f"Failed to initialize SDK client: {str(e)}"

    tool_executor = ToolExecutor()
    AVAILABLE_TOOLS = ToolExecutor.generate_available_tools(tool_executor)

    # 收集已完成步骤的信息
    completed_steps_info = []
    for step in completed_steps:
        completed_steps_info.append({
            "step_id": step.get('full_step_id', ''),
            "name": step.get('name', ''),
            "tool": step.get('tool', ''),
            "output_summary": f"{str(step.get('tool_output', ''))[:200]}..."
        })

    prompt = f"""
    由于工具执行结果不符合预期，需要重新设计当前步骤。
    绝对强制要求：新步骤必须基于已获取的数据来设计步骤计划，不允许再要求获取其他数据。例如之前工具返回的数据是实时数据，没有近一个月或者近一年的数据，那就必须调整步骤为要求获取实时数据的步骤。而不是继续要求获取历史数据。

    {AVAILABLE_TOOLS}

    当前步骤信息：
    - 步骤ID: {current_step.get('full_step_id', '未知')}
    - 步骤名称: {current_step.get('name', '未命名步骤')}
    - 所属模块: {current_step.get('module', '未分类模块')}
    - 原分析内容: {current_step.get('content', '无内容')}
    - 原使用工具: {current_step.get('tool', '无工具')}
    - 原请求参数: {json.dumps(current_step.get('parameters', {}), ensure_ascii=False)}
    - 原预期输出: {current_step.get('expected_output', '无预期输出')}

    工具实际执行结果：
    {tool_output}

    验证结果：
    - 是否符合预期: {'是' if validation_result.get('matches', False) else '否'}
    - 原因: {validation_result.get('reason', '无')}
    - 缺失信息: {', '.join(validation_result.get('missing_info', [])) or '无'}

    已完成的步骤：
    {json.dumps(completed_steps_info, ensure_ascii=False, indent=2)}

    您的任务：
    1. 基于实际工具输出和已完成步骤的结果，重新设计当前步骤
    2. 绝对强制要求：新步骤必须基于已获取的数据来设计步骤计划，不允许再要求获取其他数据。例如之前工具返回的数据是实时数据，没有近一个月或者近一年的数据，那就必须调整步骤为要求获取实时数据的步骤。而不是继续要求获取历史数据。
    3. 调整使用的工具或参数，确保能够获得有效的分析结果
    4. 保持与其他步骤的依赖关系，但可以适当调整
    5. 必须使用工具列表中存在的工具，参数必须基于已有信息
    6. 工具参数即使有默认值也必须要显示给出参数值
    7. 当前日期为 {str(datetime.date.today())}
    8. 每个步骤只能选择一个工具调用，不允许使用多个工具

    请返回一个JSON对象，包含调整后的步骤信息：
    {{
        "name": "新步骤名称",
        "content": "新的分析内容",
        "uses_tool": true/false,
        "tool": "工具名称（如果使用工具）",
        "parameters": {{
            "参数名称1": "参数值1",
            "参数名称2": "参数值2"
        }},
        "expected_output": "调整后的预期输出",
        "depends_on": ["依赖的步骤ID列表"]
    }}
    """

    try:
        with st.spinner(f"使用 {MULTIMODAL_MODEL} 调整分析步骤..."):
            resp = client.chat.completions.create(
                model=MULTIMODAL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            )

            if resp.choices and len(resp.choices) > 0:
                result_text = resp.choices[0].message.content
                # 清理可能的格式问题
                result_text = result_text.strip()
                if result_text.startswith('```json'):
                    result_text = result_text[7:-3].strip()
                elif result_text.startswith('```'):
                    result_text = result_text[3:-3].strip()

                adjusted_step = json.loads(result_text)
                # 保留模块和ID信息
                adjusted_step['module'] = current_step.get('module', '未分类模块')
                adjusted_step['module_id'] = current_step.get('module_id', '')
                adjusted_step['step_id'] = current_step.get('step_id', '')
                adjusted_step['full_step_id'] = current_step.get('full_step_id', '')

                return adjusted_step, "步骤调整成功"
            else:
                return None, "模型未返回有效响应，无法调整步骤"

    except json.JSONDecodeError as e:
        return None, f"解析调整结果失败: {str(e)}"
    except Exception as e:
        return None, f"调整步骤失败: {str(e)}"


# 执行计划 - 第三阶段
def execute_plan(plan, progress_callback=None):
    # 初始化工具执行器
    if st.session_state.tool_executor is None:
        st.session_state.tool_executor = ToolExecutor()
    tool_executor = st.session_state.tool_executor

    """按照执行计划执行分析步骤，仅向模型传递必要的前置步骤信息"""
    if not plan:
        return []

    # 提取计划中的步骤
    steps = st.session_state.task_progress.get('steps', [])
    if not steps:
        steps = extract_steps_from_plan(plan)
        st.session_state.task_progress['steps'] = steps
        st.session_state.task_progress['total_steps'] = len(steps)
        st.session_state.task_progress['current_step'] = 0
        st.session_state.task_progress['completed_steps'] = 0

    # 如果所有步骤都已完成，返回
    if st.session_state.task_progress['current_step'] >= st.session_state.task_progress['total_steps']:
        if 'plan_execution' not in st.session_state.task_progress['completed_stages']:
            st.session_state.task_progress['completed_stages'].append('plan_execution')
        return st.session_state.task_progress.get('execution_reports', [])

    # 执行当前步骤
    execution_reports = st.session_state.task_progress.get('execution_reports', [])
    current_step_idx = st.session_state.task_progress['current_step']
    step = steps[current_step_idx]
    step_name = step.get('name', f"步骤 {current_step_idx + 1}")
    module_name = step.get('module', "未分类模块")

    if progress_callback:
        progress_callback(f"正在执行 {module_name} - {step_name}", current_step_idx, len(steps))

    # 收集依赖的步骤信息（仅用于模型分析）
    dependencies = []
    if step.get('depends_on', []):
        # 查找所有已完成的步骤报告
        completed_reports = [r for r in execution_reports if r['status'] == 'completed']

        # 为每个依赖的步骤ID查找对应的报告
        for dep_step_id in step['depends_on']:
            # 查找对应的步骤
            dep_step = next((s for s in steps if s['full_step_id'] == dep_step_id), None)
            if dep_step:
                # 查找该步骤的报告
                dep_report = next(
                    (r for r in completed_reports if r['step'] == steps.index(dep_step) + 1),
                    None
                )
                if dep_report:
                    dependencies.append({
                        'step_id': dep_step_id,
                        'step_name': dep_step['name'],
                        'report': dep_report['report'],
                        'tool_output': dep_report.get('tool_output', None)
                    })

    # 显示当前执行步骤和依赖信息
    with st.expander(f"🔄 正在执行 [{module_name}]: {step_name}", expanded=True):
        st.write(f"**分析内容**: {step.get('content', '未指定')}")
        st.write(f"**是否使用工具**: {step.get('uses_tool', '否')}")

        # 显示依赖信息
        if dependencies:
            with st.expander("查看依赖的前置步骤信息", expanded=False):
                for dep in dependencies:
                    st.markdown(f"**来自步骤 {dep['step_id']}: {dep['step_name']} 的信息:**")
                    st.markdown(dep['report'])

        try:
            # 准备传递给模型的依赖信息
            dependency_context = "\n\n".join([
                f"来自步骤 {dep['step_id']} ({dep['step_name']}) 的信息:\n{dep['report']}"
                for dep in dependencies
            ])

            tool_output = None
            if step.get('uses_tool', False):
                # 执行工具时不传递依赖信息，只使用原始参数
                tool_output = tool_executor.execute(
                    tool_name=step.get('tool', ''),
                    parameters=step.get('parameters', {}),
                )

                # 显示工具输出
                st.info("工具执行完成，正在验证结果...")
                with st.expander("查看工具原始输出", expanded=False):
                    st.code(tool_output)

                # 验证工具输出是否符合预期
                validation_result = validate_tool_output(step, tool_output)

                # 显示验证结果
                if validation_result.get('matches', False):
                    st.success(f"✅ 工具输出符合步骤要求: {validation_result.get('reason', '')}")
                else:
                    st.warning(f"⚠️ 工具输出不符合预期: {validation_result.get('reason', '')}")
                    if validation_result.get('missing_info', []):
                        st.info(f"缺失信息: {', '.join(validation_result.get('missing_info', []))}")

                    # 尝试调整步骤
                    st.info("正在尝试调整步骤...")
                    completed_steps = steps[:current_step_idx]  # 获取已完成的步骤
                    adjusted_step, adjust_msg = adjust_step_based_on_output(
                        step, tool_output, validation_result, steps, completed_steps
                    )

                    if adjusted_step:
                        st.success(f"步骤已调整: {adjust_msg}")
                        # 更新当前步骤为调整后的步骤
                        steps[current_step_idx] = adjusted_step
                        st.session_state.task_progress['steps'] = steps

                        # 重新执行调整后的步骤
                        with st.expander("查看调整后的步骤", expanded=True):
                            st.json(adjusted_step)

                        # 使用调整后的步骤重新执行工具调用
                        if adjusted_step.get('uses_tool', False):
                            tool_output = tool_executor.execute(
                                tool_name=adjusted_step.get('tool', ''),
                                parameters=adjusted_step.get('parameters', {}),
                            )
                            st.info("使用调整后的参数重新执行工具...")
                            with st.expander("查看调整后工具的原始输出", expanded=False):
                                st.code(tool_output)
                        else:
                            st.info("调整后的步骤不使用工具，直接进行分析...")
                    else:
                        st.error(f"无法调整步骤: {adjust_msg}，将基于现有结果继续分析")

                # 将工具输出和依赖信息一起输入大模型生成报告
                report_text = analyze_step_with_model(step, tool_output=tool_output, dependencies=dependencies)
            else:
                # 直接调用模型进行分析，传递依赖信息
                st.info("正在进行文本分析...")
                report_text = analyze_step_with_model(step, dependencies=dependencies)

            # 更新执行报告
            step_report = {
                'step': current_step_idx + 1,
                'module': module_name,
                'name': step_name,
                'report': report_text,
                'status': 'completed',
                'tool_output': tool_output if step.get('uses_tool', False) else None,
                'validation_result': validation_result if step.get('uses_tool', False) else None
            }

            if current_step_idx < len(execution_reports):
                execution_reports[current_step_idx] = step_report
            else:
                execution_reports.append(step_report)

            # 更新会话状态
            st.session_state.task_progress['completed_steps'] = current_step_idx + 1
            st.session_state.task_progress['current_step'] = current_step_idx + 1
            st.session_state.task_progress['execution_reports'] = execution_reports

            st.success(f"✅ {module_name} - {step_name} 执行完成")

        except Exception as e:
            error_msg = f"步骤 {current_step_idx + 1} 执行失败: {str(e)}"
            if current_step_idx < len(execution_reports):
                execution_reports[current_step_idx] = {
                    'step': current_step_idx + 1,
                    'module': module_name,
                    'name': step_name,
                    'report': error_msg,
                    'status': 'failed'
                }
            else:
                execution_reports.append({
                    'step': current_step_idx + 1,
                    'module': module_name,
                    'name': step_name,
                    'report': error_msg,
                    'status': 'failed'
                })

            st.session_state.task_progress['execution_reports'] = execution_reports
            st.error(error_msg)

    # 更新任务进度状态
    st.session_state.task_progress['stage'] = 'plan_execution'
    st.rerun()

    return execution_reports


# 使用模型分析单个步骤
def analyze_step_with_model(step, tool_output=None, dependencies=None):
    """使用模型分析单个步骤，接收工具输出和依赖信息"""
    if not has_ark_sdk:
        return "volcenginesdkarkruntime not installed. Cannot analyze step."

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        return "API key not configured. Cannot analyze step."

    try:
        client = Ark(api_key=api_key)
    except Exception as e:
        return f"Failed to initialize SDK client: {str(e)}"

    # 基础提示信息
    prompt_parts = [
        "请根据以下分析步骤要求，进行详细分析并生成报告：",
        f"\n分析步骤:",
        f"模块: {step.get('module', '未命名模块')}",
        f"名称: {step.get('name', '未命名步骤')}",
        f"内容: {step.get('content', '无内容')}",
        f"预期输出: {step.get('expected_output', '无预期输出')}",
        f"\n文档初步分析信息:",
        f"{st.session_state.image_analysis_report}..."
    ]

    # 添加依赖信息（仅模型使用）
    if dependencies and len(dependencies) > 0:
        prompt_parts.append("\n相关前置步骤信息:")
        for i, dep in enumerate(dependencies):
            prompt_parts.append(f"步骤 {dep['step_id']} ({dep['step_name']}) 的分析结果:")
            prompt_parts.append(f"{dep['report']}")

    # 如果有工具输出，添加到提示中
    if tool_output:
        prompt_parts.extend([
            "\n工具执行结果:",
            f"{tool_output}",
            "\n请基于上述工具执行结果、前置步骤信息和分析步骤要求，生成分析报告。"
        ])
    else:
        prompt_parts.append("\n请基于前置步骤信息（如有时）和分析步骤要求，提供详细分析报告。")

    # 合并所有提示部分
    prompt = "\n".join(prompt_parts)

    try:
        resp = client.chat.completions.create(
            model=MULTIMODAL_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ]
        )

        if resp.choices and len(resp.choices) > 0:
            return resp.choices[0].message.content
        else:
            return "模型未返回有效响应，无法完成此步骤分析"

    except Exception as e:
        return f"分析步骤失败: {str(e)}"


# 生成最终综合报告 - 第四阶段
def generate_final_synthesis_report():
    """整合所有分析报告生成最终综合报告"""
    if not has_ark_sdk:
        return "volcenginesdkarkruntime not installed. Cannot generate synthesis report."

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        return "API key not configured. Cannot generate synthesis report."

    try:
        client = Ark(api_key=api_key)
    except Exception as e:
        return f"Failed to initialize SDK client: {str(e)}"

    # 收集所有报告
    document_report = st.session_state.get('image_analysis_report', '')
    execution_plan = st.session_state.get('execution_plan', '')
    execution_reports = st.session_state.task_progress.get('execution_reports', [])

    # 构建执行报告文本
    execution_reports_text = ""
    for report in execution_reports:
        execution_reports_text += f"## 步骤 {report['step']} [{report['module']}]: {report['name']}\n{report['report']}\n\n"

    prompt = f"""
    作为资深金融分析师，请将以下所有分析内容整合成一份全面、深入的最终综合报告：

    1. 文档初步分析报告：
    {document_report}

    2. 执行计划：
    {execution_plan}

    3. 各步骤执行结果：
    {execution_reports_text}

    您的最终综合报告应：
    - 保留所有之前分析报告的关键内容
    - 按逻辑顺序组织，结构清晰
    - 增加更深入的分析和见解
    - 使用专业的术语，同时保持可读性
    - 要保证所有数据绝对真实准确，存在缺失数据不允许说缺失数据，而是应该改变分析策略，不分析没有数据的这部分
    """

    try:
        with st.spinner(f"使用 {MULTIMODAL_MODEL} 生成最终综合报告中..."):
            resp = client.chat.completions.create(
                model=MULTIMODAL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            )

            if resp.choices and len(resp.choices) > 0:
                final_report = resp.choices[0].message.content
                st.session_state.final_synthesis_report = final_report
                st.session_state.task_progress['stage'] = 'final_report'
                # 标记当前阶段为已完成
                if 'final_report' not in st.session_state.task_progress['completed_stages']:
                    st.session_state.task_progress['completed_stages'].append('final_report')
                return final_report
            else:
                return "模型未返回有效响应，无法生成综合报告"

    except Exception as e:
        return f"生成综合报告失败: {str(e)}"


# 辅助函数：从文本中提取股票代码
def extract_tickers_from_text(text):
    """提取A股股票代码（6位数字）"""
    # 定位模型报告中明确标注个股代码的部分
    start_markers = ["个股股票代码", "股票代码", "A股代码"]
    end_markers = ["公司名称", "模块分析", "总体概述", "模块划分"]

    # 尝试所有可能的起始标记
    start_idx = -1
    for marker in start_markers:
        start_idx = text.find(marker)
        if start_idx != -1:
            break

    if start_idx != -1:
        # 尝试所有可能的结束标记
        end_idx = len(text)
        for marker in end_markers:
            temp_idx = text.find(marker, start_idx)
            if temp_idx != -1:
                end_idx = temp_idx
                break

        # 提取从起始标记到结束标记之间的内容
        code_section = text[start_idx:end_idx].strip()
    else:
        # 如果没有明确标记，搜索整个文本
        code_section = text

    # 提取6位数字的A股代码
    pattern = r'\b\d{6}\b'
    tickers = re.findall(pattern, code_section)

    # 去重并返回
    return list(dict.fromkeys(tickers))


# 辅助函数：从文本中提取公司名称
def extract_companies_from_text(text):
    """提取公司名称"""
    start_markers = ["公司名称", "对应的公司名称"]
    end_markers = ["模块分析", "总体概述", "模块划分", "个股股票代码"]

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
            cleaned_line = re.sub(r'\b\d{6}\b', '', cleaned_line).strip()
            companies.append(cleaned_line)

    # 去重
    return list(dict.fromkeys(companies))


# 辅助函数：从文本中提取模块
def extract_modules_from_text(text):
    """从分析报告中提取内容模块"""
    start_markers = ["模块划分", "内容模块", "识别出的模块"]
    end_markers = ["模块分析", "总体概述", "个股股票代码", "公司名称"]

    # 尝试所有可能的起始标记
    start_idx = -1
    for marker in start_markers:
        start_idx = text.find(marker)
        if start_idx != -1:
            break

    if start_idx == -1:
        # 如果没有明确的模块划分，尝试从分析中提取
        return extract_implied_modules(text)

    # 尝试所有可能的结束标记
    end_idx = len(text)
    for marker in end_markers:
        temp_idx = text.find(marker, start_idx)
        if temp_idx != -1:
            end_idx = temp_idx
            break

    # 提取模块部分
    module_section = text[start_idx:end_idx].strip()

    # 提取模块名称
    modules = []
    # 按行分割
    lines = [line.strip() for line in module_section.split('\n') if line.strip()]

    for line in lines:
        # 跳过标记行
        if any(marker in line for marker in start_markers):
            continue
        if line.startswith('#'):
            continue

        # 移除可能的编号前缀（如1. 2. 等）
        cleaned_line = re.sub(r'^\d+\.\s*', '', line)

        if len(cleaned_line) > 2:  # 过滤过短的条目
            modules.append(cleaned_line)

    # 去重
    return list(dict.fromkeys(modules))


# 辅助函数：从文本中提取隐含的模块
def extract_implied_modules(text):
    """当没有明确模块划分时，从分析中提取隐含的模块"""
    possible_modules = [
        "行业分析", "个股分析", "市场趋势", "财务分析",
        "投资建议", "风险评估", "宏观经济", "政策分析",
        "市场情绪", "技术分析", "估值分析", "业绩预测"
    ]

    found_modules = []
    for module in possible_modules:
        if module in text:
            found_modules.append(module)

    # 如果没有找到任何模块，返回默认模块
    if not found_modules:
        return ["总体市场分析", "个股分析", "投资建议"]

    return found_modules


# 使用大模型提取步骤结构，替代正则表达式
def extract_steps_from_plan(plan_text):
    """使用大模型从执行计划文本中提取多层级步骤结构，包括步骤间依赖关系"""
    if not has_ark_sdk:
        st.error("volcenginesdkarkruntime 未安装，无法提取步骤结构")
        return []

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        st.error("API key 未配置，无法提取步骤结构")
        return []

    try:
        client = Ark(api_key=api_key)
    except Exception as e:
        st.error(f"初始化 SDK 客户端失败: {str(e)}，无法提取步骤结构")
        return []

    # 定义期望的JSON结构，增加了依赖关系字段
    expected_format = {
        "overall_goal": "总体分析目标的简要描述",
        "modules": [
            {
                "module_id": "模块编号，如1",
                "module_name": "模块名称",
                "steps": [
                    {
                        "step_id": "步骤编号，如a",
                        "step_name": "步骤名称",
                        "content": "分析内容的详细描述",
                        "uses_tool": "布尔值，true或false",
                        "tool": "工具名称，如果uses_tool为true",
                        "parameters": {
                            "参数名称1": "参数值1",
                            "参数名称2": "参数值2"
                        },
                        "expected_output": "该步骤的预期结果",
                        "depends_on": ["1.a", "2.b"]  # 新增：依赖的步骤ID列表，为空表示无依赖
                    }
                ]
            }
        ],
        "execution_order": ["1.a", "1.b", "2.a", "..."]  # 执行顺序列表
    }

    prompt = f"""
    请分析以下执行计划文本，并将其转换为结构化的JSON数据。
    你的任务是识别出所有模块、每个模块下的步骤，每个步骤的详细信息，以及步骤之间的依赖关系。

    执行计划文本:
    {plan_text}

    依赖关系说明:
    - 如果步骤B需要使用步骤A的输出结果，则步骤B的"depends_on"应包含步骤A的ID
    - 如果步骤不需要任何其他步骤的输出，则"depends_on"应为空列表
    - 依赖关系必须严格基于执行计划中的明确说明

    请严格按照以下JSON格式返回结果，不要添加任何额外解释：
    {json.dumps(expected_format, ensure_ascii=False, indent=2)}

    注意事项:
    1. 确保JSON格式正确，可被标准JSON解析器解析
    2. "uses_tool"字段应为布尔值(true/false)
    3. "tool"字段只包含工具名，不要带有例如"工具1"之类的额外说明，不要有任何额外说明，不要有任何额外说明
    4. "parameters"字段必须使用已有信息进行构造，不允许在没有相关信息时编造参数，例如不允许编造报告日期
    5. 如果步骤不使用工具，"tool"字段应为空字符串
    6. 如果没有参数，"parameters"应为空对象
    7. "execution_order"应包含所有步骤的完整标识符，如"1.a"、"1.b"等
    8. 保留所有原始信息，不要遗漏任何模块或步骤
    """

    try:
        with st.spinner(f"使用 {MULTIMODAL_MODEL} 解析执行计划步骤中..."):
            resp = client.chat.completions.create(
                model=MULTIMODAL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            )

            if resp.choices and len(resp.choices) > 0:
                json_str = resp.choices[0].message.content

                # 清理可能的格式问题
                json_str = json_str.strip()
                # 移除可能的代码块标记
                if json_str.startswith('```json'):
                    json_str = json_str[7:-3].strip()
                elif json_str.startswith('```'):
                    json_str = json_str[3:-3].strip()

                # 解析JSON
                plan_data = json.loads(json_str)

                # 转换为我们需要的步骤格式，包含依赖关系
                steps = []
                for module in plan_data.get('modules', []):
                    module_id = module.get('module_id', '')
                    module_name = module.get('module_name', f"模块 {module_id}")

                    for step in module.get('steps', []):
                        step_id = step.get('step_id', '')
                        full_step_id = f"{module_id}.{step_id}"

                        steps.append({
                            'module': module_name,
                            'module_id': module_id,
                            'step_id': step_id,
                            'full_step_id': full_step_id,
                            'name': step.get('step_name', f"步骤 {full_step_id}"),
                            'content': step.get('content', ''),
                            'uses_tool': step.get('uses_tool', False),
                            'tool': step.get('tool', ''),
                            'parameters': step.get('parameters', {}),
                            'expected_output': step.get('expected_output', ''),
                            'depends_on': step.get('depends_on', [])  # 新增：存储依赖的步骤ID
                        })

                # 根据执行顺序排序步骤
                execution_order = plan_data.get('execution_order', [])
                if execution_order and steps:
                    # 创建步骤ID到步骤的映射
                    step_map = {step['full_step_id']: step for step in steps}
                    # 按执行顺序重新排列步骤
                    ordered_steps = []
                    for step_id in execution_order:
                        if step_id in step_map:
                            ordered_steps.append(step_map[step_id])
                            del step_map[step_id]
                    # 添加剩余未在执行顺序中出现的步骤
                    ordered_steps.extend(step_map.values())
                    return ordered_steps

                return steps
            else:
                st.error("模型未返回有效响应，无法提取步骤")
                return []

    except json.JSONDecodeError as e:
        st.error(f"解析步骤JSON失败: {str(e)}")
        return []
    except Exception as e:
        st.error(f"提取步骤失败: {str(e)}")
        return []


# 辅助函数：生成下载链接
def get_download_link(text, filename, text_description):
    """生成下载链接"""
    b64 = base64.b64encode(text.encode()).decode()
    href = f'<a href="data:text/markdown;base64,{b64}" download="{filename}">{text_description}</a>'
    return href


# 改进任务进度显示，增加模块分组
def display_task_progress():
    """显示当前任务进度和流程，确保进度条实时更新"""
    task_progress = st.session_state.task_progress

    st.markdown("### 📝 分析任务流程")

    # 显示总体进度
    stages = [
        {'id': 'initial', 'name': '初始化'},
        {'id': 'document_analysis', 'name': '文档解析'},
        {'id': 'plan_generation', 'name': '生成执行计划'},
        {'id': 'plan_execution', 'name': '执行计划'},
        {'id': 'final_report', 'name': '生成最终报告'}
    ]

    # 计算总体进度百分比
    current_stage_idx = next((i for i, s in enumerate(stages) if s['id'] == task_progress['stage']), 0)
    overall_progress = (current_stage_idx / (len(stages) - 1)) if len(stages) > 1 else 0

    st.progress(overall_progress, text=f"当前阶段: {stages[current_stage_idx]['name']}")

    # 显示阶段状态 - 根据已完成的阶段列表来显示✅
    cols = st.columns(len(stages))
    for i, stage in enumerate(stages):
        with cols[i]:
            if stage['id'] in task_progress['completed_stages']:
                status = "✅"
            elif stage['id'] == task_progress['stage']:
                status = "🔄"
            else:
                status = "⏸️"
            st.markdown(f"{status} {stage['name']}")

    st.markdown("---")

    # 根据当前阶段显示详细信息
    if task_progress['stage'] == 'document_analysis' and 'modules' in task_progress:
        st.markdown("### 🔍 文档解析结果 - 识别的模块")
        modules = task_progress['modules']
        for i, module in enumerate(modules):
            st.markdown(f"{i + 1}. {module}")

        if st.button("📋 生成执行计划"):
            with st.spinner("正在生成执行计划..."):
                plan = generate_execution_plan(
                    st.session_state.image_analysis_report,
                    modules
                )
                # 确保当前阶段被标记为已完成
                if 'document_analysis' not in st.session_state.task_progress['completed_stages']:
                    st.session_state.task_progress['completed_stages'].append('document_analysis')
                st.success("执行计划生成完成")
                st.rerun()

    elif task_progress['stage'] == 'plan_generation' and st.session_state.execution_plan:
        st.markdown("### 📋 执行计划")
        with st.expander("查看详细执行计划", expanded=False):
            st.code(st.session_state.execution_plan, language="markdown")

        if st.button("▶️ 开始执行计划"):
            st.session_state.task_progress['stage'] = 'plan_execution'
            st.session_state.task_progress['current_step'] = 0
            st.session_state.task_progress['completed_steps'] = 0
            # 确保当前阶段被标记为已完成
            if 'plan_generation' not in st.session_state.task_progress['completed_stages']:
                st.session_state.task_progress['completed_stages'].append('plan_generation')
            st.rerun()

    elif task_progress['stage'] == 'plan_execution':
        st.markdown("### ▶️ 计划执行进度")
        # 添加折叠面板显示执行计划
        with st.expander("📋 查看执行计划", expanded=False):
            st.markdown(st.session_state.execution_plan)

        total_steps = task_progress['total_steps']
        completed_steps = task_progress['completed_steps']
        current_step = task_progress['current_step']

        # 实时更新的进度条
        if total_steps > 0:
            progress = completed_steps / total_steps if total_steps > 0 else 0
            progress_bar = st.progress(progress, text=f"已完成 {completed_steps}/{total_steps} 步")

            # 按模块分组显示步骤列表
            steps = task_progress['steps']
            modules = list(dict.fromkeys(step['module'] for step in steps))  # 去重且保持顺序

            # 遍历有序模块列表
            for module in modules:
                module_steps = [s for s in steps if s['module'] == module]
                with st.expander(
                        f"📦 {module} ({sum(1 for s in module_steps if steps.index(s) < completed_steps)}/{len(module_steps)})",
                        expanded=True
                ):
                    # 按步骤在原始计划中的顺序显示
                    for step in module_steps:
                        step_index = steps.index(step)  # 保持原始步骤顺序
                        # 明确区分已完成、正在执行和未开始的步骤
                        if step_index < completed_steps:
                            step_status = "✅"
                            step_class = "completed"
                        elif step_index == current_step and completed_steps < total_steps:
                            step_status = "🔄"
                            step_class = "active"
                        else:
                            step_status = "⏸️"
                            step_class = ""

                        st.markdown(f"""
                        <div class="task-step {step_class}">
                            <strong>{step_status} 步骤 {step_index + 1}: {step['name']}</strong>
                            <p>分析内容: {step['content'][:100]}{'...' if len(step['content']) > 100 else ''}</p>
                            <p>使用工具: {'是 - ' + step['tool'] if step['uses_tool'] else '否'}</p>
                        </div>
                        """, unsafe_allow_html=True)

            # 执行步骤的逻辑，每次只执行一个步骤
            if completed_steps < total_steps:
                # 检查是否需要执行下一步
                if current_step == completed_steps:
                    # 显示当前执行的步骤信息
                    current_step_data = steps[current_step] if current_step < len(steps) else None
                    if current_step_data:
                        with st.spinner(f"正在执行步骤 {current_step + 1}/{total_steps}: {current_step_data['name']}"):
                            # 执行单步并立即更新状态
                            execute_plan(st.session_state.execution_plan)
                else:
                    # 同步状态，防止不一致
                    st.session_state.task_progress['current_step'] = completed_steps
                    st.rerun()
            elif completed_steps >= total_steps:
                # 关键修复：步骤完成后立即标记阶段为已完成
                if 'plan_execution' not in st.session_state.task_progress['completed_stages']:
                    st.session_state.task_progress['completed_stages'].append('plan_execution')
                    # 强制刷新以更新UI状态
                    st.rerun()
                st.success("所有计划步骤执行完成！")
                if st.button("📊 生成最终综合报告"):
                    with st.spinner("正在生成最终综合报告..."):
                        final_report = generate_final_synthesis_report()
                        # 确保当前阶段被标记为已完成
                        if 'plan_execution' not in st.session_state.task_progress['completed_stages']:
                            st.session_state.task_progress['completed_stages'].append('plan_execution')
                        st.success("最终综合报告生成完成")
                        st.rerun()

    elif task_progress['stage'] == 'final_report' and st.session_state.final_synthesis_report:
        st.markdown("### 📊 最终综合报告")
        with st.expander("📋 查看执行计划", expanded=False):
            st.markdown(st.session_state.execution_plan)
        with st.expander("查看最终综合报告", expanded=True):
            st.markdown(st.session_state.final_synthesis_report)

        st.success("🎉 所有分析任务已完成！")


def main():
    """主应用程序"""
    import datetime
    import base64
    import os
    from PIL import Image
    import streamlit as st

    # 初始化会话状态
    initialize_session_state()

    # 自定义CSS - 调整侧边栏宽度
    st.markdown("""
    <style>
    /* 调整侧边栏宽度为260px，避免标题挤压 */
    section[data-testid="stSidebar"] {
        width: 280px !important;
        min-width: 280px !important;
        max-width: 280px !important;
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

    /* 其他CSS样式保持不变... */
    section[data-testid="stSidebar"] > div:first-child > button[kind="header"],
    section[data-testid="stSidebar"] > div:first-child > div > button[kind="header"],
    section[data-testid="stSidebar"] .css-1lcbmhc > button[kind="header"],
    section[data-testid="stSidebar"] .css-1y4p8pa > button[kind="header"] {
        display: none !important;
        visibility: hidden !important;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 0.5rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }

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

    .stApp > div {
        overflow-x: auto !important;
    }

    .element-container {
        margin-right: 8px !important;
    }

    .sidebar .sidebar-content {
        padding: 0.5rem 0.3rem !important;
    }

    section[data-testid="stSidebar"] .element-container {
        margin-bottom: 0.5rem !important;
    }

    section[data-testid="stSidebar"] hr {
        margin: 0.8rem 0 !important;
    }

    section[data-testid="stSidebar"] h1 {
        font-size: 1.2rem !important;
        line-height: 1.3 !important;
        margin-bottom: 1rem !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
    }

    section[data-testid="stSidebar"] .stSelectbox > div > div {
        font-size: 1.1rem !important;
        font-weight: 500 !important;
    }

    section[data-testid="stSidebar"] .stSelectbox > div > div {
        min-width: 220px !important;
        width: 100% !important;
    }

    .main {
        padding-right: 8px !important;
    }

    .stApp {
        margin-right: 0 !important;
        padding-right: 8px !important;
    }

    .streamlit-expanderContent {
        padding-right: 8px !important;
        margin-right: 8px !important;
    }

    .main .block-container {
        overflow-x: visible !important;
    }

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

    .main .block-container {
        width: calc(100vw - 276px) !important;
        max-width: calc(100vw - 276px) !important;
    }

    div[data-testid="column"]:last-child {
        background-color: #f8f9fa !important;
        border-radius: 8px !important;
        padding: 12px !important;
        margin-left: 8px !important;
        border: 1px solid #e9ecef !important;
    }

    div[data-testid="column"]:last-child .streamlit-expanderHeader {
        background-color: #ffffff !important;
        border-radius: 6px !important;
        border: 1px solid #dee2e6 !important;
        font-weight: 500 !important;
    }

    div[data-testid="column"]:last-child .stMarkdown {
        font-size: 0.9rem !important;
        line-height: 1.5 !important;
    }

    div[data-testid="column"]:last-child h1 {
        font-size: 1.3rem !important;
        color: #495057 !important;
        margin-bottom: 1rem !important;
    }
    </style>

    <script>
    // JavaScript来强制隐藏侧边栏按钮
    function hideSidebarButtons() {
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

    document.addEventListener('DOMContentLoaded', hideSidebarButtons);
    setInterval(hideSidebarButtons, 1000);

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

        const mainContainer = document.querySelector('.main .block-container');
        if (mainContainer) {
            mainContainer.style.width = 'calc(100vw - 276px)';
            mainContainer.style.maxWidth = 'calc(100vw - 276px)';
        }
    }

    document.addEventListener('DOMContentLoaded', forceOptimalPadding);
    setInterval(forceOptimalPadding, 500);
    </script>
    """, unsafe_allow_html=True)

    # 渲染页面头部
    render_header()

    # 页面导航 - 保留logo和标题
    current_dir = Path(__file__).parent
    logo_path = current_dir / "logo.gif"
    with open(logo_path, "rb") as f:
        contents = f.read()
    data_url = base64.b64encode(contents).decode("utf-8")
    st.sidebar.markdown(
        f'<img src="data:image/gif;base64,{data_url}" width="150" style="display: block; margin: 0 auto;">',
        unsafe_allow_html=True,
    )
    st.sidebar.title("💡 多模态文档洞察分析")
    st.sidebar.markdown("---")

    # 初始化历史记录会话状态
    if 'analysis_history' not in st.session_state:
        st.session_state.analysis_history = []
    if 'current_analysis' not in st.session_state:
        st.session_state.current_analysis = None
    if 'analysis_counter' not in st.session_state:
        st.session_state.analysis_counter = 0

    # 生成唯一分析ID
    def generate_analysis_id():
        st.session_state.analysis_counter += 1
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"analysis_{timestamp}_{st.session_state.analysis_counter}"

    # 上方：开启新分析
    st.sidebar.subheader("📝 分析管理")
    if st.sidebar.button("🚀 开启新分析", use_container_width=True):
        # 生成新分析ID
        analysis_id = generate_analysis_id()

        # 创建新分析记录
        new_analysis = {
            "id": analysis_id,
            "title": f"分析 #{st.session_state.analysis_counter}",
            "status": "进行中",
            "start_time": datetime.datetime.now(),
            "end_time": None,
            "type": None,  # 图片/PDF/网页
            "file_name": None,
            "url": None,
            "results": None
        }

        # 保存当前分析并添加到历史记录
        st.session_state.current_analysis = new_analysis
        st.session_state.analysis_history.append(new_analysis)

        # 重置分析相关状态
        st.session_state.image_analysis_completed = False
        st.session_state.pdf_analysis_completed = False
        st.session_state.web_analysis_completed = False
        st.session_state.image_analysis_report = ""
        st.session_state.extracted_tickers = []
        st.session_state.extracted_companies = []
        st.session_state.pdf_pages = []
        st.session_state.current_pdf_page = 0
        st.session_state.pdf_analysis_reports = []
        st.session_state.web_screenshot = None
        st.session_state.final_synthesis_report = ""

        # 重置任务进度
        st.session_state.task_progress = {
            'stage': 'initial',
            'completed_stages': ['initial'],
            'steps': [],
            'current_step': 0,
            'completed_steps': 0,
            'total_steps': 0,
            'execution_reports': []
        }

        st.session_state.execution_plan = ""
        st.rerun()

    # 下方：历史分析记录
    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 历史分析记录")

    # 显示空状态提示
    if not st.session_state.analysis_history:
        st.sidebar.info("暂无历史分析记录，点击上方按钮开始新分析")
    else:
        # 按时间倒序显示历史记录
        for analysis in reversed(st.session_state.analysis_history):
            with st.sidebar.expander(
                    f"{analysis['title']} "
                    f"[{analysis['status']}] "
                    f"{analysis['start_time'].strftime('%m-%d %H:%M')}",
                    expanded=False
            ):
                # 显示分析基本信息
                st.markdown(f"**开始时间:** {analysis['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")

                if analysis['end_time']:
                    st.markdown(f"**结束时间:** {analysis['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")

                if analysis['type'] == 'file':
                    st.markdown(f"**分析文件:** {analysis['file_name']}")
                elif analysis['type'] == 'web':
                    st.markdown(f"**分析网页:** {analysis['url']}")

                # 操作按钮
                col_view, col_rename, col_delete = st.columns(3)

                with col_view:
                    if st.button("查看", key=f"view_{analysis['id']}", use_container_width=True):
                        # 加载选中的历史分析
                        st.session_state.current_analysis = analysis
                        st.rerun()

                with col_rename:
                    if st.button("重命名", key=f"rename_{analysis['id']}", use_container_width=True):
                        new_title = st.text_input(
                            "输入新标题",
                            value=analysis['title'],
                            key=f"rename_input_{analysis['id']}"
                        )
                        if new_title and new_title != analysis['title']:
                            analysis['title'] = new_title
                            st.success("标题已更新")
                            st.rerun()

                with col_delete:
                    if st.button("删除", key=f"delete_{analysis['id']}", use_container_width=True):
                        # 从历史记录中移除
                        st.session_state.analysis_history = [
                            a for a in st.session_state.analysis_history
                            if a['id'] != analysis['id']
                        ]
                        # 如果删除的是当前分析，重置当前分析
                        if (st.session_state.current_analysis and
                                st.session_state.current_analysis['id'] == analysis['id']):
                            st.session_state.current_analysis = None
                        st.success("记录已删除")
                        st.rerun()

    # 检查是否有当前活跃的分析
    if not st.session_state.current_analysis:
        st.info("请从左侧边栏点击「开启新分析」按钮开始一个新的分析任务，或选择历史分析记录查看详情。")
        return

    # 主内容区域 - 固定分为两列，右侧始终显示使用指南
    col1, col2 = st.columns([2, 1])  # 2:1比例，使用指南占三分之一

    with col1:
        # 显示当前分析标题
        st.header(f"当前分析: {st.session_state.current_analysis['title']}")

        # 多模态文档分析区域（支持图片、PDF和网页截图）
        st.subheader("🖼️ 文档分析 (多模态)")
        with st.container():
            # 网页分析部分
            st.subheader("🌐 网页分析")
            url_input = st.text_input(
                "输入网页URL",
                placeholder="例如: https://finance.yahoo.com/quote/AAPL",
                help="输入包含股票信息的网页URL，系统将自动截取完整网页并分析"
            )

            col_url1, col_url2 = st.columns(2)
            with col_url1:
                if st.button("📸 截取网页截图", disabled=not url_input):
                    # 更新当前分析信息
                    st.session_state.current_analysis['type'] = 'web'
                    st.session_state.current_analysis['url'] = url_input
                    st.session_state.current_analysis['status'] = "处理中"

                    # 重置相关状态
                    st.session_state.web_screenshot = None
                    st.session_state.web_analysis_completed = False
                    st.session_state.image_analysis_completed = False
                    st.session_state.pdf_analysis_completed = False
                    st.session_state.image_analysis_report = ""
                    st.session_state.extracted_tickers = []
                    st.session_state.extracted_companies = []
                    # 重置任务进度
                    st.session_state.task_progress = {
                        'stage': 'initial',
                        'completed_stages': ['initial'],  # 保留初始化阶段
                        'steps': [],
                        'current_step': 0,
                        'completed_steps': 0,
                        'total_steps': 0,
                        'execution_reports': []
                    }

                    # 截取网页截图
                    screenshot = capture_screenshot(url_input)
                    if screenshot:
                        st.session_state.web_screenshot = screenshot

                        # 自动分析网页截图
                        extracted_info = analyze_document_with_multimodal(
                            document=screenshot,
                            doc_type="web"
                        )

                        # 更新分析状态
                        if st.session_state.web_analysis_completed:
                            st.session_state.current_analysis['status'] = "已完成"
                            st.session_state.current_analysis['end_time'] = datetime.datetime.now()
                            st.session_state.current_analysis['results'] = {
                                'type': 'web',
                                'has_report': bool(st.session_state.image_analysis_report)
                            }

            with col_url2:
                if st.button("🔄 重新分析网页", disabled=not st.session_state.web_screenshot):
                    # 更新当前分析状态
                    st.session_state.current_analysis['status'] = "处理中"

                    # 重置任务进度
                    st.session_state.task_progress = {
                        'stage': 'initial',
                        'completed_stages': ['initial'],  # 保留初始化阶段
                        'steps': [],
                        'current_step': 0,
                        'completed_steps': 0,
                        'total_steps': 0,
                        'execution_reports': []
                    }

                    # 重新分析已有的网页截图
                    extracted_info = analyze_document_with_multimodal(
                        document=st.session_state.web_screenshot,
                        doc_type="web"
                    )

                    # 更新分析状态
                    if st.session_state.web_analysis_completed:
                        st.session_state.current_analysis['status'] = "已完成"
                        st.session_state.current_analysis['end_time'] = datetime.datetime.now()

            # 显示已有的网页截图
            if st.session_state.web_screenshot and not st.session_state.web_analysis_completed:
                st.image(
                    st.session_state.web_screenshot,
                    caption="网页截图预览",
                    use_container_width=True
                )
                if st.button("📊 分析网页截图", key="analyze_web_screenshot"):
                    # 更新当前分析状态
                    st.session_state.current_analysis['status'] = "处理中"

                    # 重置任务进度
                    st.session_state.task_progress = {
                        'stage': 'initial',
                        'completed_stages': ['initial'],  # 保留初始化阶段
                        'steps': [],
                        'current_step': 0,
                        'completed_steps': 0,
                        'total_steps': 0,
                        'execution_reports': []
                    }

                    extracted_info = analyze_document_with_multimodal(
                        document=st.session_state.web_screenshot,
                        doc_type="web"
                    )

                    # 更新分析状态
                    if st.session_state.web_analysis_completed:
                        st.session_state.current_analysis['status'] = "已完成"
                        st.session_state.current_analysis['end_time'] = datetime.datetime.now()

            # 文件上传部分
            st.subheader("📂 文件上传 (图片/PDF)")
            uploaded_file = st.file_uploader(
                "上传包含股票信息的文档（图片或PDF格式）",
                type=["jpg", "jpeg", "png", "pdf"]
            )

            # 处理上传的文档
            if uploaded_file is not None:
                # 更新当前分析信息
                st.session_state.current_analysis['type'] = 'file'
                st.session_state.current_analysis['file_name'] = uploaded_file.name
                st.session_state.current_analysis['status'] = "处理中"

                # 检查文件类型
                file_extension = uploaded_file.name.split('.')[-1].lower()

                # 重置相关状态（如果上传了新文件）
                if 'last_uploaded_file' not in st.session_state or st.session_state.last_uploaded_file != uploaded_file.name:
                    st.session_state.last_uploaded_file = uploaded_file.name
                    st.session_state.image_analysis_completed = False
                    st.session_state.pdf_analysis_completed = False
                    st.session_state.web_analysis_completed = False
                    st.session_state.image_analysis_report = ""
                    st.session_state.extracted_tickers = []
                    st.session_state.extracted_companies = []
                    st.session_state.pdf_pages = []
                    st.session_state.current_pdf_page = 0
                    st.session_state.pdf_analysis_reports = []
                    st.session_state.web_screenshot = None
                    st.session_state.tool_executor = None
                    # 重置任务进度
                    st.session_state.task_progress = {
                        'stage': 'initial',
                        'completed_stages': ['initial'],  # 保留初始化阶段
                        'steps': [],
                        'current_step': 0,
                        'completed_steps': 0,
                        'total_steps': 0,
                        'execution_reports': []
                    }

                # 处理PDF文件
                if file_extension == 'pdf' and not st.session_state.pdf_analysis_completed:
                    # 转换PDF为图片
                    if not st.session_state.pdf_pages:
                        pdf_pages = convert_pdf_to_images(uploaded_file)
                        st.session_state.pdf_pages = pdf_pages

                    # 如果转换成功，进行分析
                    if st.session_state.pdf_pages and not st.session_state.pdf_analysis_completed:
                        extracted_info = analyze_document_with_multimodal(
                            document=st.session_state.pdf_pages,
                            doc_type="pdf"
                        )

                        # 更新分析状态
                        if st.session_state.pdf_analysis_completed:
                            st.session_state.current_analysis['status'] = "已完成"
                            st.session_state.current_analysis['end_time'] = datetime.datetime.now()
                            st.session_state.current_analysis['results'] = {
                                'type': 'pdf',
                                'page_count': len(st.session_state.pdf_pages),
                                'has_report': bool(st.session_state.image_analysis_report)
                            }

                # 处理图片文件
                elif file_extension in ['jpg', 'jpeg', 'png'] and not st.session_state.image_analysis_completed:
                    try:
                        image = Image.open(uploaded_file)
                        # 使用指定的多模态模型分析图片
                        extracted_info = analyze_document_with_multimodal(
                            document=image,
                            doc_type="image"
                        )

                        # 更新分析状态
                        if st.session_state.image_analysis_completed:
                            st.session_state.current_analysis['status'] = "已完成"
                            st.session_state.current_analysis['end_time'] = datetime.datetime.now()
                            st.session_state.current_analysis['results'] = {
                                'type': 'image',
                                'has_report': bool(st.session_state.image_analysis_report)
                            }
                    except Exception as e:
                        st.error(f"图片处理错误: {str(e)}")
                        logger.error(f"图片处理错误: {str(e)}")
                        # 更新分析状态为失败
                        st.session_state.current_analysis['status'] = "失败"

            # 显示文档分析结果（如果已完成）
            if st.session_state.image_analysis_completed or st.session_state.pdf_analysis_completed or st.session_state.web_analysis_completed:
                # 显示PDF预览和导航（如果是PDF文件）
                if st.session_state.pdf_analysis_completed and st.session_state.pdf_pages:
                    total_pages = len(st.session_state.pdf_pages)

                    st.markdown("### PDF预览与导航")

                    # 页面导航控制
                    col_prev, col_page, col_next = st.columns([1, 2, 1])

                    with col_prev:
                        if st.button("上一页", disabled=st.session_state.current_pdf_page == 0):
                            st.session_state.current_pdf_page -= 1

                    with col_page:
                        st.markdown(f"**第 {st.session_state.current_pdf_page + 1}/{total_pages} 页**")

                    with col_next:
                        if st.button("下一页", disabled=st.session_state.current_pdf_page == total_pages - 1):
                            st.session_state.current_pdf_page += 1

                    # 显示当前页
                    current_page = st.session_state.pdf_pages[st.session_state.current_pdf_page]
                    st.image(
                        current_page['image'],
                        caption=f"PDF第 {current_page['page_number']} 页",
                        use_container_width=True
                    )

                # 显示网页截图（如果是网页分析）
                if st.session_state.web_analysis_completed and st.session_state.web_screenshot:
                    st.markdown("### 网页截图")
                    with st.expander("查看完整网页截图", expanded=False):
                        st.image(
                            st.session_state.web_screenshot,
                            caption="分析的网页截图",
                            use_container_width=True
                        )

                # 显示文档分析报告
                if st.session_state.image_analysis_report:
                    st.markdown("### 文档分析报告")
                    with st.expander("查看完整文档分析报告", expanded=False):
                        st.markdown(st.session_state.image_analysis_report)

            # 显示使用的模型信息
            st.info(f"使用的多模态模型: {MULTIMODAL_MODEL}")

        st.markdown("---")

        # 显示任务流程进度
        display_task_progress()

    # 右侧始终渲染使用指南，不再受按钮控制
    with col2:
        st.markdown("### ℹ️ 使用指南")

        # 快速开始指南
        with st.expander("🎯 快速开始", expanded=True):
            st.markdown("""
            ### 📋 操作步骤
            1. 上传文档（图片/PDF）或输入网页URL
            2. 系统将自动分析文档内容
            3. 查看生成的执行计划
            4. 执行分析计划，系统将自动调用必要的工具
            5. 查看最终综合报告
            """)

        # 分析流程说明
        with st.expander("🔄 分析流程详解", expanded=False):
            st.markdown("""
            ### 🔍 四阶段分析流程
            1. **文档解析**：系统分析上传的文档内容，提取关键信息
            2. **生成执行计划**：根据文档内容创建详细的分析步骤和工具调用计划
            3. **执行计划**：按步骤执行分析，自动调用股票分析等工具
            4. **生成最终报告**：整合所有分析结果，生成专业的综合报告
            """)

        # 执行计划分析报告
        with st.expander("🛠️ 执行计划分析报告", expanded=False):
            execution_reports = st.session_state.task_progress.get('execution_reports', [])

            if not execution_reports:
                st.info("尚未执行任何分析步骤，完成执行计划后将显示各步骤报告")
            else:
                st.markdown(f"共 {len(execution_reports)} 个步骤，点击展开查看详情：")
                for report in execution_reports:
                    status = "✅" if report['status'] == 'completed' else "❌"
                    with st.expander(f"{status} 步骤 {report['step']} [{report['module']}]: {report['name']}",
                                     expanded=False):
                        st.markdown(report['report'])

        # 报告下载
        with st.expander("❓ 报告下载", expanded=False):
            # 检查是否有可下载的报告
            has_reports = (
                    st.session_state.image_analysis_report or
                    st.session_state.execution_plan or
                    st.session_state.execution_plan or
                    st.session_state.task_progress.get('execution_reports') or
                    st.session_state.final_synthesis_report
            )

            if not has_reports:
                st.info("尚未生成任何报告，完成分析流程后可下载报告")
            else:
                # 生成时间戳用于文件名
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

                # 文档分析报告下载
                if st.session_state.image_analysis_report:
                    doc_report_text = f"# 文档分析报告\n\n{st.session_state.image_analysis_report}"
                    st.markdown(
                        get_download_link(
                            doc_report_text,
                            f"document_analysis_report_{timestamp}.md",
                            "📄 下载文档分析报告"
                        ),
                        unsafe_allow_html=True
                    )

                # 执行计划下载
                if st.session_state.execution_plan:
                    plan_text = f"# 执行计划\n\n{st.session_state.execution_plan}"
                    st.markdown(
                        get_download_link(
                            plan_text,
                            f"execution_plan_{timestamp}.md",
                            "📋 下载执行计划"
                        ),
                        unsafe_allow_html=True
                    )

                # 执行步骤报告下载
                execution_reports = st.session_state.task_progress.get('execution_reports', [])
                if execution_reports:
                    steps_report = "# 执行步骤报告\n\n"
                    for report in execution_reports:
                        steps_report += f"## 步骤 {report['step']} [{report['module']}]: {report['name']}\n\n{report['report']}\n\n"

                    st.markdown(
                        get_download_link(
                            steps_report,
                            f"execution_steps_report_{timestamp}.md",
                            "📝 下载执行步骤报告"
                        ),
                        unsafe_allow_html=True
                    )

                # 最终综合报告下载
                if st.session_state.final_synthesis_report:
                    final_report_text = f"# 最终综合报告\n\n{st.session_state.final_synthesis_report}"
                    st.markdown(
                        get_download_link(
                            final_report_text,
                            f"final_synthesis_report_{timestamp}.md",
                            "📊 下载最终综合报告"
                        ),
                        unsafe_allow_html=True
                    )

                # 完整报告包下载
                full_report = "# 完整分析报告包\n\n"
                full_report += "## 1. 文档分析报告\n\n"
                full_report += f"{st.session_state.image_analysis_report or '无文档分析报告'}\n\n"
                full_report += "## 2. 执行计划\n\n"
                full_report += f"{st.session_state.execution_plan or '无执行计划'}\n\n"
                full_report += "## 3. 执行步骤报告\n\n"
                for report in execution_reports:
                    full_report += f"### 步骤 {report['step']} [{report['module']}]: {report['name']}\n\n{report['report']}\n\n"
                full_report += "## 4. 最终综合报告\n\n"
                full_report += f"{st.session_state.final_synthesis_report or '无最终综合报告'}\n\n"

                st.markdown(
                    get_download_link(
                        full_report,
                        f"full_analysis_report_{timestamp}.md",
                        "📦 下载完整报告包（包含所有报告）"
                    ),
                    unsafe_allow_html=True
                )

        # 风险提示
        st.warning("""
        ⚠️ **警告**

        - 本系统提供的分析结果仅供参考，不构成任何投资建议
        - AI分析存在局限性，据此操作造成的任何损失，本系统不承担责任
        """)

    # 显示系统状态
    if st.session_state.last_analysis_time:
        st.info(f"🕒 上次分析时间: {st.session_state.last_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()