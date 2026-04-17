"""Route registration for all feature modules."""


def register_routes(app, bcrypt, oauth):
    from radar_app.admin.routes import register_admin_routes
    from radar_app.auth.routes import register_auth_routes
    from radar_app.dashboard.routes import register_dashboard_routes
    from radar_app.portfolio.routes import register_portfolio_routes
    from radar_app.public.routes import register_public_routes
    from radar_app.search.routes import register_search_routes
    from radar_app.stocks.routes import register_stock_routes
    from radar_app.system.routes import register_system_routes
    from radar_app.watchlist.routes import register_watchlist_routes

    register_auth_routes(app, bcrypt, oauth)
    register_dashboard_routes(app)
    register_public_routes(app)
    register_search_routes(app)
    register_admin_routes(app)
    register_portfolio_routes(app)
    register_watchlist_routes(app)
    register_stock_routes(app)
    register_system_routes(app)
