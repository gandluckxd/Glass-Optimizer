from fastapi import APIRouter, HTTPException
from models import DetailsRawRequest, WarehouseRemainderRequest, WarehouseMainMaterialRequest
from db_functions import get_tables, get_details_raw, get_warehouse_remainders, get_warehouse_main_material, get_goods_price
import asyncio
import time

router = APIRouter()

@router.get("/tables")
def tables():
    return get_tables()

@router.post("/details-raw")
async def details_raw(request: DetailsRawRequest):
    """
    Получить детали с улучшенной обработкой таймаутов
    """
    try:
        print(f"🚀 API: Получен запрос details-raw для grorderid={request.grorderid}")
        start_time = time.time()
        
        # Выполняем запрос с таймаутом
        result = get_details_raw(request.grorderid)
        
        execution_time = time.time() - start_time
        print(f"✅ API: Запрос выполнен за {execution_time:.2f}с")
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time if 'start_time' in locals() else 0
        print(f"❌ API ERROR (details-raw): {e} (время выполнения: {execution_time:.2f}с)")
        
        # Если это таймаут, возвращаем более информативное сообщение
        if "timeout" in str(e).lower() or execution_time > 100:
            raise HTTPException(
                status_code=408, 
                detail={
                    "error": "Query timeout", 
                    "message": "Запрос к базе данных занял слишком много времени",
                    "grorderid": request.grorderid,
                    "execution_time": round(execution_time, 2),
                    "suggestions": [
                        "Проверьте производительность базы данных",
                        "Убедитесь что grorderid существует",
                        "Попробуйте позже"
                    ]
                }
            )
        
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/warehouse-remainders")
def warehouse_remainders(request: WarehouseRemainderRequest):
    return get_warehouse_remainders(request.goodsid)

@router.post("/warehouse-main-material")
def warehouse_main_material(request: WarehouseMainMaterialRequest):
    return get_warehouse_main_material(request.goodsid)

@router.post("/goods-price")
def goods_price(request: WarehouseRemainderRequest):
    """
    Получить стоимость товара по goodsid
    """
    try:
        price = get_goods_price(request.goodsid)
        return {"price": price, "goodsid": request.goodsid}
    except Exception as e:
        print(f"❌ API ERROR (goods-price): {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
