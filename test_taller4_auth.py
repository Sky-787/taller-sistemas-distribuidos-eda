"""
test_taller4_auth.py
Suite de pruebas automatizadas completas para el Taller 4:
- LAB 10: Autenticación JWT + RBAC (Roles: user, admin, superadmin)
- Seguridad de Contraseñas (Hashing con bcrypt)
- Ciclo de Vida del Token (Generación, claims, expiración)
- Patrones de Resiliencia (Circuit Breaker y Rate Limiting)
"""

import os
import sys
import time
from datetime import timedelta
import unittest
from fastapi.testclient import TestClient

# Asegurar path para importar orders-service
sys.path.insert(0, os.path.abspath("orders-service"))

from main import app
from database import SessionLocal, UserModel, get_user_by_email
from auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ROLE_HIERARCHY
)
from resilience import catalog_circuit_breaker, CircuitState, rate_limiter
from jose import jwt


class TestTaller4AuthAndResilience(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Inicializa el cliente de pruebas de FastAPI y usuarios de prueba."""
        cls.client = TestClient(app)
        cls.db = SessionLocal()

        # Limpiar usuarios de prueba si existían
        test_emails = [
            "test_user@taller4.com",
            "test_admin@taller4.com",
            "test_superadmin@taller4.com",
            "test_new_register@taller4.com"
        ]
        for email in test_emails:
            u = get_user_by_email(cls.db, email)
            if u:
                cls.db.delete(u)
        cls.db.commit()

        # Crear usuarios para la suite de pruebas
        users_to_create = [
            ("test_user@taller4.com", "Test User Standard", "UserSecret123!", "user"),
            ("test_admin@taller4.com", "Test Admin Ops", "AdminSecret123!", "admin"),
            ("test_superadmin@taller4.com", "Test Super Admin", "SuperAdminSecret123!", "superadmin"),
        ]
        for email, name, pwd, role in users_to_create:
            u = UserModel(
                email=email,
                full_name=name,
                role=role,
                hashed_password=get_password_hash(pwd)
            )
            cls.db.add(u)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        """Limpia los usuarios de prueba creados."""
        test_emails = [
            "test_user@taller4.com",
            "test_admin@taller4.com",
            "test_superadmin@taller4.com",
            "test_new_register@taller4.com"
        ]
        for email in test_emails:
            u = get_user_by_email(cls.db, email)
            if u:
                cls.db.delete(u)
        cls.db.commit()
        cls.db.close()

    # ─── 1. Pruebas de Hashing y Verificación de Contraseñas ────────
    def test_01_password_hashing_and_verification(self):
        """Punto 5 y 6: Valida que bcrypt genera hashes únicos y verify_password los valida."""
        raw_password = "MySecurePassword2026!"
        hashed = get_password_hash(raw_password)

        self.assertNotEqual(raw_password, hashed)
        self.assertTrue(hashed.startswith("$2b$") or hashed.startswith("$2a$"))
        self.assertTrue(verify_password(raw_password, hashed))
        self.assertFalse(verify_password("WrongPassword123", hashed))
        print(" [PASS] 1. Cifrado bcrypt y verificación de contraseñas funcionando correctamente")

    # ─── 2. Registro de Usuarios ────────────────────────────────────
    def test_02_register_user_endpoint(self):
        """Punto 4 y 10: Registro de usuario en /auth/register y omisión de hashed_password."""
        payload = {
            "email": "test_new_register@taller4.com",
            "full_name": "Nuevo Usuario Registrado",
            "password": "PasswordRegistrada2026!",
            "role": "user"
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["email"], payload["email"])
        self.assertEqual(data["full_name"], payload["full_name"])
        self.assertEqual(data["role"], "user")
        self.assertIn("id", data)
        # Seguridad: Punto 11.4: Evita devolver hashed_password
        self.assertNotIn("hashed_password", data)
        self.assertNotIn("password", data)

        # Verificar en BD que la contraseña esté hasheada y nunca en texto plano
        user_in_db = get_user_by_email(self.db, payload["email"])
        self.assertIsNotNone(user_in_db)
        self.assertNotEqual(user_in_db.hashed_password, payload["password"])
        self.assertTrue(verify_password(payload["password"], user_in_db.hashed_password))
        print(" [PASS] 2. Registro de usuarios con contraseña hasheada y respuesta segura")

    def test_03_register_duplicate_email_fails(self):
        """Valida que no se permitan emails duplicados (HTTP 400)."""
        payload = {
            "email": "test_user@taller4.com",
            "full_name": "Duplicado",
            "password": "pwd",
            "role": "user"
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("ya se encuentra registrado", response.json()["detail"])
        print(" [PASS] 3. Validación de unicidad de email en registro (HTTP 400)")

    # ─── 3. Inicio de Sesión y Generación de Tokens JWT ─────────────
    def test_04_login_success_and_jwt_generation(self):
        """Puntos 2, 7 y 10: Login en /auth/login retorna token JWT válido con expiración."""
        login_data = {
            "username": "test_user@taller4.com",
            "password": "UserSecret123!"
        }
        response = self.client.post("/auth/login", data=login_data)
        self.assertEqual(response.status_code, 200)
        token_info = response.json()

        self.assertIn("access_token", token_info)
        self.assertEqual(token_info["token_type"], "bearer")

        # Decodificar y validar claims del JWT
        token = token_info["access_token"]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        self.assertEqual(payload["sub"], "test_user@taller4.com")
        self.assertEqual(payload["role"], "user")
        self.assertIn("exp", payload)
        print(" [PASS] 4. Login exitoso y generación de token JWT firmado HS256 con claims")

    def test_05_login_invalid_credentials_fails(self):
        """Punto 8: Credenciales inválidas retornan HTTP 401 Unauthorized."""
        response = self.client.post("/auth/login", data={
            "username": "test_user@taller4.com",
            "password": "ContrasenaIncorrecta"
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn("incorrectos", response.json()["detail"])

        # Usuario inexistente
        response_non_existent = self.client.post("/auth/login", data={
            "username": "no_existe@taller4.com",
            "password": "SomePassword"
        })
        self.assertEqual(response_non_existent.status_code, 401)
        print(" [PASS] 5. Rechazo de credenciales inválidas (HTTP 401 Unauthorized)")

    # ─── 4. Validación de Usuario Autenticado (/auth/me) ────────────
    def test_06_get_current_user_profile(self):
        """Punto 8: Endpoint protegido /auth/me retorna perfil a partir del token Bearer."""
        # Obtener token
        token = create_access_token({"sub": "test_admin@taller4.com", "role": "admin"})
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.get("/auth/me", headers=headers)
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(profile["email"], "test_admin@taller4.com")
        self.assertEqual(profile["role"], "admin")
        self.assertNotIn("hashed_password", profile)
        print(" [PASS] 6. Endpoint /auth/me identifica al usuario a partir del token Bearer")

    def test_07_access_protected_endpoint_without_token_fails(self):
        """Valida que invocar endpoint protegido sin token retorne HTTP 401."""
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)
        print(" [PASS] 7. Petición sin token rechazada con HTTP 401 Unauthorized")

    def test_08_expired_token_fails(self):
        """Punto 10 y 11: Token expirado es rechazado con HTTP 401."""
        # Crear token expirado en el pasado
        expired_token = create_access_token(
            {"sub": "test_user@taller4.com", "role": "user"},
            expires_delta=timedelta(seconds=-10)
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = self.client.get("/auth/me", headers=headers)
        self.assertEqual(response.status_code, 401)
        print(" [PASS] 8. Token JWT expirado rechazado con HTTP 401 Unauthorized")

    # ─── 5. Control de Acceso Basado en Roles (RBAC) ─────────────────
    def test_09_rbac_admin_endpoint_permissions(self):
        """
        Punto 9: Endpoint /admin (requiere 'admin'):
        - Rol 'user' (Nivel 1): 403 Forbidden
        - Rol 'admin' (Nivel 2): 200 OK
        - Rol 'superadmin' (Nivel 3): 200 OK (Jerarquía)
        """
        token_user = create_access_token({"sub": "test_user@taller4.com", "role": "user"})
        token_admin = create_access_token({"sub": "test_admin@taller4.com", "role": "admin"})
        token_superadmin = create_access_token({"sub": "test_superadmin@taller4.com", "role": "superadmin"})

        # Caso A: Usuario estándar intenta acceder al panel admin
        res_user = self.client.get("/admin", headers={"Authorization": f"Bearer {token_user}"})
        self.assertEqual(res_user.status_code, 403)
        self.assertIn("Permisos insuficientes", res_user.json()["detail"])

        # Caso B: Administrador accede al panel admin
        res_admin = self.client.get("/admin", headers={"Authorization": f"Bearer {token_admin}"})
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.json()["mensaje"], "Acceso autorizado")

        # Caso C: Superadministrador accede al panel admin (jerarquía nivel 3 >= 2)
        res_superadmin = self.client.get("/admin", headers={"Authorization": f"Bearer {token_superadmin}"})
        self.assertEqual(res_superadmin.status_code, 200)
        self.assertEqual(res_superadmin.json()["mensaje"], "Acceso autorizado")
        print(" [PASS] 9. RBAC: /admin permite admin y superadmin, rechaza rol 'user' (403)")

    def test_10_rbac_superadmin_endpoint_permissions(self):
        """
        Punto 9: Endpoint /superadmin (requiere 'superadmin'):
        - Rol 'user': 403 Forbidden
        - Rol 'admin': 403 Forbidden
        - Rol 'superadmin': 200 OK
        """
        token_user = create_access_token({"sub": "test_user@taller4.com", "role": "user"})
        token_admin = create_access_token({"sub": "test_admin@taller4.com", "role": "admin"})
        token_superadmin = create_access_token({"sub": "test_superadmin@taller4.com", "role": "superadmin"})

        res_user = self.client.get("/superadmin", headers={"Authorization": f"Bearer {token_user}"})
        self.assertEqual(res_user.status_code, 403)

        res_admin = self.client.get("/superadmin", headers={"Authorization": f"Bearer {token_admin}"})
        self.assertEqual(res_admin.status_code, 403)

        res_superadmin = self.client.get("/superadmin", headers={"Authorization": f"Bearer {token_superadmin}"})
        self.assertEqual(res_superadmin.status_code, 200)
        self.assertIn("Superadministrador", res_superadmin.json()["nivel_acceso"])
        print(" [PASS] 10. RBAC: /superadmin restringe acceso exclusivamente a 'superadmin'")

    # ─── 6. Patrones de Resiliencia: Circuit Breaker y Rate Limit ───
    def test_11_circuit_breaker_telemetry_and_transitions(self):
        """Valida que el Circuit Breaker transiciona de CLOSED a OPEN tras superar umbral de fallos."""
        status = self.client.get("/resilience/circuit-breaker").json()
        self.assertIn("state", status)
        self.assertIn("failure_count", status)

        # Probar registro de fallos
        catalog_circuit_breaker.record_failure()
        catalog_circuit_breaker.record_failure()
        catalog_circuit_breaker.record_failure()
        self.assertEqual(catalog_circuit_breaker.state, CircuitState.OPEN)
        self.assertFalse(catalog_circuit_breaker.can_execute())

        # Restaurar estado cerrado para no alterar otras pruebas
        catalog_circuit_breaker.record_success()
        self.assertEqual(catalog_circuit_breaker.state, CircuitState.CLOSED)
        self.assertTrue(catalog_circuit_breaker.can_execute())
        print(" [PASS] 11. Circuit Breaker conmuta estados correctamente ante fallas consecutivas")

    def test_12_rate_limiting_headers(self):
        """Valida que el middleware inyecte los encabezados X-RateLimit en las respuestas."""
        response = self.client.get("/orders")
        self.assertIn("X-RateLimit-Limit", response.headers)
        self.assertIn("X-RateLimit-Remaining", response.headers)
        print(" [PASS] 12. Middleware de Rate Limiting activo e inyectando headers HTTP")


if __name__ == "__main__":
    unittest.main()

