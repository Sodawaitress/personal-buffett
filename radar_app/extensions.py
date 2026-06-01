"""Flask extension bootstrap."""

import os

from authlib.integrations.flask_client import OAuth
from flask_bcrypt import Bcrypt
from flask_cors import CORS


def init_extensions(app):
    bcrypt = Bcrypt(app)
    oauth = OAuth(app)

    # Allow Next.js dev server to call /api/* endpoints.
    # In production the app is same-origin, so CORS only fires for localhost:3000.
    _dev_origin = os.getenv("NEXTJS_ORIGIN", "http://localhost:3000")
    CORS(
        app,
        resources={r"/api/*": {"origins": [_dev_origin]}},
        supports_credentials=True,
    )

    return bcrypt, oauth
