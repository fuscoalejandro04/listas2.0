from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class Product(BaseModel):
    # Campos estándar de la taxonomía
    codigo: str
    nombre_articulo: str
    descripcion: Optional[str] = None
    marca: Optional[str] = None
    precio_lista: float = Field(gt=0, description="El precio debe ser mayor a cero")
    iva: Optional[float] = Field(None, ge=0, le=100)
    ean: Optional[str] = None
    moneda: Optional[str] = "USD"
    
    # Metadatos del sistema (auditoría)
    proveedor_origen: Optional[str] = None
    fecha_importacion: datetime = Field(default_factory=datetime.now)
    confianza_mapping: float = Field(default=1.0, ge=0, le=1.0)

    @validator('ean')
    def validate_ean(cls, v):
        if v is not None:
            # Validación básica: que sea numérico y de 13 dígitos (luego pondremos checksum)
            if not v.isdigit() or len(v) != 13:
                raise ValueError('EAN debe tener 13 dígitos numéricos')
        return v
