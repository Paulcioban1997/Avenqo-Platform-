import json
import urllib.request
import urllib.error

def test_invalid_password():
    url = "http://localhost:3000/api/auth/register"
    payload = {
        "email": "invalid-pw-test@avenqo.ca",
        "password": "simplepassword",
        "first_name": "Test",
        "last_name": "User",
        "company_name": "Test Co",
        "company_email": "invalid-pw-test@avenqo.ca",
        "country": "Canada",
        "timezone": "America/Toronto",
        "industry": "Commerce"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req)
        print("FAIL: Expected 422 error")
    except urllib.error.HTTPError as e:
        content_type = e.headers.get("Content-Type", "")
        body = e.read().decode("utf-8")
        data = json.loads(body)
        print("Status code:", e.code)
        print("Content-Type:", content_type)
        print("Response data:", json.dumps(data, ensure_ascii=False, indent=2))
        
        # Verify no "Value error, " prefix
        details = data.get("error", {}).get("details", [])
        for d in details:
            msg = d.get("msg", "")
            assert not msg.startswith("Value error,"), f"Prefix found in: {msg}"
            print("Validation message:", msg)
            if "mot de passe" in msg.lower():
                assert "caractère spécial" in msg, f"Accents broken: {msg}"
                print("SUCCESS: Clean accents, no mojibake, no 'Value error,' prefix!")

if __name__ == "__main__":
    test_invalid_password()
