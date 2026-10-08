# Orders Ingestion Job

Reads every order from the (mock) Shopify Admin API, turns them into one row
per line item with net revenue, and loads them into SQLite. Safe to rerun.

## How to run (Docker only)

1. Start the mock API:
```
   docker compose up -d --build
```
2. Create your local config file (it is git-ignored, so the token stays secret):
```
   cp .env.example .env          # PowerShell: copy .env.example .env
```
3. Build and run the job:
```
   docker build -t vf-ingest .
   docker run --rm --env-file .env -e ORDERS_API_BASE=http://host.docker.internal:8080 --add-host=host.docker.internal:host-gateway -v "$(pwd)/data:/data" vf-ingest
```
   PowerShell: use `"${PWD}/data:/data"`.
   Inside the container `localhost` is the container itself, so the job
   reaches the API on the host through `host.docker.internal`.
4. The database is `data/orders.db`, table `order_line_items`. Run
   `queries/monthly_product_revenue.sql` in any SQLite tool; change the month
   on its first line.

Expected output: 3,847 orders fetched, 116 cancelled, 1,297 shipping lines
skipped, 7,450 rows loaded, 12,107 units, net revenue 290,728.70.
Running it a second time gives identical numbers.

## What the job does
- Follows the `Link` header until there is no `next` page (limit=250, 16 pages).
- Retries 429, 5xx and network errors: max 8 attempts, doubling wait, uses
  `Retry-After`. 400/401/404 stop immediately. If a page cannot be fetched
  the job exits with code 1 BEFORE touching the database, so the table can
  never be loaded with partial data.
- Skips cancelled orders and the `SHIP-EXPRESS` line.
- Net revenue = quantity x unit price - discount allocations, in integer cents.

## Decisions
- *Money*-> is stored as integer cents (`2990` = 29.90 EUR). Decimal is used to
  parse the API strings; floats are never used, so sums are exact.
- *Re-runnable*-> upsert on `line_item_id` (primary key),+ deletion of the
  rows of orders that are cancelled, all in 1 transaction. A crash leaves the
  table as it was.
- *Refunded / partially refunded orders are included*-> because the task only
  excludes cancelled orders and the API gives no refund amounts. The
  `financial_status` column makes them visible.
- *"Month"*-> is the local date as written in the data (+02:00) . The SQL uses
  `substr(order_created_at, 1, 7)` on purpose: SQLite's `strftime` converts to
  UTC first and could move an order near midnight into another month.
- *Config* comes from environment variables / a `.env` file (small built-in
  loader, no extra dependency). The token is never in the code or the image.

## With more time
1. Alerting on failed runs, and structured logging instead of `print`.
2. Incremental loads: only fetch orders changed since the last run.
3. Automated tests for the net-revenue calculation and the filtering rules.
4. Handle refunds properly (needs refund data the API doesn't provide here).

## AI usage
- **First `ingest.py`:** I wrote it myself (fetch, pagination, retries, SQLite upsert).
- **Final `ingest.py`:** Claude extended and rewrote it to meet the task's rules
  (flat table, filtering, discounts, capped retries, built-in .env loader). I ran it,
  tested re-runs, and checked the output against the expected values and functions.
- **SQL query, Dockerfile, .dockerignore, README structure:** written with Claude;
  I ran, verified and debugged them. README shortened by claude after it was handwritten by me.
- **Cloud answer:** I drafted it myself; Claude suggested the staging-table/MERGE approach and helped polish the wording.
- **Explanations/troubleshooting:** Claude explained Docker, Git, Python and SQL
  concepts and helped debug errors. I also used GeeksforGeeks, Reddit and Quora.

## Hours
- Task work: 2h 42min
- Learning before/during (Docker, Git, SQL, API basics): 5h 57min

## Deployment question: Cloud Run + BigQuery

I haven't used Cloud Run or BigQuery, so parts of this are educated guesses.

- **Storage:** `orders.db` would disappear when the job ends, because a Cloud Run container has a temporary filesystem. The data would live in a BigQuery table in an EU dataset, and `sqlite3` in `ingest.py` would be replaced by Google's BigQuery Python library. My guess is to load rows into a staging table and `MERGE` them into the real one, which does the upsert and drops cancelled orders (I'd verify this in the docs).
- **Access:** the job would run as a service account with only the permissions it needs. I believe Google's library picks those up without a password in the code. The token would go into Secret Manager and be read as an environment variable, so that part of `ingest.py` stays the same.
- **Running it:** my understanding is that I'd push the image built from my Dockerfile to Artifact Registry and run it as a Cloud Run *job*, which fits a script that runs once and exits. Cloud Scheduler would trigger it on a cron schedule (for example nightly). I'd look up the Scheduler permissions, timeouts and retries, and I'd expect to alert on a non-zero exit code.
- **Where I'd get stuck:** permissions and authentication, and testing safely. I'd want a separate dev dataset so a bug can't overwrite real data.
- **Production risk:** 3,847 orders now could be 1000 times more next year, so fetching the full history every run would become slow and costly. Roughly one request in four fails (429 or 5xx) and I make 8 attempts per page (1 try and 7 retries). With many more pages, the chance that one page fails all 8 attempts grows, and then the whole run loads nothing. The job logs an error, but nothing alerts anyone. A fix for the scale problem is to load only orders changed since the last run instead of the full history.





