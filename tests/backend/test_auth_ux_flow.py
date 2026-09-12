import pytest
import httpx
from backend.app.core.security import hash_password, verify_password, generate_token, hash_token

BACKEND_URL = "http://127.0.0.1:8000"

def test_anti_enumeration_forgot_password():
    """Vérifie que la réponse de mot de passe oublié est strictement neutre pour email existant ou non."""
    client = httpx.Client(base_url=BACKEND_URL, timeout=10.0)
    
    # Test avec un email inconnu
    r_unknown = client.post("/api/v1/auth/password/forgot", json={"email": "nonexistent_test_account_9999@avenqo.ca"})
    assert r_unknown.status_code == 200
    data_unknown = r_unknown.json()
    msg = data_unknown.get("message", "").lower()
    assert "compte" in msg and "email" in msg

    # Test avec le compte démo existant
    r_known = client.post("/api/v1/auth/password/forgot", json={"email": "demo@avenqo.ca"})
    assert r_known.status_code == 200
    data_known = r_known.json()
    
    # Doit avoir exactement le même format / structure pour éviter l'énumération
    assert r_unknown.status_code == r_known.status_code
    assert r_unknown.json() == r_known.json()

def test_reset_password_invalid_token_rejected():
    """Vérifie qu'un faux token ou token invalide est refusé avec HTTP 400."""
    client = httpx.Client(base_url=BACKEND_URL, timeout=10.0)
    
    r = client.post(
        "/api/v1/auth/password/reset",
        json={
            "token": "invalid_or_fake_token_1234567890",
            "new_password": "NewSecurePassword2026!",
        }
    )
    assert r.status_code == 400
    res = r.json()
    msg = (res.get("error", {}).get("message") or res.get("detail") or "").lower()
    assert "invalide" in msg or "expir" in msg

def test_reset_password_weak_password_rejected():
    """Vérifie qu'un mot de passe trop faible est rejeté."""
    client = httpx.Client(base_url=BACKEND_URL, timeout=10.0)
    
    r = client.post(
        "/api/v1/auth/password/reset",
        json={
            "token": "some_token",
            "new_password": "weak",
        }
    )
    assert r.status_code in (400, 422)

if __name__ == "__main__":
    test_anti_enumeration_forgot_password()
    test_reset_password_invalid_token_rejected()
    test_reset_password_weak_password_rejected()
    print("ALL AUTH UX BACKEND TESTS PASSED SUCCESSFULLY!")
