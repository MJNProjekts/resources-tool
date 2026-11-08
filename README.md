# RESOURCES Tool

**English** · [Latviešu](README.lv.md)

A local data collector, Telegram alerts and a web dashboard for the
location-based economy game [RESOURCES](https://www.resources-game.ch),
built on the game's official data API.

> **About this project**
> - This is a **learning project**: I build it to learn Python, SQLite and small
>   web apps, and to play the game a bit smarter.
> - It is meant to run **only on your own computer**. There is no server, no
>   login and no cloud: your API key and game data stay on your machine.
> - It is **unofficial** and not affiliated with or endorsed by the game's developer.
> - Every API query costs **API credits** that you buy in the game. Read the
>   credit section below before running it.
> - Numbers are estimates based on the API data and formulas measured in the
>   game. Check them before making big decisions in the game.

## What it does

**Collector** (`collector.py`) fetches your data on a schedule, keeps a history
in a local SQLite database and sends Telegram alerts:

| | |
|---|---|
| 🚨 New item | A game update added a resource or product. Early prices are often far higher than later |
| 📦 Warehouse | Full in less than 6 h, with advice: sell to a player buyer above the KI-market price, or to the KI-market |
| 🏷 Buyers above KI-market | The most profitable player buy requests, each announced once |
| 💰 KI-market price rise | KI-market price clearly above its 7-day average |
| 🎯 Missions opened | The exact opening time is known from the mission timer, no extra queries |
| ⏰ Mission deadline | A mission ends soon with its goal not reached (shows the penalty) |
| 🔧 Maintenance | Mines below a set condition and not maintained, linked to the Maintenance mission |
| 📊 Daily report | Points and rank change, money, warehouse value, mine condition, missions opening soon |

**Dashboard** (`python -m web.app`) shows your current state in LV or EN:
key numbers, a "to do now" list, warehouse (fill, time to full, buyer price),
a mines map with coverage of factory needs, factory profit with real load,
investment payback (factory upgrades, Tech Upgrades on mines), recycling value,
special building upgrade progress, missions, money and open achievements.

*KI-market price* is the game's own name for the price the computer market pays.

## API credits

Each query except the credit check costs one credit. The collector asks only
as often as the data changes, about **19 credits per day**:

| How often | Queries |
|---|---|
| every 6 h | warehouses, market, missions |
| daily | player, factories, special buildings, money, trade log |
| weekly | recipes, upgrade costs, recycling, troops, HQ, achievements |
| on demand | mines: when the predicted mine condition reaches the check level (+ weekly) |
| on demand | item list: when an unknown item appears (+ monthly) |

Safety limits: a daily credit budget, a stop below a minimum number of credits,
and no automatic retries. The dashboard spends credits only with the
"Refresh warehouse" button (at most once per 5 minutes).

## Setup

You need Python 3.10+ and an API key from the game.

```bash
git clone <this repo>
cd resources-tool
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # put your API key (and Telegram bot) in .env
```

Telegram is optional: without a token, messages are printed in the terminal.

## Usage

```bash
python collector.py --status       # what is due, credits used (0 credits)
python collector.py --once         # fetch what is due now
python collector.py                # run forever (keep the window open)
python collector.py --fetch 2      # fetch one query now (1 credit)
python collector.py --report       # send the daily report now (0 credits)

python -m web.app                  # dashboard at http://127.0.0.1:8050
```

## Security notes

- `.env` (API key, Telegram token), the database and any downloaded samples are
  in `.gitignore`. **Never commit them.** Your database contains your game history.
- The dashboard listens only on `127.0.0.1` (this computer) by default.
- `python -m web.app --lan` makes it reachable from your phone on the same Wi-Fi.
  There is no login, so use it only on a trusted network. In LAN mode the
  credit-spending refresh button works only on the computer itself, unless you
  also pass `--lan-refresh`.
- The refresh endpoint requires a custom header, so other websites cannot make
  your browser spend credits.
- Error messages never contain the API key.

## Game formulas found so far

Measured in the game and checked against real upgrade costs:

- Warehouse capacity = **5000 × level²**
- Factory output per hour = **level × base output**
- Factory and special building upgrade cost = **base cost × (target level)²**, items too
- Recycling output = **API base amount × Recycling Plant level**
- Mine condition drops about **3.5–4 % per day** (refined automatically)
- Buying on the market adds about **9 % transport** (paid by the buyer)
- The API has no unique mine ID: `mineID` is the mine *type*, so mines are keyed by coordinates

## Project layout

```
collector.py          scheduler, fetching, alert dispatch
probe.py              fetch single queries to inspect their structure
rgtool/api.py         API client (no retries: retries cost credits)
rgtool/schema.sql     database schema (reference / state / history)
rgtool/db.py          stores every API answer
rgtool/maintenance.py mine condition forecast
rgtool/alerts.py      alerts and daily report
rgtool/i18n.py        Telegram texts (en, lv)
web/data.py           dashboard numbers (production model, payback)
web/app.py            Flask server
web/static/           the page (vanilla JS, Leaflet map, SVG charts, i18n.js)
```

## License

MIT, see [LICENSE](LICENSE).
