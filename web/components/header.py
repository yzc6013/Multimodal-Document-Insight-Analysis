"""
页面头部组件
"""

import streamlit as st

def render_header():
    """渲染页面头部"""
    
    # 主标题
    st.markdown("""
    <div class="main-header">
        <h1>多模态文档洞察分析平台</h1>
        <h5>多智能体协同的多模态文档深度洞察系统</h5>
    </div>
    """, unsafe_allow_html=True)
    
    # 功能特性展示
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="metric-card">
            <h4>🤝 多智能体协作</h4>
            <p>结合多种智能体工具深度解析</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="metric-card">
            <h4>🔍 多模态全解析</h4>
            <p>支持多种格式、模态文档解析</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="metric-card">
            <h4>📊 深度解析框架</h4>
            <p>文档内容因果溯源深度解析</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="metric-card">
            <h4>🧩 全域数据融合</h4>
            <p>结合MCP本地数据与联网数据</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 分隔线
    st.markdown("---")
