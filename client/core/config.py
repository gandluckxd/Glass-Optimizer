"""
Configuration settings for the 2D optimization application
"""

# API Configuration
API_URL = "http://localhost:8000"

# Optimization Settings
DEFAULT_OPTIMIZATION_PARAMS = {
    'target_waste_percent': 5.0,  # ИЗМЕНЕНО: Увеличено с 3.0% до 5.0% для реальных данных
    'remainder_waste_percent': 20.0,  # ДОБАВЛЕНО: Процент отходов для деловых остатков
    'allow_rotation': True,
    'min_cut_size': 10,
    'blade_width': 10,
    'min_remnant_width': 180,  # Минимальная ширина делового остатка согласно требованиям
    'min_remnant_height': 100, # Минимальная высота делового остатка согласно требованиям
    'use_remainders': True,
    'algorithm': 'AUTO',
    # НОВЫЕ ПАРАМЕТРЫ ДЛЯ МИНИМИЗАЦИИ ДЕЛОВЫХ ОСТАТКОВ
    'aggressive_remnant_reduction': True,  # Агрессивное уменьшение деловых остатков
    'min_remnant_area': 5000.0,  # Минимальная площадь делового остатка (мм²)
    'remnant_optimization_level': 2,  # Уровень оптимизации остатков (1-3)
    'allow_small_details_in_remnants': True,  # Разрешить размещение мелких деталей в остатках
    'max_remnant_count_per_sheet': 3  # Максимальное количество деловых остатков на лист
}

# Application Settings
DEBUG = True
ENABLE_LOGGING = True
LOG_LEVEL = 'DEBUG' 