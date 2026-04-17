"""Flask extension bootstrap."""

from authlib.integrations.flask_client import OAuth
from flask_bcrypt import Bcrypt


def init_extensions(app):
    bcrypt = Bcrypt(app)
    oauth = OAuth(app)
    return bcrypt, oauth
