import os
import json
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Annotated

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    if save_path:
        data.to_csv(save_path)
        logger.info(f"{tag} saved to {save_path}")


def get_current_date():
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(decorator):
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date):

    if not isinstance(date, datetime):
        date = datetime.strptime(date, "%Y-%m-%d")

    if date.weekday() >= 5:
        days_to_add = 7 - date.weekday()
        next_weekday = date + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date

def convert_symbol(symbol: str) -> str:
    """转换股票代码格式，确保是6位数字格式

    Args:
        symbol: 股票代码，可能带有市场标识

    Returns:
        str: 6位数字格式的股票代码
    """
    # 移除可能的市场后缀
    symbol = symbol.split('.')[0]
    # 移除可能的市场前缀
    if symbol.startswith(('SH', 'SZ', 'BJ')):
        symbol = symbol[2:]
    # 确保是6位数字
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError(f"Invalid A-share stock symbol: {symbol}")
    return symbol


def add_market_prefix(symbol: str) -> str:
    """添加A股市场标识前缀

    Args:
        symbol: 6位股票代码

    Returns:
        str: 带市场标识的股票代码，如：
            - SH600519 (上海主板)
            - SZ000002 (深圳主板)
            - SZ300059 (创业板)
            - SH688001 (科创板)
    """
    symbol = convert_symbol(symbol)

    # 上海证券交易所
    if symbol.startswith('6'):
        return f"SH{symbol}"
    # 深圳证券交易所
    elif symbol.startswith('000') or symbol.startswith('001'):  # 深圳主板
        return f"SZ{symbol}"
    elif symbol.startswith('002') or symbol.startswith('003'):  # 中小板
        return f"SZ{symbol}"
    elif symbol.startswith('300') or symbol.startswith('301'):  # 创业板
        return f"SZ{symbol}"
    elif symbol.startswith('688') or symbol.startswith('689'):  # 科创板
        return f"SH{symbol}"
    else:
        raise ValueError(f"Unknown market for stock symbol: {symbol}")
