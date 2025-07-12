"""
GUI компоненты для приложения оптимизации 2D раскроя
"""

# Импорт config не вызывает циркулярных зависимостей
from .config import *

__version__ = "2.0.0"

# OptimizerWindow импортируется при необходимости,
# чтобы избежать циркулярных зависимостей
def get_main_window():
    """Получить главное окно (ленивая загрузка)"""
    from .main_window import OptimizerWindow
    return OptimizerWindow

__all__ = ["get_main_window"] 