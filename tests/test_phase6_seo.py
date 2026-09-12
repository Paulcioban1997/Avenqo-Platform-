"""Automated tests for Phase 6: Next.js SEO, Sitemap, Robots, Schema.org, and Internationalization."""

import json
import re
import urllib.request
import urllib.error
import pytest

BASE_URL = "http://127.0.0.1:3005"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(path: str, headers: dict = None, follow_redirects: bool = True):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=headers or {})
    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=5) as response:
            return response.getcode(), response.headers, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8")


def test_robots_txt_spec():
    code, headers, body = fetch("/robots.txt")
    assert code == 200
    assert "User-Agent: *" in body or "User-agent: *" in body
    assert "Allow: /" in body
    assert "Allow: /pricing" in body
    assert "Allow: /terms" in body
    assert "Allow: /privacy" in body
    assert "Disallow: /dashboard" in body
    assert "Disallow: /retail" in body
    assert "Disallow: /admin" in body
    assert "Disallow: /api" in body
    assert "Disallow: /login" in body
    assert "Disallow: /register" in body
    assert "Sitemap: https://avenqo.ca/sitemap.xml" in body
    assert "Host: https://avenqo.ca" in body


def test_sitemap_xml_spec():
    code, headers, body = fetch("/sitemap.xml")
    assert code == 200
    assert "https://avenqo.ca/" in body
    assert "https://avenqo.ca/pricing" in body
    assert "https://avenqo.ca/terms" in body
    assert "https://avenqo.ca/privacy" in body
    # SaaS and auth private routes MUST NOT be in the sitemap
    assert "/dashboard" not in body
    assert "/retail" not in body
    assert "/central-ai" not in body
    assert "/data" not in body
    assert "/integrations" not in body
    assert "/admin" not in body
    assert "/login" not in body
    assert "/register" not in body
    assert "/api" not in body


def test_manifest_spec():
    code, headers, body = fetch("/manifest.webmanifest")
    assert code == 200
    data = json.loads(body)
    assert "Avenqo" in data.get("name", "")
    assert data.get("display") == "standalone"


def test_homepage_seo_and_json_ld():
    code, headers, body = fetch("/")
    assert code == 200
    # HTML lang
    assert '<html lang="fr"' in body
    # Title
    assert "Avenqo — AI Business Operating System" in body
    # Canonical
    assert '<link rel="canonical" href="https://avenqo.ca/"' in body or '<link rel="canonical" href="https://avenqo.ca"' in body
    # OpenGraph & Twitter
    assert 'property="og:title"' in body
    assert 'property="og:image"' in body
    assert 'name="twitter:card"' in body
    # JSON-LD Schema.org presence and validity
    schema_matches = re.findall(r'<script type="application/ld\+json">({.*?})</script>', body, re.DOTALL)
    assert len(schema_matches) >= 2
    types_found = set()
    for s in schema_matches:
        parsed = json.loads(s)
        types_found.add(parsed.get("@type"))
    assert "Organization" in types_found
    assert "SoftwareApplication" in types_found
    # Verify Schema.org uses official Avenqo plan nomenclature: Demo, Professional, Enterprise
    sw_app = next(json.loads(s) for s in schema_matches if json.loads(s).get("@type") == "SoftwareApplication")
    offer_names = [o.get("name") for o in sw_app.get("offers", {}).get("offers", [])]
    assert "Demo" in offer_names
    assert "Professional" in offer_names
    assert "Enterprise" in offer_names
    assert "Essentiel" not in offer_names
    assert "Professionnel" not in offer_names
    # Ensure no legacy app.avenqo.ca links
    assert "app.avenqo.ca" not in body


def test_pricing_page_seo():
    code, headers, body = fetch("/pricing")
    assert code == 200
    assert "Tarifs" in body
    assert '<link rel="canonical" href="https://avenqo.ca/pricing"' in body
    assert "Demo" in body
    assert "Professional" in body
    assert "Enterprise" in body
    assert "app.avenqo.ca" not in body


def test_terms_and_privacy_seo():
    for path in ["/terms", "/privacy"]:
        code, headers, body = fetch(path)
        assert code == 200
        assert f'<link rel="canonical" href="https://avenqo.ca{path}"' in body


def test_auth_pages_noindex():
    for path in ["/login", "/register"]:
        code, headers, body = fetch(path)
        assert code == 200
        assert 'name="robots" content="noindex, follow"' in body


def test_private_saas_routes_security_and_noindex_headers():
    for path in ["/dashboard", "/retail", "/admin"]:
        code, headers, body = fetch(path)
        assert code == 200
        x_robots = headers.get("X-Robots-Tag", "")
        assert "noindex" in x_robots
        assert "nofollow" in x_robots
        # Body from Flutter index.html must also have meta robots noindex
        assert 'name="robots" content="noindex, nofollow"' in body


def test_redirect_www_to_apex():
    # Simulate Host: www.avenqo.ca
    code, headers, body = fetch("/", headers={"Host": "www.avenqo.ca"}, follow_redirects=False)
    assert code in (301, 308)
    location = headers.get("Location", "")
    assert location.startswith("https://avenqo.ca")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
