import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import enum

# URL de conexión a PostgreSQL (viene del docker-compose)
# URL de conexión a PostgreSQL (viene del entorno o AWS RDS)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:Coworking2026!@coworking-orders-db.clams6woe8i0.us-east-2.rds.amazonaws.com:5432/coworking_orders"
)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# Engine con pool de conexiones
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # verifica conexión antes de usar
    pool_recycle=300,          # recicla conexiones cada 5 min
    echo=False
)

# Fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos declarativos
Base = declarative_base()


class OrderStatus(enum.Enum):
    """Enum para estados de una orden de reserva."""
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class FulfillmentSource(enum.Enum):
    """Origen de la información del espacio al crear la orden."""
    SYNCHRONOUS_CATALOG = "SYNCHRONOUS_CATALOG"
    EVENT_CACHE_FALLBACK = "EVENT_CACHE_FALLBACK"


class OrderModel(Base):
    """Modelo SQLAlchemy para órdenes de reserva de coworking."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, index=True)
    space_name = Column(String(255), nullable=True)
    user_email = Column(String(255), nullable=False, index=True)
    hours = Column(Integer, nullable=False)
    price_per_hour = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(
        SQLEnum(OrderStatus),
        nullable=False,
        default=OrderStatus.CONFIRMED
    )
    fulfillment_source = Column(
        SQLEnum(FulfillmentSource),
        nullable=False,
        default=FulfillmentSource.SYNCHRONOUS_CATALOG
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        """Convierte el modelo a diccionario compatible con la API."""
        return {
            "id": self.id,
            "space_id": self.space_id,
            "space_name": self.space_name,
            "user_email": self.user_email,
            "hours": self.hours,
            "price_per_hour": self.price_per_hour,
            "total_price": self.total_price,
            "status": self.status.value if self.status else "CONFIRMED",
            "fulfillment_source": self.fulfillment_source.value if self.fulfillment_source else "SYNCHRONOUS_CATALOG",
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class UserModel(Base):
    """Modelo SQLAlchemy para usuarios del sistema con roles y contraseñas hasheadas (RBAC)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user")
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


def get_user_by_email(db, email: str):
    """Consulta un usuario en PostgreSQL a partir de su correo electrónico."""
    return db.query(UserModel).filter(UserModel.email == email).first()


def get_db():
    """Generador de sesión de base de datos para inyección de dependencias en FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crea todas las tablas definidas en los modelos (si no existen)."""
    Base.metadata.create_all(bind=engine)

