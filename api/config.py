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
CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', '120'))

