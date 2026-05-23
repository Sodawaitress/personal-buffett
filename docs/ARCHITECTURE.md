# PBC Refactor Architecture

This branch now uses a modular monolith layout:

- one repo
- one Flask app factory
- feature modules under `radar_app/<feature>/`
- data modules under `radar_app/data/`
- thin routes
- data access in `query.py`
- template/API shaping in `presenter.py`
- orchestration in `service.py`
- legacy script calls isolated behind `radar_app/legacy/`
- large script files split by responsibility instead of many tiny fragments

## Current layout

```text
run.py                         # dev entrypoint
app.py                         # compatibility shim
db.py                          # compatibility shim over radar_app.data
radar_app/
  __init__.py                  # app factory + runtime prep
  settings.py                  # secret/debug/port settings
  extensions.py                # bcrypt / oauth init
  context.py                   # context processors
  routes.py                    # register all feature routes

  data/
    core.py                    # sqlite path / connection / init / migrate
    users.py                   # users + push settings
    stocks.py                  # stock master + watchlist + prices
    market.py                  # news / fund flow / fundamentals / market data
    analysis.py                # analysis / reports / events / accuracy
    jobs.py                    # pipeline_jobs table helpers
    portfolio.py               # portfolio brief helpers
    notifications.py           # poor-rating notifications

  shared/
    auth.py                    # login_required
    i18n.py                    # string loading
    jobs.py                    # pending job lookup
    market.py                  # market helpers
    metric_hints.py            # human-readable financial hints
    runtime.py                 # CN_TZ and runtime values
    startup.py                 # db init / migrate helper

  legacy/
    pipeline.py                # wrappers around scripts.pipeline / classifier
    search_backend.py          # wrappers around stock_search
    market_data.py             # wrappers around nz_fetch / macro_fetch / nz_profiles
    portfolio.py               # wrapper around portfolio_brief

  auth/
    routes.py
    service.py

  admin/
    routes.py
    service.py

  dashboard/
    routes.py
    service.py
    query.py
    presenter.py

  portfolio/
    routes.py
    service.py

  public/
    routes.py
    service.py

  search/
    routes.py
    service.py

  watchlist/
    routes.py
    service.py
    query.py
    presenter.py

  stocks/
    routes.py
    service.py
    action_service.py
    query.py
    presenter.py

  system/
    routes.py
    service.py

scripts/
  pipeline.py                  # compatibility entrypoint only
  pipeline_fetch.py            # single-stock fetch steps
  pipeline_analysis.py         # layer2/layer3 analysis helpers
  pipeline_jobs.py             # job orchestration + cache checks

  buffett_analyst.py           # public analysis entrypoints
  buffett_prompts.py           # framework prompts
  buffett_groq.py              # Groq client
  buffett_signals.py           # news signal scoring
  buffett_utils.py             # output parsing helpers
  buffett_context.py           # prompt context assembly

  stock_fetch.py               # market/news fetch orchestration
  stock_fetch_financials.py    # A-share financial/signal fetchers
  stock_pipeline.py            # daily pipeline orchestration
  stock_report.py              # markdown / push content builders
```

## Rules

1. All new HTTP endpoints go through `radar_app/<feature>/routes.py`.
2. Route handlers should stay thin: request in, response out.
3. Cross-feature helpers belong in `radar_app/shared/`.
4. Any call into old top-level script modules should go through `radar_app/legacy/`.
5. `app.py` stays only as a compatibility export for older imports and tests.
6. `run.py` and `radar_app.create_app()` are the real entrypoints.

## Refactor status

Done:

- `app.py` is reduced to a compatibility shim
- `db.py` is reduced to a compatibility shim
- all web routes are registered from `radar_app`
- `watchlist`, `stocks`, and `dashboard` have route/query/presenter/service splits
- `portfolio`, `public`, and `search` have dedicated service layers
- direct legacy script imports inside feature modules were moved behind `radar_app/legacy/`
- app bootstrap was split into settings/extensions/context/routes helpers
- data access was split out of the old `db.py` monolith into `radar_app/data/`
- the biggest script files now have explicit boundaries for pipeline, Buffett analysis, stock fetch, and stock report assembly

Still intentionally left in place:

- top-level script modules under `scripts/` still contain their own path/setup assumptions
- some feature modules still use only `routes + service` because they are small enough for now
- `app.py` still exists for compatibility, even though `run.py` is the preferred dev entrypoint
- a few script entrypoints are still single files on purpose because they read better as orchestration modules than as deeper nested packages
