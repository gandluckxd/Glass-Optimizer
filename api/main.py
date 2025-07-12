from fastapi import FastAPI
from dotenv import load_dotenv
import uvicorn
from routes import router
from pydantic import BaseModel
from typing import List, Optional
from fastapi import HTTPException
import asyncio
from concurrent.futures import ThreadPoolExecutor

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
    is_remainder: int
    xml_data: str

class OptimizationUploadRequest(BaseModel):
    """Модель запроса загрузки оптимизации"""
    grorderid: int
    sheets: List[OptimizationSheet]

@app.post("/upload-optimization")
async def upload_optimization(request: OptimizationUploadRequest):
    """
    Загрузка данных оптимизации в базу данных Altawin
    
    Этапы:
    1. Удаление существующих данных для grorderid
    2. Вставка новых записей в таблицу OPTDATA
    """
    try:
        print(f"🔄 API: Начало загрузки оптимизации для grorderid={request.grorderid}")
        print(f"📊 API: Количество листов: {len(request.sheets)}")
        
        from db_functions import upload_optimization_to_db
        
        loop = asyncio.get_running_loop()
        
        # Запускаем блокирующую функцию в отдельном потоке
        future = loop.run_in_executor(
            executor, 
            upload_optimization_to_db, 
            request.grorderid, 
            [sheet.dict() for sheet in request.sheets] # Преобразуем модели в словари
        )
        
        # Ждем результат с таймаутом в 30 секунд
        result = await asyncio.wait_for(future, timeout=30.0)
        
        if result.get('success'):
            print(f"✅ API: Оптимизация успешно загружена в базу")
            return {
                "success": True,
                "message": f"Данные оптимизации успешно загружены",
                "grorderid": request.grorderid,
                "sheets_count": len(request.sheets),
                "details": result
            }
        else:
            error_msg = result.get('message', 'Неизвестная ошибка базы данных')
            print(f"❌ API: Ошибка загрузки в базу: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
            
    except asyncio.TimeoutError:
        error_msg = "Превышен таймаут ожидания ответа от базы данных (30 секунд). Вероятно, база данных заблокирована другим процессом."
        print(f"❌ API: {error_msg}")
        raise HTTPException(status_code=504, detail=error_msg)
    except Exception as e:
        error_msg = f"Ошибка загрузки оптимизации: {str(e)}"
        print(f"❌ API: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)