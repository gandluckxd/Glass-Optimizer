"""
Configuration module for API server
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '10.8.0.3'),
    'port': int(os.getenv('DB_PORT', '3050')),
    'database': os.getenv('DB_NAME', 'D:/altAwinDB/ppk.gdb'),
    'user': os.getenv('DB_USER', 'sysdba'),
    'password': os.getenv('DB_PASSWORD', 'masterkey')
}

# Debug configuration
DEBUG_ORDER_ID = int(os.getenv('DEBUG_ORDER_ID', '28434'))

# Connection pool settings
MAX_POOL_SIZE = int(os.getenv('MAX_POOL_SIZE', '5'))
CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', '300'))  # Увеличено до 5 минут

# API timeout settings
API_TIMEOUT = int(os.getenv('API_TIMEOUT', '600'))  # 10 минут для API операций
DB_OPERATION_TIMEOUT = int(os.getenv('DB_OPERATION_TIMEOUT', '300'))  # 5 минут для операций БД

# Debug settings
ENABLE_DETAILED_LOGGING = os.getenv('ENABLE_DETAILED_LOGGING', 'true').lower() == 'true'
LOG_DB_OPERATIONS = os.getenv('LOG_DB_OPERATIONS', 'true').lower() == 'true'

