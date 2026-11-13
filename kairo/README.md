# Kairo — why is this stock moving?

Pick a US stock and Kairo tells you, in a couple of seconds, the most likely reasons
it's moving: company news, competitors and suppliers, its sector, the economy and
geopolitics. Each reason gets a likelihood and links to the headlines behind it.

The name comes from the Greek *kairos*, "the decisive moment".

Built for the Sea x OpenAI Codex Hackathon, Kuala Lumpur (5 Dec 2026).

![Kairo screenshot](docs/screenshot.png)

## How it works

1. **Live prices**: with a Finnhub key, every trade streams in over a WebSocket within
   milliseconds; without one, Kairo polls Yahoo Finance every 2 seconds. One shared feed
   serves all open screens (`backend/app/live.py`).
2. **Market context**: the stock, the S&P 500 (SPY) and its sector ETF, so a stock-specific
   move is separated from the whole market moving.
3. **News in five groups**: company, peers & supply chain, sector, economy, geopolitics
   (`backend/app/universe.py` lists what each stock is connected to). Off-topic stories are
   filtered out and well-known outlets are preferred.
4. **Price reaction per headline**: how the stock moved in the ~30 minutes right after each
   headline (a mini event study). This gives the AI timing evidence, not just text.
5. **AI ranking**: an OpenAI model ranks the likely reasons, with likelihoods that add up to
   100% (including "not explained by the news"), citing the headlines it used.
6. **Answers ready in advance**: a background loop keeps every listed stock's answer fresh
   and only asks the AI again when something changes (a new company headline or a real price
   move). Clicking a stock returns its answer in about a millisecond
   (`backend/app/service.py`).

7. **Ask Kairo**: follow-up questions about the current stock, answered by the AI from the
   same prices and headlines, with headline citations (`backend/app/analyzer/chat.py`).
8. **Alerts**: when a watchlist stock moves 1% within 15 minutes, or crosses 3/5/7/10% on the
   day, Kairo pops up an alert with the likely reason (`backend/app/alerts.py`).

If OpenAI is unavailable or rate-limited, Kairo pauses AI calls for a while and shows a simpler
offline analysis instead, then switches back automatically.

## Run it

You need Python 3.11+ and Node 18+.

```bash
# Backend
cd backend
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then paste your keys into .env (see below)
../.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                   # open http://localhost:5173
```

No keys yet? Set `DATA_MODE=sample` in `backend/.env`. The app then runs fully offline on
**synthetic sample data**, clearly marked with a yellow banner. Use it for development
only, never as real market information.

Single server for demos: run `npm run build` in `frontend/`, and the backend serves the
app at http://localhost:8000.

Tests: `cd backend && ../.venv/bin/python -m pytest`

Phone demo without a server: `scripts/export_static_demo.py OUT_DIR --live` saves a snapshot of
real data, and `VITE_STATIC=1 npx vite build --base ./` builds a version of the app that reads it.

## Put it online

The `Dockerfile` builds everything into one container that any Docker host can run. On
[Render](https://render.com), for example:

1. Give Kairo its own GitHub repo (or point Render at the `kairo` folder of this one).
2. Render: **New → Web Service**, connect the repo, choose **Docker** as the runtime.
3. Under **Environment**, add `OPENAI_API_KEY` and `FINNHUB_API_KEY`. Never put keys in the code.
4. Create the service. Render gives you a public `https://….onrender.com` link.

Free hosting plans usually sleep when nobody visits, so the first visit is slow and background
pre-computing pauses. For the demo, use a plan that stays awake.

Test the container locally: `docker build -t kairo . && docker run -p 8000:8000 --env-file backend/.env kairo`

## Getting the API keys

| Key | Where | Cost |
| --- | --- | --- |
| `OPENAI_API_KEY` | platform.openai.com → sign in → **Settings → Billing** (add credit) → **API keys → Create new secret key** | Pay as you go. Without credits: 50 requests a day, which background pre-computing uses up fast (set `WARM_WATCHLIST=false` until you add credits) |
| `TIINGO_API_KEY` | tiingo.com → account → **API → Token** | Free tier for prices (low request limits); news needs Tiingo's News API plan |
| `FINNHUB_API_KEY` | finnhub.io/register → the key is on your dashboard | Free tier: live trade stream + 60 requests/min |

Paste them into `backend/.env`. Never commit that file (it's in `.gitignore`) and never
share keys in chat. OpenAI's terms have age rules, so have a team member who is 18+ own
the account and billing.

Google News and Yahoo Finance need no key.

## Before selling it

The free data sources here are fine for a prototype and a demo, but not for a paid
product:

- **Market data**: Yahoo's chart endpoint is unofficial. Switch to a licensed feed
  (e.g. Polygon, Alpaca, Databento).
- **News**: use a licensed real-time feed (e.g. Benzinga, Finnhub paid) for speed and
  redistribution rights.
- **Positioning**: Kairo explains moves; it does not give buy/sell advice. Keep it
  that way unless you get proper regulatory advice.
- **Calibration**: check that "70% likely" reasons are right about 70% of the time, by
  replaying past moves where the cause is known.

## Project layout

```
backend/app/
  main.py               API: /api/stream/{ticker}, /api/ticks, /api/ask/{ticker}, /api/alerts
  alerts.py             sharp-move detection and alert feed
  live.py               live price feed (Finnhub WebSocket, Yahoo polling fallback)
  service.py            pre-computed answers, re-analysis only when something changes
  context.py            gathers prices + news in parallel, price reactions, cache
  universe.py           what each stock is connected to
  providers/            prices (Yahoo), news (Finnhub, Google News, Yahoo RSS), sample data
  analyzer/             OpenAI analyzer, Ask Kairo chat, offline fallback, engine that picks one
frontend/src/
  App.tsx               layout, ticker search, streaming
  api.ts, useTicks.ts   server calls, live price hook
  components/           Verdict, AskKairo, Alerts, PriceChart, Watchlist, TickerTape, NewsFeed, Search
```

*Explains likely reasons for past price moves from public news. Not investment advice.*
