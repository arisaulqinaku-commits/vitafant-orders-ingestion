import os
import sqlite3
import sys
import time
from decimal import Decimal, ROUND_HALF_UP

import requests


def load_env_file(path=".env"):
   
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

TOKEN = os.environ.get("ORDERS_API_TOKEN")
API_BASE = os.environ.get("ORDERS_API_BASE", "http://localhost:8080")
API_URL = f"{API_BASE}/admin/api/2026-01/orders.json?limit=250"
DB_FILE = os.environ.get("DB_PATH", "orders.db")

MAX_RETRIES = 8 
SHIPPING_SKU = "SHIP-EXPRESS"


def parse_to_cents(price_val) -> int:
    """Converts money string (e.g. '29.90') safely to integer cents (2990).
    Decimal is used instead of float so we never get rounding errors."""
    if price_val is None:
        return 0
    cents = Decimal(str(price_val)) * 100
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def init_db(conn: sqlite3.Connection):
    """Creates ONE table with one row per line item. line_item_id is the PRIMARY KEY,
    so the same line item can never be stored twice."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS order_line_items (
                line_item_id      INTEGER PRIMARY KEY,
                order_id          INTEGER NOT NULL,
                order_name        TEXT NOT NULL,
                sku               TEXT,
                product_title     TEXT,
                quantity          INTEGER NOT NULL,
                unit_price_cents  INTEGER NOT NULL,
                discount_cents    INTEGER NOT NULL,
                net_revenue_cents INTEGER NOT NULL,
                order_created_at  TEXT NOT NULL,
                country_code      TEXT,
                currency          TEXT,
                financial_status  TEXT
            );
        """)


def get_with_retries(url: str, headers: dict):
    """Does one GET request. If the API says 'too many requests' (429), has a
    server error (5xx) or the network fails, wait and try again (max MAX_RETRIES times).
    Other errors (like 401 wrong token) are our fault, so we stop right away."""
    wait = 1
    for attempt in range(1, MAX_RETRIES + 1):
        sleep_for = wait
        try:
            response = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            print(f"  Network error: {e}")
        else:
            if response.status_code == 200:
                return response

            if response.status_code == 429 or response.status_code >= 500:
                print(f"  Got status {response.status_code}.")
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_for = int(retry_after)  # the API tells us how long to wait
            else:
                raise RuntimeError(f"API returned {response.status_code}: {response.text}")

        if attempt < MAX_RETRIES:
            print(f"  Retrying in {sleep_for} second(s) (attempt {attempt} of {MAX_RETRIES})...")
            time.sleep(sleep_for)
            wait = wait * 2  # wait longer each time: 1, 2, 4, 8 ...

    raise RuntimeError(f"Giving up after {MAX_RETRIES} attempts: {url}")


def fetch_all_orders():
    """Fetches all orders by following the 'next' link until there is none"""
    if not TOKEN:
        raise RuntimeError("ORDERS_API_TOKEN is missing. Copy .env.example to .env first.")

    headers = {"X-Vitafant-Token": TOKEN}  # must be sent with EVERY request
    current_url = API_URL
    all_orders = []
    page = 0

    while current_url:
        page += 1
        print(f"Fetching page {page}...")
        response = get_with_retries(current_url, headers)

        orders = response.json().get("orders", [])
        all_orders.extend(orders)
        print(f"  Received {len(orders)} orders (Total collected: {len(all_orders)})")

        next_link = response.links.get("next")  # no 'next' link = last page
        current_url = next_link["url"] if next_link else None

    return all_orders


def prepare_rows(orders: list):

    rows = []
    cancelled_order_ids = []
    skipped_shipping = 0

    for order in orders:
       
        if order.get("cancelled_at") is not None:
            cancelled_order_ids.append(order.get("id"))
            continue

       
        address = order.get("shipping_address") or {}
        country_code = address.get("country_code")

        for item in order.get("line_items", []):
           
            if item.get("sku") == SHIPPING_SKU:
                skipped_shipping += 1
                continue

            quantity = item.get("quantity", 1)
            unit_price_cents = parse_to_cents(item.get("price"))

          
            discount_cents = 0
            for discount in item.get("discount_allocations", []):
                discount_cents += parse_to_cents(discount.get("amount"))

            
            net_revenue_cents = quantity * unit_price_cents - discount_cents

            rows.append((
                item.get("id"),
                order.get("id"),
                order.get("name"),
                item.get("sku"),
                item.get("title"),
                quantity,
                unit_price_cents,
                discount_cents,
                net_revenue_cents,
                order.get("created_at"),
                country_code,
                order.get("currency"),
                order.get("financial_status"),
            ))

    print(f"Skipped {len(cancelled_order_ids)} cancelled orders and {skipped_shipping} shipping lines.")
    return rows, cancelled_order_ids


def save_rows_to_db(conn: sqlite3.Connection, rows: list, cancelled_order_ids: list):
   
    with conn:
        conn.executemany("""
            INSERT INTO order_line_items (
                line_item_id, order_id, order_name, sku, product_title, quantity,
                unit_price_cents, discount_cents, net_revenue_cents,
                order_created_at, country_code, currency, financial_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(line_item_id) DO UPDATE SET
                order_id=excluded.order_id,
                order_name=excluded.order_name,
                sku=excluded.sku,
                product_title=excluded.product_title,
                quantity=excluded.quantity,
                unit_price_cents=excluded.unit_price_cents,
                discount_cents=excluded.discount_cents,
                net_revenue_cents=excluded.net_revenue_cents,
                order_created_at=excluded.order_created_at,
                country_code=excluded.country_code,
                currency=excluded.currency,
                financial_status=excluded.financial_status;
        """, rows)

        # An order that was cancelled AFTER an earlier run must disappear from the table
        conn.executemany(
            "DELETE FROM order_line_items WHERE order_id = ?",
            [(order_id,) for order_id in cancelled_order_ids],
        )


def main():
    # 1. Get the data first. If this fails we stop BEFORE touching the database.
    print("Fetching orders from API...")
    orders = fetch_all_orders()
    print(f"Fetched {len(orders)} orders.")


    rows, cancelled_order_ids = prepare_rows(orders)

  
    db_folder = os.path.dirname(DB_FILE)
    if db_folder:
        os.makedirs(db_folder, exist_ok=True)  # e.g. /data when running in Docker

    conn = sqlite3.connect(DB_FILE)
    init_db(conn)
    print(f"Saving {len(rows)} line items to database...")
    save_rows_to_db(conn, rows, cancelled_order_ids)

   
    cursor = conn.cursor()
    row_count, units, net_cents = cursor.execute(
        "SELECT COUNT(*), SUM(quantity), SUM(net_revenue_cents) FROM order_line_items"
    ).fetchone()

    print("\nDatabase sync complete!")
    print(f"Rows in DB: {row_count}")
    print(f"Units sold: {units}")
    print(f"Net revenue: {net_cents / 100:,.2f}")

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)  # non-zero exit code = the job failed
