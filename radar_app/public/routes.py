"""Public page routes extracted from the legacy app module."""

from flask import render_template, session

from radar_app.public.service import build_home_context


def register_public_routes(app):
    @app.route('/home')
    def home():
        return render_template('home.html', **build_home_context('user_id' in session))

    @app.route('/about')
    def about():
        return render_template('about.html')
