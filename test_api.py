"""Praxya API smoke test — run from repo root."""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"

def get(path):
    r = urllib.request.urlopen(BASE + path)
    return json.loads(r.read())

def main():
    print("=" * 60)
    print("STEP 1 — Health check")
    print("=" * 60)
    try:
        h = get("/health")
        print(f"  status:  {h['status']}")
        print(f"  db:      {h['db']}")
        print(f"  factors: {h['emission_factors_loaded']}")
        ok = h["status"] == "ok"
        print(f"  RESULT:  {'PASS' if ok else 'FAIL'}")
    except Exception as e:
        print(f"  FAIL — {e}")
        print("  Is uvicorn running on port 8000?")
        return

    print()
    print("=" * 60)
    print("STEP 1b — OpenAPI route groups")
    print("=" * 60)
    try:
        api = get("/openapi.json")
        routes = sorted(api["paths"].keys())
        for p in routes:
            m = list(api["paths"][p].keys())[0].upper()
            print(f"  {m:6s} {p}")
        groups = {"/api/ingest": False, "/api/emissions": False,
                  "/api/reports": False, "/api/admin": False}
        for p in routes:
            for g in groups:
                if p.startswith(g):
                    groups[g] = True
        print()
        for g, ok in groups.items():
            print(f"  {'PASS' if ok else 'FAIL'} — {g}")
    except Exception as e:
        print(f"  FAIL — {e}")

    print()
    print("=" * 60)
    print("STEP 3 — Emissions summary (expects 422 — needs auth)")
    print("=" * 60)
    rp = "b0000001-5eed-0000-0000-000000000001"
    fac = "f0000001-5eed-0000-0000-000000000001"
    url = f"{BASE}/api/emissions/summary?reporting_period_id={rp}&facility_id={fac}"
    try:
        r = urllib.request.urlopen(url)
        print(f"  Response: {r.read().decode()[:300]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  HTTP {e.code}: {body}")
        if e.code in (401, 422):
            print("  PASS — endpoint exists, auth required as expected")
        else:
            print("  WARN — unexpected status code")
    except Exception as e:
        print(f"  FAIL — {e}")

    print()
    print("Done. Check results above.")

if __name__ == "__main__":
    main()
