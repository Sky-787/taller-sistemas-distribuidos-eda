from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="Catalog Service",
    description="Servicio de catálogo de espacios de coworking",
    version="1.0.0"
)

# Modelo de datos para un espacio de coworking (CAMBIO DE CONTRATO INCOMPATIBLE)
class Space(BaseModel):
    id: int
    name: str
    capacity: int
    hourly_rate: float  # <--- ANTES: price_per_hour (Cambio de contrato sin versionar)
    available: bool = True

# Datos iniciales simulados en memoria
SPACES: List[Space] = [
    Space(id=1, name="Escritorio Individual Flex", capacity=1, hourly_rate=15.0, available=True),
    Space(id=2, name="Oficina Privada Junior", capacity=3, hourly_rate=35.0, available=True),
    Space(id=3, name="Sala de Juntas Ejecutiva", capacity=8, hourly_rate=60.0, available=True),
    Space(id=4, name="Auditorio Principal", capacity=25, hourly_rate=150.0, available=True),
]

@app.get("/health", tags=["Salud"])
def health_check():
    """Endpoint de verificación de salud del microservicio."""
    return {"status": "ok", "service": "catalog-service"}

@app.get("/spaces", response_model=List[Space], tags=["Espacios"])
def get_spaces():
    """Retorna la lista completa de espacios de coworking disponibles."""
    return SPACES

@app.get("/spaces/{space_id}", response_model=Space, tags=["Espacios"])
def get_space(space_id: int):
    """Retorna los detalles de un espacio específico por su ID."""
    for space in SPACES:
        if space.id == space_id:
            return space
    raise HTTPException(status_code=404, detail=f"Espacio con ID {space_id} no encontrado")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
