from fastapi import FastAPI
from dotenv import load_dotenv
import uvicorn
from modules.routes import router
from pydantic import BaseModel
from typing import List, Optional
from fastapi import HTTPException
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from modules.config import API_TIMEOUT, ENABLE_DETAILED_LOGGING

# Загрузка переменных окружения
load_dotenv()

app = FastAPI(title="Firebird Database API")
app.include_router(router)

# Создаем пул потоков для выполнения блокирующих операций
executor = ThreadPoolExecutor(max_workers=5)

class OptimizationSheet(BaseModel):
    """Модель данных листа оптимизации"""
    num_glass: int
    goodsid: int
    width: int
    height: int
    trash_area: int
    percent_full: float
    percent_waste: float
    piece_count: int
    sum_area: int
    qty: int
    amfactor: float  # amfactor как отдельный параметр
    is_remainder: int
    free_rectangles: list  # Данные о полученных деловых остатках
    xml_data: str

class OptimizationUploadRequest(BaseModel):
    """Модель запроса загрузки оптимизации"""
    grorderid: int
    sheets: List[OptimizationSheet]
    adjust_materials: bool = False

@app.post("/upload-optimization")
async def upload_optimization(request: OptimizationUploadRequest):
    """
    Загрузка данных оптимизации в базу данных Altawin
    
    Этапы:
    1. Удаление существующих данных для grorderid
    2. Вставка новых записей в таблицу OPTDATA
    """
    start_time = time.time()
    
    try:
        print(f"🔄 API: Начало загрузки оптимизации для grorderid={request.grorderid}")
        print(f"📊 API: Количество листов: {len(request.sheets)}")
        print(f"🔧 API: Корректировка материалов: {request.adjust_materials}")
        
        # Детальная информация о листах
        if ENABLE_DETAILED_LOGGING:
            print(f"📋 API: Детализация листов:")
            for i, sheet in enumerate(request.sheets):
                print(f"   Лист {i+1}: goodsid={sheet.goodsid}, размеры={sheet.width}x{sheet.height}, "
                      f"qty={sheet.qty}, amfactor={sheet.amfactor}, is_remainder={sheet.is_remainder}")
                if sheet.free_rectangles:
                    print(f"     Получено деловых остатков: {len(sheet.free_rectangles)}")
        
        from utils.db_functions import upload_optimization_to_db
        
        loop = asyncio.get_running_loop()
        
        print(f"⏱️ API: Запуск операции в отдельном потоке с таймаутом {API_TIMEOUT} секунд...")
        
        # Запускаем блокирующую функцию в отдельном потоке
        future = loop.run_in_executor(
            executor, 
            upload_optimization_to_db, 
            request.grorderid, 
            [sheet.dict() for sheet in request.sheets], # Преобразуем модели в словари
            request.adjust_materials
        )
        
        # Ждем результат с увеличенным таймаутом
        result = await asyncio.wait_for(future, timeout=API_TIMEOUT)
        
        execution_time = time.time() - start_time
        print(f"⏱️ API: Операция завершена за {execution_time:.2f} секунд")
        
        if result.get('success'):
            print(f"✅ API: Оптимизация успешно загружена в базу")
            print(f"📊 API: Вставлено листов: {result.get('inserted_count', 0)}")
            
            response_data = {
                "success": True,
                "message": f"Данные оптимизации успешно загружены за {execution_time:.2f} секунд",
                "grorderid": request.grorderid,
                "sheets_count": len(request.sheets),
                "execution_time": round(execution_time, 2),
                "details": result
            }
            
            # Добавляем информацию о корректировке материалов
            if request.adjust_materials:
                response_data["materials_adjusted"] = result.get('materials_adjusted', False)
                if result.get('materials_adjusted'):
                    print(f"✅ API: Корректировка материалов выполнена успешно")
                    print(f"📊 API: Детали корректировки: {result}")
                else:
                    print(f"⚠️ API: Корректировка материалов не выполнена")
            
            return response_data
        else:
            error_msg = result.get('message', 'Неизвестная ошибка базы данных')
            print(f"❌ API: Ошибка загрузки в базу: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
            
    except asyncio.TimeoutError:
        execution_time = time.time() - start_time
        error_msg = f"Превышен таймаут ожидания ответа от базы данных ({API_TIMEOUT} секунд). " \
                   f"Операция выполнялась {execution_time:.2f} секунд. " \
                   f"Вероятно, база данных заблокирована другим процессом или операция слишком сложная."
        print(f"❌ API: {error_msg}")
        raise HTTPException(status_code=504, detail=error_msg)
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Ошибка загрузки оптимизации за {execution_time:.2f} секунд: {str(e)}"
        print(f"❌ API: {error_msg}")
        import traceback
        print(f"❌ API: Трассировка ошибки: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_msg)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    uvicorn.run(app, host="0.0.0.0", port=8000)