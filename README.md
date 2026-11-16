# Spinny Cost of Ownership Analyser

Paste a [Spinny](https://www.spinny.com) used-car listing link and get the real
2-year cost of owning that car: EMI, maintenance/servicing, roadside
assistance, extended warranty — netted against Spinny's Assured Buyback value.

## How it works

- **`backend/`** — a Flask API that scrapes a Spinny listing page. Spinny
  server-renders the full product record into the page as a minified JS
  object (`window.__INITIAL_STATE__`); the scraper locates the
  `productDetail` block, converts it to valid JSON, and returns price, the
  best-matched loan offer (amount / rate / tenure / EMI), Spinny's own 2-year
  servicing package cost, RSA pricing, extended-warranty tiers, and the
  Assured Buyback figure when Spinny has published one for that specific car.
- **`frontend/`** — a Streamlit dashboard that calls the Flask API, lets you
  tune the assumptions that aren't fixed by the listing (down payment, loan
  tenure, interest rate, which running costs to include, buyback estimate if
  Spinny hasn't published one), and shows a waterfall breakdown of the net
  cost.

## Run it locally

```bash
# backend
cd backend
pip install -r requirements.txt
python app.py            # serves http://localhost:5000

# frontend (separate terminal)
cd frontend
pip install -r requirements.txt
streamlit run app.py     # serves http://localhost:8501
```

The frontend talks to `http://localhost:5000` by default. Override with the
`BACKEND_URL` environment variable or a `.streamlit/secrets.toml` with
`BACKEND_URL = "..."`.

## Deploying

**Backend (Flask) → Render**
1. Push this repo to GitHub.
2. On [Render](https://render.com), "New +" → "Web Service" → pick this repo.
3. Render picks up `backend/render.yaml` automatically (root dir `backend`,
   `gunicorn app:app`). Free plan is fine.
4. Copy the deployed URL (e.g. `https://spinny-analyser-backend.onrender.com`).

**Frontend (Streamlit) → Streamlit Community Cloud**
1. On [share.streamlit.io](https://share.streamlit.io), "New app" → pick this
   repo → set main file path to `frontend/app.py`.
2. In the app's "Secrets", add:
   ```toml
   BACKEND_URL = "https://spinny-analyser-backend.onrender.com"
   ```
3. Deploy. Share the resulting `*.streamlit.app` link with your friend.

Render's free tier sleeps after ~15 minutes idle, so the first scrape after a
while takes a few extra seconds to wake up — that's expected.

## Note on the numbers

Price, Spinny's best-matched EMI/loan offer, 2-year servicing cost, RSA
pricing and extended-warranty tiers are scraped directly from the listing.
Spinny does not publish a per-listing Assured Buyback figure for every car —
when it's missing, the dashboard asks you for your own buyback estimate
instead of guessing one silently.
