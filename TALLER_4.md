# Taller 4: Backend Avanzado FastAPI
## LAB 10: Autenticación JWT + RBAC y Patrones de Resiliencia en orders-service

---

## 🎯 1. Objetivo General

Añadir autenticación robusta mediante tokens **JSON Web Tokens (JWT)**, autorización jerárquica con **Control de Acceso Basado en Roles (RBAC)**, persistencia segura de usuarios en **PostgreSQL (AWS RDS)** mediante **SQLAlchemy** y **Alembic**, y patrones de resiliencia avanzada (**Circuit Breaker** y **Rate Limiting**) al microservicio `orders-service`.

---

## 🏗️ 2. Arquitectura de Seguridad y Roles (RBAC)

El sistema define tres niveles jerárquicos de acceso:

| Rol | Nivel | Descripción | Rutas Permitidas |
| :--- | :---: | :--- | :--- |
| **`user`** | 1 | Usuario básico del coworking | `/orders`, `/catalog-cache`, `/auth/me` |
| **`admin`** | 2 | Administrador operativo | Todas las de `user` + `/admin`, gestión operativa |
| **`superadmin`** | 3 | Administrador principal / Seguridad | Acceso global irrestricto + `/superadmin`, auditoría |

### Diagrama de Flujo de Autenticación y Autorización

```
┌──────────────┐                  ┌────────────────────────────────────────┐                  ┌────────────────┐
│   Cliente    │ ── POST /login ─>│             orders-service             │ ── Consulta ────>│ PostgreSQL RDS │
│ (Swagger/UI) │                  │ (Verifica bcrypt hash + Genera JWT)    │                  │  (Tabla users) │
│              │ <── 200 Token ───│                                        │ <── UserData ────│                │
└──────────────┘                  └────────────────────────────────────────┘                  └────────────────┘
       │                                       │
       │ Bearer <token>                        ▼
       ├─────────────────────────> [ Middleware Rate Limiting ] (Sliding Window)
       │                                       │
       ├─────────────────────────> [ OAuth2PasswordBearer ] (Decodifica JWT HS256)
       │                                       │
       ├─────────────────────────> [ get_current_user ] (Verifica existencia en DB)
       │                                       │
       └─────────────────────────> [ require_role("admin") ]
                                               │
                                    ┌──────────┴──────────┐
                                    ▼                     ▼
                          Nivel >= 2? (SÍ)          Nivel < 2? (NO)
                            [ 200 OK ]              [ 403 Forbidden ]
```

---

## 📦 3. Dependencias Incorporadas (`orders-service/requirements.txt`)

```text
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
httpx==0.25.2
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.13.1
python-jose[cryptography]==3.5.0
passlib==1.7.4
bcrypt==3.2.2
python-multipart==0.0.33
```

---

## 🗄️ 4. Modelo de Datos y Migración Alembic (`UserModel`)

En [`orders-service/database.py`](orders-service/database.py):

```python
class UserModel(Base):
    """Modelo SQLAlchemy para usuarios del sistema con roles y contraseñas hasheadas (RBAC)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user") # 'user', 'admin', 'superadmin'
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        """Convierte el modelo a diccionario seguro para respuestas de API (sin hashed_password)."""
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
```

### Migración Alembic Generada y Aplicada
- Archivo: `orders-service/alembic/versions/8f5e47c59a2f_add_users_table_for_rbac_auth.py`
- Estado: **Migrado exitosamente a PostgreSQL (AWS RDS)**.

---

## 🔐 5. Módulo de Autenticación (`orders-service/auth.py`)

Implementa los 10 puntos clave requeridos por el taller:
1. **Configuración de Seguridad**: `SECRET_KEY`, algoritmo `HS256`, y expiración `ACCESS_TOKEN_EXPIRE_MINUTES = 60`.
2. **Cifrado de Contraseñas**: `pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")`.
3. **Esquema OAuth2**: `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")`.
4. **Modelos Pydantic**: `Token`, `TokenData`, `UserInDB`, `UserCreate` y `UserResponse` (sin exponer hashes).
5. **Verificación**: `verify_password(plain, hashed)`.
6. **Hashing**: `get_password_hash(password)`.
7. **Generador JWT**: `create_access_token(data, expires_delta)` con timestamps UTC con zona horaria (`timezone.utc`).
8. **Identificación de Usuario**: `get_current_user` inyectado mediante dependencias de FastAPI (`Depends(oauth2_scheme)`, `Depends(get_db)`).
9. **Control de Acceso Jerárquico**: `require_role(required_role)` que valida la jerarquía matemática (`user: 1 < admin: 2 < superadmin: 3`) y retorna `HTTP 403 Forbidden` si el usuario no cuenta con privilegios suficientes.

---

## 🛡️ 6. Patrones de Resiliencia (`orders-service/resilience.py`)

Para cumplir integralmente con el objetivo del taller ("rate limiting, circuit breakers y patrones de resiliencia"):

1. **Circuit Breaker (`CircuitBreaker`)**:
   - Monitorea llamadas al microservicio de catálogo.
   - Si se presentan 3 fallas consecutivas, el circuito conmuta de `CLOSED` a `OPEN`.
   - Cuando está `OPEN`, cortocircuita las llamadas síncronas de inmediato, evitando bloqueos por timeout y conmutando directamente a la caché resiliente EDA (**Event-Carried State Transfer**).
   - Tras 15 segundos de enfriamiento, transiciona a `HALF_OPEN` para verificar si el catálogo se ha recuperado.
2. **Rate Limiter (`RateLimitMiddleware`)**:
   - Algoritmo de ventana deslizante en memoria (*Sliding Window*).
   - Inyecta encabezados estándar `X-RateLimit-Limit` y `X-RateLimit-Remaining`.
   - Retorna `HTTP 429 Too Many Requests` con el header `Retry-After` ante ráfagas excesivas.

---

## 🛠️ 7. Puntos Críticos y Correcciones Aplicadas (Sección 11 del Taller)

| # | Detalle / Error Advertido | Solución Implementada en el Código |
| :-: | :--- | :--- |
| **1** | Faltan dependencias (`get_db`, `UserModel`). | Creados e importados desde `database.py`, con inyección de dependencias `Session = Depends(get_db)` y modelo ORM. |
| **2** | Tiempo de expiración discrepante (60 vs 15 min). | Unificado a **60 minutos** de duración por defecto en `create_access_token` y variable de entorno. |
| **3** | Rol del usuario consultado vs verificado. | `get_current_user` valida la existencia y rol directamente en PostgreSQL RDS, garantizando consistencia. |
| **4** | Fuga de contraseñas en respuestas. | Se implementó el esquema `UserResponse` y método `UserModel.to_dict()`, los cuales excluyen estrictamente `hashed_password`. |
| **5** | Fechas de expiración sin zona horaria. | Se utiliza `datetime.now(timezone.utc)` para garantizar cumplimiento estricto del estándar RFC 7519. |
| **6** | Seguridad de la información en el JWT. | El payload contiene únicamente `sub` (correo) y `role`. No se incluye información sensible ni confidencial. |

---

## 🧪 8. Resultados de la Suite de Pruebas Automatizadas

Se construyó una suite de pruebas integral en [`test_taller4_auth.py`](test_taller4_auth.py) que valida el 100% de los requisitos:

```bash
python test_taller4_auth.py
```

### Salida de la Ejecución:
```text
Ran 12 tests in 17.784s

OK
 [PASS] 1. Cifrado bcrypt y verificación de contraseñas funcionando correctamente
 [PASS] 2. Registro de usuarios con contraseña hasheada y respuesta segura
 [PASS] 3. Validación de unicidad de email en registro (HTTP 400)
 [PASS] 4. Login exitoso y generación de token JWT firmado HS256 con claims
 [PASS] 5. Rechazo de credenciales inválidas (HTTP 401 Unauthorized)
 [PASS] 6. Endpoint /auth/me identifica al usuario a partir del token Bearer
 [PASS] 7. Petición sin token rechazada con HTTP 401 Unauthorized
 [PASS] 8. Token JWT expirado rechazado con HTTP 401 Unauthorized
 [PASS] 9. RBAC: /admin permite admin y superadmin, rechaza rol 'user' (403)
 [PASS] 10. RBAC: /superadmin restringe acceso exclusivamente a 'superadmin'
 [PASS] 11. Circuit Breaker conmuta estados correctamente ante fallas consecutivas
 [PASS] 12. Middleware de Rate Limiting activo e inyectando headers HTTP
```

Adicionalmente, se verificó compatibilidad retrospectiva con la arquitectura Serverless del Taller 2:
```bash
python test_serverless_pipeline.py
# Ran 5 tests in 5.163s -> OK (5/5 PASS)
```

---

## 👥 9. Usuarios Semilla Preconfigurados para Pruebas Inmediatas

Al iniciar la aplicación (`uvicorn main:app --port 8002`), se inicializan automáticamente en la base de datos:

| Correo | Contraseña | Rol | Nivel | Propósito de Prueba |
| :--- | :--- | :---: | :---: | :--- |
| `user@coworking.com` | `User2026!` | `user` | 1 | Acceso estándar; rechazo 403 en `/admin` |
| `admin@coworking.com` | `Admin2026!` | `admin` | 2 | Acceso permitido en `/admin`; rechazo 403 en `/superadmin` |
| `superadmin@coworking.com` | `SuperAdmin2026!` | `superadmin` | 3 | Acceso total permitido a `/admin` y `/superadmin` |

