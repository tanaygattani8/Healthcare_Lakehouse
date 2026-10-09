"""Phase 5 probe P2, kept as a record: ask Genie a question and read back its SQL."""

from __future__ import annotations

import sys
import time
from datetime import timedelta

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(override=False)          # DATABRICKS_HOST / DATABRICKS_TOKEN
    w = WorkspaceClient()
    started = time.time()
    message = w.genie.start_conversation_and_wait(
        sys.argv[1], "How many hospital stays are there?",
        timeout=timedelta(minutes=3))
    print("status:", message.status)
    print("seconds:", round(time.time() - started, 1))
    for attachment in message.attachments or []:
        if attachment.query:
            print("sql:", attachment.query.query)
        if attachment.text:
            print("text:", attachment.text.content)


if __name__ == "__main__":
    main()
