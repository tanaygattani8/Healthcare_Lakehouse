"""One place that knows how to reach the Databricks SQL warehouse.

`.env` is a file, not an environment. Nothing loads it into `os.environ` on its
own, so every script that read `os.environ["DATABRICKS_HOST"]` directly worked
only when the surrounding shell happened to have exported the variables — which
is not a property you want a script to depend on. `load_dotenv()` closes that
gap, and having exactly one module call it means the next script cannot forget.

Two callers today, more in later phases. The duplicated `sql.connect(...)` block
they each carried is the reason this is a function rather than a loader helper.
"""

from __future__ import annotations

import os

from databricks import sql
from dotenv import load_dotenv

REQUIRED = ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")


def connect():
    """Open a warehouse connection using credentials from `.env`.

    Raises with the names of anything missing rather than a bare KeyError on
    whichever variable happened to be read first — the original failure named
    DATABRICKS_HOST while two others were equally absent.
    """
    # override=False: a variable already exported in the shell wins over .env,
    # which is what lets CI inject secrets without a file on disk.
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
