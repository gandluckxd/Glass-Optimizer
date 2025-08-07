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
    'algorithm': 'AUTO'
}

# Application Settings
DEBUG = True
ENABLE_LOGGING = True
LOG_LEVEL = 'DEBUG' 