"""
Основная логика приложения оптимизации 2D раскроя
"""

from .optimizer_core import optimize, OptimizationResult
from .data_manager import DataManager
from .api_client import *

__all__ = ["optimize", "OptimizationResult", "DataManager"] 