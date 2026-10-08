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

## What I know is weak(ish)
- No automated tests.
- Fetches all orders on every run instead of only changed ones.
- Refund amounts are not available, so refunds are not subtracted.
- A line item removed from a non-cancelled order after the first load stays in
  the table.
- Logging is plain `print`.

## With more time
- weak points in order of priority i guess

## AI usage
First ingest.py	I wrote it: fetch, pagination, retries, SQLite upsert
Final ingest.py	Claude extended and rewrote it to meet the task's rules; I tested it and checked the numbers until i felt it was right

SQL query, Dockerfile, .dockerignore and a summary/structure for this README made with AI tools, run, verified and selected by me

the Dockerfile among other things that I had never encountered the requirement for it to run without you needing to have python installed so I used Claude and a few other tools to explain how it would work and write a couple of versions for this code(of which i chose the one currently in the task)


Other than the more concrete use I was using AI and online resources like quora, geeks4geeks, reddit and other such forums for my questions and concerns with the code, API and Desktop Docker

## AI usage
- **First `ingest.py`:** I wrote it myself (fetch, pagination, retries, SQLite upsert).
- **Final `ingest.py`:** Claude extended and rewrote it to meet the task's rules
  (flat table, filtering, discounts, capped retries, built-in .env loader). I ran it,
  tested re-runs, and checked the output against [what you really did].
- **SQL query, Dockerfile, .dockerignore, README structure:** written with Claude;
  I ran, verified and debugged them.

- **Explanations/troubleshooting:** Claude explained Docker, Git, Python and SQL
  concepts and helped debug errors. I also used GeeksforGeeks, Reddit and Quora.
## Hours
- Task work: 2h 42min
- - Learning before/during (Docker, Git, SQL, API basics): 5h 57min

## Deployment question: Cloud Run + BigQuery
- orders.db would disappear the moment the job is done because cloudrun's container has temporary memory disks and then the db exists in a BigQuery table in an EU data set. ingest.py would be changed: sqlite3 replaced by google's bigquery python library. rows are placed in a staging table and then merged into the real one which upserts the information and drops cancelled orders.

- the entire job runs as a service account with just the permissions it needs and I believe google's library picks those up without needing a password on the code. The token gets put in secret manager and is read as an environment variable that just means it's one less thing we need to change from the original code as it still works the same.

- For production, I'd push the Docker image to Artifact Registry and run it as a Cloud Run job, which is a great fit since the script just runs once and exits. I'd set up Cloud Scheduler to trigger it automatically on a cron schedule, like every night. I'd also make sure Scheduler has the right IAM permissions to run the job, configure timeouts and retries, and set up alerts to flag any non-zero exit code as a failure.

- carrying this task over I think my difficulties would lie in safe testing and permissions and authentication. I'd want a separate dev dataset, so a bug can't overwrite real data and unlike simpler platforms, Google Cloud IAM roles map directly to specific API actions.

- as for what i think would be difficult in **production** for this task specifically is that the order numbers of course are not up to scale for future expansion. Now it's 3847, next year it could be 1000 times more and this could cause slowness and other costly issues, my cap for retries is 8 attempts(1 try and 7 retries), but with so many requests another issue arises, and that is how the task just quits quietly with no alerts(although there is an error message in the logs if you check) or anything(which is especially bad given that every 429 or 5xx error have a high percentage rate of happening due to the APIs behaviour. The code stops before loading anything, so one page that fails all 8 attempts means that whole run loads nothing). There are fixes for this of course such as only loading new orders since the last run of the ingest and not the entire history of orders every time.
