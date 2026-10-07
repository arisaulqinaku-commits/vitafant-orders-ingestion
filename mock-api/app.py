"""
Vitafant Hiring Task - Mock Orders API

A deliberately imperfect, Shopify-like orders endpoint.
Deterministic dataset (seeded), non-deterministic failures (rate limits, 5xx).

Run:
    docker compose up          # preferred
    uvicorn app:app --port 8080 --host 0.0.0.0   # fallback
"""
import base64
import os
import random
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

API_TOKEN = os.environ.get("ORDERS_API_TOKEN", "vf_demo_a7f3d91c4b8e")
PAGE_MAX = 250
TOTAL_ORDERS = 3847
RATE_LIMIT_PROB = float(os.environ.get("RATE_LIMIT_PROB", "0.20"))
SERVER_ERROR_PROB = float(os.environ.get("SERVER_ERROR_PROB", "0.05"))

app = FastAPI(title="Vitafant Mock Orders API", docs_url=None, redoc_url=None)

CATALOG = [
    ("VF-D3K2-90",   "Vitamin D3 + K2 Tropfen",        24.90),
    ("VF-MAG-120",   "Magnesium Komplex 120 Kapseln",  29.90),
    ("VF-OM3-60",    "Omega-3 Algenöl",                34.90),
    ("VF-ZNK-100",   "Zink + Selen",                   16.90),
    ("VF-KOL-300",   "Kollagen Pulver Vanille",        39.90),
    ("VF-ASH-90",    "Ashwagandha KSM-66",             27.90),
    ("VF-B12-50",    "Vitamin B12 Tropfen",            14.90),
    ("VF-FE-60",     "Eisen + Vitamin C",              19.90),
    ("VF-PRO-30",    "Probiotika 20 Mrd. KBE",         32.90),
    ("VF-KUR-90",    "Kurkuma Extrakt + Piperin",      22.90),
    ("VF-BIO-120",   "Biotin Haar & Nägel",            18.90),
    ("VF-MUL-90",    "Multivitamin Daily",             26.90),
]

SHIPPING_SKU = ("SHIP-EXPRESS", "Schneller Versand", 4.90)

COUNTRIES = ["DE"] * 62 + ["AT"] * 26 + ["IT"] * 12
FIN_STATUS = ["paid"] * 88 + ["partially_refunded"] * 7 + ["refunded"] * 5

START = datetime(2026, 5, 1, tzinfo=timezone(timedelta(hours=2)))
WINDOW_DAYS = 92


def _money(value: float) -> str:
    """Shopify returns money as strings. So do we."""
    return f"{value:.2f}"


def _build_dataset():
    rng = random.Random(20260821)
    orders = []
    line_item_id = 900000000
    for i in range(TOTAL_ORDERS):
        order_id = 5000000 + i
        created = START + timedelta(
            days=rng.randint(0, WINDOW_DAYS - 1),
            hours=rng.randint(6, 22),
            minutes=rng.randint(0, 59),
            seconds=rng.randint(0, 59),
        )
        cancelled = rng.random() < 0.031
        items = []
        for _ in range(rng.choice([1, 1, 1, 2, 2, 3, 4])):
            sku, title, base = rng.choice(CATALOG)
            qty = rng.choice([1, 1, 1, 2, 3])
            unit = round(base * rng.choice([1.0, 1.0, 1.0, 0.9]), 2)
            gross = unit * qty
            disc = round(gross * rng.choice([0.0, 0.0, 0.0, 0.10, 0.15]), 2)
            line_item_id += 1
            items.append({
                "id": line_item_id,
                "sku": sku,
                "title": title,
                "quantity": qty,
                "price": _money(unit),
                "discount_allocations": (
                    [{"amount": _money(disc), "discount_application_index": 0}] if disc else []
                ),
            })
        if rng.random() < 0.34:
            line_item_id += 1
            items.append({
                "id": line_item_id,
                "sku": SHIPPING_SKU[0],
                "title": SHIPPING_SKU[1],
                "quantity": 1,
                "price": _money(SHIPPING_SKU[2]),
                "discount_allocations": [],
            })
        orders.append({
            "id": order_id,
            "name": f"#VF{100000 + i}",
            "created_at": created.isoformat(),
            "updated_at": (created + timedelta(minutes=rng.randint(1, 4000))).isoformat(),
            "cancelled_at": (created + timedelta(hours=rng.randint(2, 72))).isoformat()
            if cancelled else None,
            "financial_status": "voided" if cancelled else rng.choice(FIN_STATUS),
            "currency": "EUR",
            "shipping_address": {"country_code": rng.choice(COUNTRIES)},
            "line_items": items,
        })
    orders.sort(key=lambda o: o["created_at"])
    return orders


ORDERS = _build_dataset()


def _encode(offset: int) -> str:
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode().rstrip("=")


def _decode(cursor: str) -> int:
    pad = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad).decode()
        return int(raw.split(":", 1)[1])
    except Exception:
        return -1


@app.get("/health")
def health():
    return {"status": "ok", "orders": len(ORDERS)}


@app.get("/admin/api/2026-01/orders.json")
def list_orders(
    request: Request,
    limit: int = 50,
    page_info: str | None = None,
    x_vitafant_token: str | None = Header(default=None),
):
    if x_vitafant_token != API_TOKEN:
        return JSONResponse({"errors": "Invalid API token"}, status_code=401)

    roll = random.random()
    if roll < RATE_LIMIT_PROB:
        return JSONResponse(
            {"errors": "Exceeded 2 calls per second for api client."},
            status_code=429,
            headers={"Retry-After": "1"},
        )
    if roll < RATE_LIMIT_PROB + SERVER_ERROR_PROB:
        return JSONResponse({"errors": "Internal server error"}, status_code=500)

    if limit < 1 or limit > PAGE_MAX:
        return JSONResponse(
            {"errors": f"limit must be between 1 and {PAGE_MAX}"}, status_code=400
        )

    offset = 0
    if page_info:
        offset = _decode(page_info)
        if offset < 0:
            return JSONResponse({"errors": "Invalid page_info"}, status_code=400)

    page = ORDERS[offset:offset + limit]
    headers = {}
    nxt = offset + limit
    if nxt < len(ORDERS):
        url = f"{request.base_url}admin/api/2026-01/orders.json?limit={limit}&page_info={_encode(nxt)}"
        headers["Link"] = f'<{url}>; rel="next"'
    return JSONResponse({"orders": page}, headers=headers)
