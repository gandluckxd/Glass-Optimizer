#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Клиентская часть приложения оптимизации 2D раскроя

Этот пакет содержит:
- core: Основная логика оптимизации и работы с API
- gui: Графический интерфейс пользователя  
- Основной модуль запуска приложения
"""

__version__ = "1.0.0"
__author__ = "2D Optimization Team"

# Экспорт основных компонентов для удобного импорта
from .core.api_client import check_api_connection
from .gui.main_window import OptimizerWindow

__all__ = [
    'check_api_connection',
    'OptimizerWindow'
] 