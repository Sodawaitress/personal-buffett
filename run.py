#!/usr/bin/env python3
"""Production entry point. Gunicorn target: run:app"""

from app import app

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
