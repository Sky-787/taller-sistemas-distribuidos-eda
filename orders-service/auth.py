"""
auth.py - Módulo de Autenticación JWT y Control de Acceso Basado en Roles (RBAC)
Taller 4: Backend Avanzado FastAPI (LAB 10)
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db, UserModel, get_user_by_email

# ─── 2. Configuración de Seguridad ─────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", "change-me-in-production")
ALGORITHM = "HS256"
# Unificado a 60 minutos según especificación del Taller 4
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# ─── 3. Configuración de Cifrado y Esquema OAuth2 ───────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Jerarquía de permisos RBAC: user (1) < admin (2) < superadmin (3)
ROLE_HIERARCHY: Dict[str, int] = {
    "user": 1,
    "admin": 2,
    "superadmin": 3
}


# ─── 4. Modelos de Datos Pydantic ──────────────────────────────────
class Token(BaseModel):
    """Información que recibe el cliente tras autenticarse con éxito."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Datos payload extraídos del token JWT."""
    email: Optional[str] = None
    role: Optional[str] = "user"


class UserInDB(BaseModel):
    """Representación de usuario almacenado en base de datos."""
    id: Optional[int] = None
    email: str
    full_name: str
    role: str = "user"
    hashed_password: str


class UserCreate(BaseModel):
    """Esquema de entrada para registro de nuevos usuarios."""
    email: str
    full_name: str
    password: str
    role: Optional[str] = "user"


class UserResponse(BaseModel):
    """Esquema de respuesta de usuario (protege la contraseña omitiendo el hash)."""
    id: int
    email: str
    full_name: str
    role: str
    created_at: Optional[str] = None


# ─── 5. Verificación de Contraseñas ────────────────────────────────
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con su hash bcrypt."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── 6. Generación de Hashes de Contraseñas ────────────────────────
def get_password_hash(password: str) -> str:
    """Genera el hash seguro bcrypt de la contraseña proporcionada."""
    return pwd_context.hash(password)


# ─── 7. Creación del Token de Acceso JWT ───────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Genera un token JWT firmado con algoritmo HS256 y fecha de expiración UTC.
    Unifica el tiempo de duración por defecto a ACCESS_TOKEN_EXPIRE_MINUTES (60 min).
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ─── 8. Identificación del Usuario Autenticado ───────────────────────
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserModel:
    """
    Decodifica y valida el token JWT Bearer, extrayendo el correo y rol.
    Verifica la existencia del usuario en la base de datos PostgreSQL.
    Lanza HTTP 401 Unauthorized si el token es inválido, expirado o el usuario no existe.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas, token expirado o no proporcionado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub") or payload.get("email")
        role: str = payload.get("role", "user")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email, role=role)
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user


# ─── 9. Control de Permisos según el Rol (RBAC) ────────────────────
def require_role(required_role: str):
    """
    Fábrica de dependencias para autorización jerárquica de roles (RBAC).
    Permite acceso si el nivel del rol del usuario es >= al requerido:
    - user: Nivel 1 (Usuario básico)
    - admin: Nivel 2 (Administrador)
    - superadmin: Nivel 3 (Administrador principal)
    Lanza HTTP 403 Forbidden si el usuario no tiene permisos suficientes.
    """
    def role_checker(current_user: UserModel = Depends(get_current_user)) -> UserModel:
        user_role = (current_user.role or "user").lower()
        req_role = required_role.lower()

        user_level = ROLE_HIERARCHY.get(user_role, 0)
        required_level = ROLE_HIERARCHY.get(req_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes: se requiere rol '{required_role}' o superior (rol actual: '{current_user.role}')"
            )
        return current_user

    return role_checker

