"""
API клиент для взаимодействия с сервером оптимизации
"""

import requests
import json
from .config import API_URL

def check_api_connection():
    """Проверка доступности API"""
    try:
        # Используем существующий endpoint /tables для проверки
        response = requests.get(f"{API_URL}/tables", timeout=120)
        return response.status_code == 200
    except Exception as e:
        print(f"API connection error: {e}")
        return False

def api_request(endpoint, data=None, method='GET'):
    """Универсальная функция для API запросов"""
    url = f"{API_URL}/{endpoint.lstrip('/')}"
    
    try:
        if method == 'POST':
            response = requests.post(
                url, 
                json=data,  # Используем json= вместо data=
                headers={'Content-Type': 'application/json'}, 
                timeout=120
            )
        else:
            response = requests.get(url, timeout=120)
        
        response.raise_for_status()
        
        try:
            result = response.json()
            # Отладочная информация о ответе API
            print(f"🔧 DEBUG API CLIENT: Response type: {type(result)}")
            if isinstance(result, dict):
                print(f"🔧 DEBUG API CLIENT: Response keys: {list(result.keys())}")
                for key, value in result.items():
                    if isinstance(value, list):
                        print(f"🔧 DEBUG API CLIENT: '{key}' contains {len(value)} items")
                    else:
                        print(f"🔧 DEBUG API CLIENT: '{key}': {type(value)}")
            elif isinstance(result, list):
                print(f"🔧 DEBUG API CLIENT: Response is list with {len(result)} items")
            return result
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return None
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None

def get_tables():
    """Получение списка таблиц"""
    return api_request('tables', method='GET')

def get_details_raw(grorderid):
    """Получение сырых данных деталей по номеру заказа"""
    data = {"grorderid": grorderid}
    return api_request('details-raw', data, 'POST')

def get_warehouse_main_material(goodsid):
    """Получение основных материалов склада"""
    data = {"goodsid": goodsid}
    return api_request('warehouse-main-material', data, 'POST')

def get_warehouse_remainders(goodsid):
    """Получение остатков склада"""
    data = {"goodsid": goodsid}
    return api_request('warehouse-remainders', data, 'POST')

def upload_optimization_data(grorderid: int, optimization_data: list, adjust_materials: bool = False):
    """
    Загрузка данных оптимизации в Altawin
    
    Args:
        grorderid: ID сменного задания
        optimization_data: Список данных оптимизации для каждого листа
        adjust_materials: Флаг корректировки списания материалов
    
    Returns:
        dict: Результат загрузки
    """
    try:
        print(f"🔄 API: Отправка данных оптимизации для grorderid={grorderid}")
        print(f"📊 API: Количество листов: {len(optimization_data)}")
        print(f"🔧 API: Корректировка материалов: {'ВКЛЮЧЕНА' if adjust_materials else 'ОТКЛЮЧЕНА'}")
        
        url = f"{API_URL}/upload-optimization"
        
        payload = {
            "grorderid": grorderid,
            "sheets": optimization_data,
            "adjust_materials": adjust_materials
        }
        
        # Логируем информацию о листах
        print(f"📋 API: Информация о листах:")
        for i, sheet in enumerate(optimization_data):
            is_remainder = sheet.get('is_remainder', 0)
            goodsid = sheet.get('goodsid')
            print(f"📋 API: Лист {i+1}: goodsid={goodsid}, is_remainder={is_remainder}")
        
        # Логируем первый лист для отладки (без XML)
        if optimization_data:
            sample_sheet = optimization_data[0].copy()
            if 'xml_data' in sample_sheet:
                sample_sheet['xml_data'] = f"<XML data, {len(sample_sheet['xml_data'])} chars>"
            print(f"📋 API: Пример данных листа: {sample_sheet}")
        
        response = requests.post(url, json=payload, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API: Данные оптимизации успешно загружены")
            return result
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                error_detail = response.json().get('detail', 'Неизвестная ошибка')
                error_msg = f"{error_msg}: {error_detail}"
            except:
                pass
            
            print(f"❌ API: Ошибка загрузки оптимизации: {error_msg}")
            return {"success": False, "message": error_msg}
            
    except requests.exceptions.Timeout:
        error_msg = "Таймаут запроса к API серверу"
        print(f"❌ API: {error_msg}")
        return {"success": False, "message": error_msg}
    except requests.exceptions.ConnectionError:
        error_msg = "Не удается подключиться к API серверу"
        print(f"❌ API: {error_msg}")
        return {"success": False, "message": error_msg}
    except Exception as e:
        error_msg = f"Неожиданная ошибка: {str(e)}"
        print(f"❌ API: {error_msg}")
        return {"success": False, "message": error_msg} 