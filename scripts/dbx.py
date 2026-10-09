"""The one module that loads .env and connects to the Databricks SQL warehouse."""

from __future__ import annotations

import os

from databricks import sql
from dotenv import load_dotenv

REQUIRED = ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")


def connect():
    """Open a warehouse connection from .env, naming every missing variable."""
    # override=False: shell variables win, so CI can inject secrets.
    load_dotenv(override=False)

    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            f"missing credentials: {', '.join(missing)}. "
            "Copy .env.example to .env and fill it in — .env is gitignored."
        )

    return sql.connect(
        # The connector wants a bare hostname; .env holds the browser URL.
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", "").strip("/"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )
