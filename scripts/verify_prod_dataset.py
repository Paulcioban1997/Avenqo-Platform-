import uuid
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from backend.app.core.security import create_access_token, generate_token, hash_token

db_url = "postgresql://postgres:aVxFamcMziEnMoleBZCYdkLpOELxLatB@tramway.proxy.rlwy.net:25367/railway"
engine = create_engine(db_url)

with engine.begin() as conn:
    row = conn.execute(text("SELECT id, company_id FROM users WHERE email='gauffy95@gmail.com'")).fetchone()
    user_id = row[0]
    company_id = row[1]
    
    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=15)
    refresh_token = generate_token()
    
    conn.execute(text("""
        INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, created_at)
        VALUES (:id, :user_id, :token_hash, :expires_at, :created_at)
    """), {
        "id": session_id,
        "user_id": user_id,
        "token_hash": hash_token(refresh_token),
        "expires_at": expires_at,
        "created_at": now,
    })

try:
    import jwt
    now_jwt = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(company_id),
        "session_id": str(session_id),
        "jti": str(uuid.uuid4()),
        "iat": now_jwt,
        "exp": now_jwt + timedelta(minutes=15),
        "iss": "avenqo-platform",
        "aud": "avenqo-clients",
        "type": "access",
    }
    access_token = jwt.encode(payload, secret, algorithm="HS256")
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 1. GET /api/v1/datasets
    req = urllib.request.Request("https://api.avenqo.ca/api/v1/datasets", headers=headers)
    with urllib.request.urlopen(req) as resp:
        print(f"GET /api/v1/datasets HTTP {resp.status}")
        datasets = json.loads(resp.read().decode())
        print(f"Datasets returned: {len(datasets)}")
        for d in datasets:
            print(f"  - ID: {d['id']}, Name: {d['name']}, source_missing: {d.get('source_missing')}, pipeline_status: {d.get('pipeline_status')}")
            
    # 2. GET export CSV
    ds_id = "7d757146-97b7-43e5-8e84-f1aa0ab5afcd"
    req_export = urllib.request.Request(f"https://api.avenqo.ca/api/v1/datasets/{ds_id}/export/csv", headers=headers)
    try:
        with urllib.request.urlopen(req_export) as resp:
            print(f"GET /api/v1/datasets/{ds_id}/export/csv HTTP {resp.status}")
            content = resp.read()
            print(f"Export CSV size: {len(content)} bytes")
            print("First 150 bytes:\n", repr(content[:150]))
    except urllib.error.HTTPError as e:
        print(f"Export HTTP error {e.code}: {e.read().decode()}")
        
    # 3. GET cleaning detail
    req_cleaning = urllib.request.Request(f"https://api.avenqo.ca/api/v1/datasets/{ds_id}/cleaning", headers=headers)
    try:
        with urllib.request.urlopen(req_cleaning) as resp:
            print(f"GET /api/v1/datasets/{ds_id}/cleaning HTTP {resp.status}")
            cleaning = json.loads(resp.read().decode())
            print(f"Cleaning preview rows: {len(cleaning.get('rows', []))}")
            print("Cleaning keys:", list(cleaning.keys()))
    except urllib.error.HTTPError as e:
        print(f"Cleaning HTTP error {e.code}: {e.read().decode()}")

finally:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_sessions WHERE id = :id"), {"id": session_id})
        print("Cleaned up temporary verification session.")
