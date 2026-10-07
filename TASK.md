# Vitafant — Take-Home Task

**Role:** Junior Software Developer, Tech & Systems
**Time budget:** 2–3 hours. This is paid — please note your actual hours when you submit.
**Deadline:** agreed individually.

---

## Context

Vitafant is a direct-to-consumer brand selling across several European markets.
Our analytics stack runs on scheduled jobs that pull data out of operational APIs and land it
in a warehouse, where marketing and finance query it.

You are going to build a small version of exactly that: **one job that pulls orders from an API,
turns them into clean line-item revenue records, and loads them into a database.**

The API in this repo is a stand-in for our Shopify Admin API. It behaves like the real thing,
including the annoying parts.

---

## What you get

```
vf-hiring-task/
├── docker-compose.yml
├── .env.example
└── mock-api/          ← don't modify this
```

Start it:

```bash
docker compose up
curl http://localhost:8080/health
```

No Docker? Fallback:

```bash
cd mock-api && pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

### The endpoint

```
GET /admin/api/2026-01/orders.json?limit=250&page_info=<cursor>
Header: X-Vitafant-Token: <token>
```

- Auth token is in `.env.example`. **Treat it as a real secret.**
- `limit` maxes out at 250.
- Pagination is cursor-based. The response carries a `Link` header:
  `<...?limit=250&page_info=abc>; rel="next"`. No header means you're done.
- The API rate-limits and occasionally throws 5xx. This is intentional. Handle it.

### Response shape (abridged)

```json
{
  "orders": [{
    "id": 5000123,
    "name": "#VF100123",
    "created_at": "2026-05-14T09:23:11+02:00",
    "cancelled_at": null,
    "financial_status": "paid",
    "currency": "EUR",
    "shipping_address": { "country_code": "DE" },
    "line_items": [{
      "id": 900001234,
      "sku": "VF-MAG-120",
      "title": "Magnesium Komplex 120 Kapseln",
      "quantity": 2,
      "price": "29.90",
      "discount_allocations": [{ "amount": "5.98", "discount_application_index": 0 }]
    }]
  }]
}
```

---

## What to build

### 1. An ingestion job

A Python program that reads every order from the API and writes one row **per line item** into a
SQLite database (file on disk, your choice of name).

Required columns — name them as you like, but all of these must be there:

| Field | Notes |
|---|---|
| line item id | |
| order id | |
| order name | e.g. `#VF100123` |
| sku | |
| product title | |
| quantity | |
| unit price | |
| discount amount | total discount allocated to that line item |
| net revenue | see rule below |
| order created at | |
| country code | from the shipping address |

### 2. Business rules

- **Net revenue** per line item = `quantity × unit price − discount allocations`.
- **Cancelled orders** (`cancelled_at` is not null) are excluded entirely. They are not revenue.
- **SKU `SHIP-EXPRESS`** ("Schneller Versand") is a shipping charge, not a product.
  It must not appear in the output table.
- Money arrives as strings. Handle it so that sums are correct.

### 3. Re-runnability

The job will eventually run on a schedule. **Running it twice must not corrupt the table** —
no duplicated rows, no doubled revenue. How you achieve that is up to you.
Say in your README what you did and why.

### 4. A SQL query

A separate `.sql` file that answers: **net revenue and units sold per product for a given month,
ranked by revenue.** It should run against your table as-is.

### 5. A Dockerfile

For your job, not for the mock API. It should build and run without me installing Python.

### 6. A README

Short. Please cover:

- how to run it (assume I have Docker and nothing else)
- what you'd have done differently with more time, or what you know is weak
- **Deployment question, written answer, ~10 lines:** our production version of this job would run
  on **Google Cloud Run** on a schedule and load into **BigQuery** instead of SQLite. You haven't
  worked with either. Describe how you'd approach it: what you'd need to find out, what you think
  changes structurally, and where you'd expect to get stuck. Researching the docs is fine and
  expected. Guessing honestly is better than pretending.

---

## Ground rules

- **Python.** Any libraries you want.
- **AI tools are allowed** — we use them too. But you own every line: if I ask why something is
  written the way it is, "the model wrote it" is not an answer. Note in the README where you used
  them and what you changed.
- **Don't modify `mock-api/`.** If you think it's broken, tell me instead.
- **Don't build a UI, a web server, tests for everything, or a config framework.** Scope creep
  costs you points, not gains them. If you're past 3 hours, stop and write down what's missing.

---

## Self-check

If your ingestion is correct, the API serves **3,847 orders** in total.
The other numbers you should be able to derive yourself — that's part of the task.

---

## Submitting

A git repo (GitHub link or a zip with the `.git` folder) containing your code, the `.sql` file,
the Dockerfile and the README. Commit history is welcome — I'd rather see how you got there than
one commit called "final".

If something is ambiguous, make a decision, write it down in the README, and move on.
Deciding under uncertainty is part of what we're looking at.
