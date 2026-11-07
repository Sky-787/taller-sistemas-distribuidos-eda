import os
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import httpx
from fastapi import FastAPI, HTTPException, Query, Body, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, init_db, OrderModel, UserModel, OrderStatus, FulfillmentSource, get_user_by_email
from auth import (
    Token,
    TokenData,
    UserInDB,
    UserCreate,
    UserResponse,
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    require_role,
    oauth2_scheme
)
from resilience import catalog_circuit_breaker, CircuitState, RateLimitMiddleware

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orders-service")

app = FastAPI(
    title="Orders Service - Backend Avanzado",
    description="Servicio de órdenes con PostgreSQL, Event-Driven Architecture, Autenticación JWT + RBAC, Circuit Breaker y Rate Limiting",
    version="4.0.0"
)

# Middleware de Resiliencia: Rate Limiting
app.add_middleware(RateLimitMiddleware)

# URLs de otros servicios (configurables por variables de entorno)
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:8001")
if "catalog-service-coworking" in CATALOG_SERVICE_URL and not CATALOG_SERVICE_URL.endswith(".onrender.com"):
    CATALOG_SERVICE_URL = "https://catalog-service-coworking.onrender.com"
elif CATALOG_SERVICE_URL and not CATALOG_SERVICE_URL.startswith(("http://", "https://")):
    CATALOG_SERVICE_URL = f"http://{CATALOG_SERVICE_URL}"

ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics-service:8003")

# Caché local de espacios sincronizada mediante eventos (Event-Carried State Transfer)
SPACES_CACHE: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "name": "Escritorio Individual Flex", "price_per_hour": 15.0, "hourly_rate": 15.0, "available": True},
    2: {"id": 2, "name": "Oficina Privada Junior", "price_per_hour": 35.0, "hourly_rate": 35.0, "available": True},
    3: {"id": 3, "name": "Sala de Juntas Ejecutiva", "price_per_hour": 60.0, "hourly_rate": 60.0, "available": True},
    4: {"id": 4, "name": "Auditorio Principal", "price_per_hour": 150.0, "hourly_rate": 150.0, "available": True},
}

# Lista en memoria para compatibilidad retrospectiva con suites de pruebas
ORDERS: List[Dict[str, Any]] = []


# ─── Modelos Pydantic de Respuesta ────────────────────────────────
class OrderResponse(BaseModel):
    id: int
    space_id: int
    space_name: Optional[str] = None
    user_email: str
    hours: int
    price_per_hour: float
    total_price: float
    status: str = "CONFIRMED"
    fulfillment_source: str = "SYNCHRONOUS_CATALOG"
    created_at: str


# ─── Eventos de Startup ──────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    """Inicializa la base de datos PostgreSQL y crea usuarios semilla si no existen."""
    try:
        init_db()
        logger.info("Base de datos PostgreSQL inicializada correctamente")

        # Sembrar usuarios por defecto para pruebas de roles
        from database import SessionLocal
        db = SessionLocal()
        try:
            default_users = [
                ("user@coworking.com", "Usuario Demo", "User2026!", "user"),
                ("admin@coworking.com", "Administrador Demo", "Admin2026!", "admin"),
                ("superadmin@coworking.com", "Super Administrador", "SuperAdmin2026!", "superadmin"),
            ]
            for email, name, pwd, role in default_users:
                existing = get_user_by_email(db, email)
                if not existing:
                    u = UserModel(
                        email=email,
                        full_name=name,
                        role=role,
                        hashed_password=get_password_hash(pwd)
                    )
                    db.add(u)
            db.commit()
            logger.info("Usuarios semilla verificados/creados correctamente en PostgreSQL")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error al inicializar PostgreSQL o sembrar usuarios: {e}")


# ─── Endpoints de Inicio y Salud ──────────────────────────────────
@app.get("/", tags=["Inicio"])
def root():
    return {
        "message": "Microservicio de Órdenes de Coworking (FastAPI + JWT + RBAC + EDA)",
        "docs_url": "/docs",
        "version": "4.0.0",
        "endpoints": {
            "health": "/health",
            "auth_register": "/auth/register",
            "auth_login": "/auth/login",
            "auth_me": "/auth/me",
            "admin_panel": "/admin",
            "superadmin_panel": "/superadmin",
            "orders": "/orders",
            "catalog_cache": "/catalog-cache",
            "circuit_breaker": "/resilience/circuit-breaker",
            "event_webhook": "/events/space-changed"
        }
    }


@app.get("/health", tags=["Salud"])
def health_check(db: Session = Depends(get_db)):
    """Endpoint de verificación de salud del microservicio, PostgreSQL y Circuit Breaker."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": "orders-service",
        "version": "4.0.0",
        "database": db_status,
        "circuit_breaker": catalog_circuit_breaker.get_status()["state"]
    }


# ─── Endpoints de Autenticación (LAB 10 - JWT) ─────────────────────
@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Autenticación"])
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario en la base de datos PostgreSQL.
    - Cifra la contraseña con bcrypt antes de guardarla.
    - Asigna el rol especificado ('user', 'admin', 'superadmin').
    - Retorna el usuario creado omitiendo de forma segura el hashed_password.
    """
    valid_roles = ["user", "admin", "superadmin"]
    role = (user_in.role or "user").lower()
    if role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol '{role}' no válido. Roles permitidos: {valid_roles}"
        )

    existing_user = get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El correo electrónico '{user_in.email}' ya se encuentra registrado"
        )

    hashed_pwd = get_password_hash(user_in.password)
    new_user = UserModel(
        email=user_in.email,
        full_name=user_in.full_name,
        role=role,
        hashed_password=hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"Usuario registrado exitosamente: {new_user.email} con rol [{new_user.role}]")
    return UserResponse(**new_user.to_dict())


@app.post("/auth/login", response_model=Token, tags=["Autenticación"])
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica al usuario contra PostgreSQL y genera un token JWT firmado.
    - Recibe el email en el campo 'username' y la contraseña en 'password'.
    - Valida el hash con verify_password.
    - Genera el token con tiempo de expiración unificado (60 minutos) y rol.
    """
    user = get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo electrónico o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    logger.info(f"Sesión iniciada con éxito para usuario: {user.email}")
    return Token(access_token=access_token, token_type="bearer")


@app.get("/auth/me", response_model=UserResponse, tags=["Autenticación"])
def read_current_user(current_user: UserModel = Depends(get_current_user)):
    """Retorna el perfil del usuario autenticado a partir del token JWT Bearer."""
    return UserResponse(**current_user.to_dict())


# ─── Endpoints de Control de Acceso (LAB 10 - RBAC) ────────────────
@app.get("/admin", tags=["RBAC - Control de Acceso"])
async def panel_admin(current_user: UserModel = Depends(require_role("admin"))):
    """
    Ruta protegida para Administradores (Nivel 2) y Superadministradores (Nivel 3).
    Un usuario con rol 'user' (Nivel 1) recibirá HTTP 403 Forbidden.
    """
    return {
        "mensaje": "Acceso autorizado",
        "usuario": current_user.email,
        "rol": current_user.role,
        "nivel_acceso": "Administrador"
    }


@app.get("/superadmin", tags=["RBAC - Control de Acceso"])
async def panel_superadmin(current_user: UserModel = Depends(require_role("superadmin"))):
    """
    Ruta protegida exclusiva para Superadministradores (Nivel 3).
    Usuarios 'user' o 'admin' recibirán HTTP 403 Forbidden.
    """
    return {
        "mensaje": "Acceso exclusivo autorizado",
        "usuario": current_user.email,
        "rol": current_user.role,
        "nivel_acceso": "Superadministrador Principal"
    }


# ─── Endpoints de Resiliencia ──────────────────────────────────────
@app.get("/resilience/circuit-breaker", tags=["Resiliencia"])
def get_circuit_breaker_status():
    """Retorna el estado de telemetría y salud del Circuit Breaker."""
    return catalog_circuit_breaker.get_status()


# ─── Endpoints de Órdenes ─────────────────────────────────────────
@app.get("/orders", response_model=List[OrderResponse], tags=["Órdenes"])
def get_orders(db: Session = Depends(get_db)):
    """Retorna el listado completo de órdenes registradas en PostgreSQL."""
    orders = db.query(OrderModel).order_by(OrderModel.created_at.desc()).all()
    return [OrderResponse(**order.to_dict()) for order in orders]


@app.get("/catalog-cache", tags=["Event-Driven Architecture"])
def get_catalog_cache():
    """
    Retorna el estado de la caché local sincronizada a través de eventos SpaceChanged
    provenientes de EventBridge -> SQS -> Lambda Consumer.
    """
    return {
        "description": "Caché local desacoplada alimentada por eventos",
        "cached_spaces_count": len(SPACES_CACHE),
        "spaces": list(SPACES_CACHE.values())
    }


@app.post("/events/space-changed", tags=["Event-Driven Architecture"])
def handle_space_changed_event(event: Dict[str, Any] = Body(...)):
    """
    Webhook receptor invocado por la Lambda Consumidora (consumer-fn) de AWS.
    Aplica el patrón Event-Carried State Transfer para actualizar la disponibilidad
    y tarifas en tiempo real sin acoplamiento síncrono.
    """
    space_id = event.get("space_id")
    if not space_id:
        raise HTTPException(status_code=400, detail="Missing required field: 'space_id'")

    price = event.get("price_per_hour") or event.get("hourly_rate") or 0.0
    SPACES_CACHE[space_id] = {
        "id": space_id,
        "name": event.get("name", f"Espacio #{space_id}"),
        "capacity": event.get("capacity"),
        "available": bool(event.get("available", True)),
        "price_per_hour": float(price),
        "hourly_rate": float(price),
        "last_synced_at": event.get("timestamp", datetime.now(timezone.utc).isoformat())
    }

    logger.info(f"Caché de órdenes actualizada por evento para espacio #{space_id}: {SPACES_CACHE[space_id]}")
    return {
        "status": "synchronized",
        "space_id": space_id,
        "cached_data": SPACES_CACHE[space_id]
    }


@app.post("/orders", response_model=OrderResponse, status_code=201, tags=["Órdenes"])
async def create_order(
    space_id: int = Query(..., description="ID del espacio a reservar"),
    user_email: str = Query(..., description="Email del usuario que reserva"),
    hours: int = Query(..., gt=0, description="Cantidad de horas de reserva"),
    enable_eda_fallback: bool = Query(True, description="Usar caché Event-Driven si el catálogo síncrono falla"),
    db: Session = Depends(get_db)
):
    """
    Crea una nueva orden de reserva y la persiste en PostgreSQL con Circuit Breaker.
    1. Verifica el estado del Circuit Breaker para evitar sobrecargar el catálogo.
    2. Si está OPEN, conmuta inmediatamente a la caché EDA sin esperar timeout.
    3. Si está CLOSED/HALF_OPEN, intenta la consulta síncrona HTTP.
    4. Soporta tolerant reader (price_per_hour / hourly_rate).
    5. Persiste en PostgreSQL y notifica evento a analytics.
    """
    catalog_url = f"{CATALOG_SERVICE_URL}/spaces/{space_id}"
    space_data = None
    fulfillment_source = FulfillmentSource.SYNCHRONOUS_CATALOG

    # 1. Verificar Circuit Breaker antes de llamada síncrona
    if not catalog_circuit_breaker.can_execute():
        logger.warning(f"Circuit Breaker en estado {catalog_circuit_breaker.state.value}: cortocircuitando llamada a {catalog_url}")
    else:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(catalog_url)
                if response.status_code == 200:
                    space_data = response.json()
                    catalog_circuit_breaker.record_success()
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Space with id {space_id} not found in catalog")
                else:
                    logger.warning(f"Error HTTP del catálogo síncrono: {response.status_code}")
                    catalog_circuit_breaker.record_failure()
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise exc
            logger.warning(f"Catálogo síncrono no responde en {catalog_url}: {exc}")
            catalog_circuit_breaker.record_failure()
            if not enable_eda_fallback:
                raise HTTPException(status_code=503, detail="Catalog service unavailable") from exc

    # 2. Resiliencia Event-Driven: Si el catálogo síncrono falló o el circuito estaba abierto, usar caché local
    if space_data is None:
        if space_id in SPACES_CACHE:
            logger.info(f"Activando Fallback Resiliente EDA: Usando caché local para espacio #{space_id}")
            space_data = SPACES_CACHE[space_id]
            fulfillment_source = FulfillmentSource.EVENT_CACHE_FALLBACK
        else:
            raise HTTPException(
                status_code=503,
                detail="Catalog service unavailable and no cached event state found for this space"
            )

    # Validar disponibilidad
    if not space_data.get("available", True):
        raise HTTPException(
            status_code=400,
            detail=f"El espacio '{space_data.get('name')}' no se encuentra disponible actualmente."
        )

    # Tolerant Reader (Soporta tanto 'price_per_hour' como 'hourly_rate')
    price_val = space_data.get("price_per_hour")
    if price_val is None:
        price_val = space_data.get("hourly_rate")

    if price_val is None:
        raise HTTPException(
            status_code=500,
            detail="Contract error: neither 'price_per_hour' nor 'hourly_rate' found in space data"
        )

    price_per_hour = float(price_val)
    total_price = round(price_per_hour * hours, 2)
    space_name = space_data.get("name", f"Espacio #{space_id}")

    # 3. Persistir en PostgreSQL
    order = OrderModel(
        space_id=space_id,
        space_name=space_name,
        user_email=user_email,
        hours=hours,
        price_per_hour=price_per_hour,
        total_price=total_price,
        status=OrderStatus.CONFIRMED,
        fulfillment_source=fulfillment_source,
        created_at=datetime.now(timezone.utc)
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    # Sincronizar en memoria para tests retrospectivos
    order_dict = order.to_dict()
    ORDERS.append(order_dict)

    logger.info(f"Orden #{order.id} persistida en PostgreSQL (Fuente: {fulfillment_source.value})")

    # 4. Enviar evento de analytics (best-effort, no bloquea la orden)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{ANALYTICS_SERVICE_URL}/events", json={
                "event_type": "order_created",
                "order_id": order.id,
                "space_id": space_id,
                "space_name": space_name,
                "user_email": user_email,
                "hours": hours,
                "price_per_hour": price_per_hour,
                "total_price": total_price,
                "fulfillment_source": fulfillment_source.value
            })
    except Exception as e:
        logger.warning(f"No se pudo enviar evento de analytics: {e}")

    return OrderResponse(**order_dict)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
