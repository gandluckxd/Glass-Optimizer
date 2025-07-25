from pydantic import BaseModel
from typing import Optional

class OptimizationRequest(BaseModel):
    glass_type: str
    width: float
    height: float
    quantity: int

class OptimizationResult(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class DetailsRawRequest(BaseModel):
    grorderid: int

class WarehouseRemainderRequest(BaseModel):
    goodsid: int

class WarehouseMainMaterialRequest(BaseModel):
    goodsid: int
