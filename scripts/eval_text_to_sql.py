"""Ask each contestant every question, run its SQL, record a verdict (spec §4).

    .venv/Scripts/python.exe -m scripts.eval_text_to_sql --set dev --run-id dev-1 \\
        --contestants answer_key,raw,metrics [--genie-space <id>]

Resumable: a rerun with the same --run-id skips answers already recorded.
Only verdicts are stored, never result values.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from scripts import dbx
from scripts.eval_questions import Question, check_frozen, load
from scripts.sql_gate import problem
from scripts.text_to_sql_score import MAX_ROWS, REFUSE, decide, is_refusal

MODEL = "databricks-meta-llama-3-3-70b-instruct"
EVAL = Path("eval")
METRIC_VIEWS = Path("sql/metric_views.sql")
CONTESTANTS = ("answer_key", "raw", "metrics", "genie")

PROMPT = """You write Databricks SQL. Answer the question with exactly one SELECT
statement that names every table in full (catalog.schema.table). Reply with the
SQL only: no explanation, no code fences. If the tables below cannot answer the
question, or answering needs names, addresses, identifiers or other personal
details, reply with the single word REFUSE.
{note}
Tables:
{context}

Question: {question}"""

# D67: the first note read as "always select the dimensions", and never said
# what MEASURE() accepts; 7 of metrics' 11 dev-1 failures came from that.
METRICS_NOTE = """The tables are metric views. In a query on a metric view:
- MEASURE() takes only the name of a measure, such as MEASURE(stays). Put no
  expression or other function inside it; round or combine outside it, such as
  round(MEASURE(stays) / 1000, 1).
- Select a dimension only to break a number down by it, then GROUP BY ALL. For
  one overall number, select only measures and leave out GROUP BY.
- To count only some rows, filter on a dimension with WHERE.
For example:
SELECT is_planned, MEASURE(stays) FROM healthcare_dev.metrics.stays GROUP BY ALL
SELECT MEASURE(stays) FROM healthcare_dev.metrics.stays WHERE is_planned"""


def scrub(message: object) -> str:
    """Error text for storage, with no data values (spec §4): just the Databricks
    error class if there is one, else the first line with quoted literals masked."""
    text = str(message)
    if m := re.search(r"\[[A-Z_.]+\]", text):
        return m.group(0)
    first = (text.splitlines() or [""])[0]
    return re.sub(r"""'[^']*'|"[^"]*"|[0-9]+""", "...", first)[:300]


def fetch(cur, sql: str) -> tuple[list[tuple] | None, str | None]:
    try:
        cur.execute(sql)
        return [tuple(row) for row in cur.fetchmany(MAX_ROWS + 1)], None
    except Exception as e:          # the error is the verdict's evidence
        return None, scrub(e)


def gold_schema(cur) -> str:
    cur.execute("""
        SELECT c.table_name, t.comment, c.column_name, c.full_data_type, c.comment
        FROM healthcare_dev.information_schema.columns c
        JOIN healthcare_dev.information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'gold'
        ORDER BY c.table_name, c.ordinal_position""")
    lines, current = [], None
    for table, table_comment, column, dtype, comment in cur.fetchall():
        if table != current:
            lines.append(f"\nhealthcare_dev.gold.{table}: {table_comment or ''}")
            current = table
        lines.append(f"  {column} {dtype}" + (f" -- {comment}" if comment else ""))
    return "\n".join(lines)


def strip_fences(text: str) -> str:
    return re.sub(r"^```(?:sql)?\s*|\s*```$", "", text.strip(), flags=re.I).strip()


def ask_model(cur, context: str, note: str, question: str) -> str:
    # One statement, one question; nothing selected around it (errors E43).
    cur.execute(
        f"SELECT r.result, r.errorMessage FROM (SELECT ai_query('{MODEL}', :prompt, "
        "modelParameters => named_struct('temperature', 0.0), failOnError => false) AS r)",
        {"prompt": PROMPT.format(note=note, context=context, question=question)})
    result, error = cur.fetchone()
    if error:
        raise RuntimeError(error)
    return strip_fences(result)


def ask_genie(space_id: str, question: str) -> str:
    from datetime import timedelta

    from databricks.sdk import WorkspaceClient  # only the genie contestant needs it
    from databricks.sdk.service.dashboards import MessageStatus

    message = WorkspaceClient().genie.start_conversation_and_wait(
        space_id, question, timeout=timedelta(minutes=3))
    if message.error or message.status in (MessageStatus.FAILED, MessageStatus.CANCELLED):
        raise RuntimeError(f"genie {message.status}: {message.error}")
    for attachment in message.attachments or []:
        if attachment.query and attachment.query.query:
            return attachment.query.query
    return REFUSE        # Genie answered in words (or asked back): no SQL written


def record(cur, **row) -> None:
    cur.execute("""
        INSERT INTO healthcare_dev.ops.eval_run
        VALUES (:run_id, :set_name, :contestant, :question_id, :tier,
                CAST(:generated_sql AS STRING), :verdict, CAST(:error AS STRING),
                :seconds, current_timestamp())""", row)


def answer(cur, contestant: str, q: Question, contexts: dict, genie_space: str | None) -> str:
    if contestant == "answer_key":
        return q.answer_sql or REFUSE
    if contestant == "genie":
        return ask_genie(genie_space, q.question)
    return ask_model(cur, *contexts[contestant], q.question)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", choices=["dev", "test"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--contestants", default="answer_key,raw,metrics")
    parser.add_argument("--genie-space")
    args = parser.parse_args()

    if not re.fullmatch(rf"{args.set}-[0-9]+", args.run_id):
        raise SystemExit(f"--run-id must look like {args.set}-1")
    contestants = list(dict.fromkeys(c.strip() for c in args.contestants.split(",") if c.strip()))
    if unknown := set(contestants) - set(CONTESTANTS):
        raise SystemExit(f"unknown contestants: {unknown}")
    if "genie" in contestants and not args.genie_space:
        raise SystemExit("the genie contestant needs --genie-space")

    path = EVAL / f"questions_{args.set}.yaml"
    if args.set == "test":
        check_frozen(path, EVAL / "questions_test.sha256")
    questions = load(path)

    with dbx.connect() as conn, conn.cursor() as cur:
        # A run cut short by the cap must lose nothing: errored answers are retried
        # (same pattern as scripts/detect_llm.py deleting NULL replies).
        names = ", ".join(f"'{c}'" for c in contestants)    # from the fixed allow-list
        cur.execute("DELETE FROM healthcare_dev.ops.eval_run WHERE run_id = :run_id "
                    f"AND verdict = 'error' AND contestant IN ({names})",
                    {"run_id": args.run_id})
        cur.execute("SELECT contestant, question_id FROM healthcare_dev.ops.eval_run "
                    "WHERE run_id = :run_id", {"run_id": args.run_id})
        done = {tuple(row) for row in cur.fetchall()}
        # Each context is built only when its contestant runs (metric_views.sql
        # may not exist yet; the raw schema costs a query).
        contexts = {}
        if "raw" in contestants:
            contexts["raw"] = (gold_schema(cur), "")
        if "metrics" in contestants:
            contexts["metrics"] = (METRIC_VIEWS.read_text(encoding="utf-8"), METRICS_NOTE)
        # Defence in depth: the gate already blocks unqualified table names, but
        # if one slipped through it would resolve to a metric view, never silver.
        cur.execute("USE healthcare_dev.metrics")

        for q in questions:
            todo = [c for c in contestants if (c, q.id) not in done]
            if not todo:
                continue
            expected = None
            if q.answerable:
                expected, failure = fetch(cur, q.answer_sql)
                if failure:
                    raise SystemExit(f"{q.id}: the answer SQL itself fails: {failure}")
            for contestant in todo:
                started = time.time()
                reply = error = gate = actual = run_error = None
                try:
                    reply = answer(cur, contestant, q, contexts, args.genie_space)
                except Exception as e:                 # cap, timeout, malformed reply
                    error = scrub(e)
                if not error and not (reply or "").strip():
                    reply, error = None, "empty reply"
                if reply and q.answerable and not is_refusal(reply):
                    try:
                        gate = problem(reply)
                    except Exception as e:             # a gate bug must not end the run
                        gate = f"gate error: {type(e).__name__}"
                    if not gate:
                        actual, run_error = fetch(cur, reply)
                verdict = decide(answerable=q.answerable, reply=reply, gate_problem=gate,
                                 run_error=run_error, expected=expected, actual=actual,
                                 ordered=q.ordered)
                record(cur, run_id=args.run_id, set_name=args.set, contestant=contestant,
                       question_id=q.id, tier=q.tier, generated_sql=reply, verdict=verdict,
                       error=error or gate or run_error,
                       seconds=round(time.time() - started, 1))
                print(f"{q.id} t{q.tier} {contestant:10} {verdict}", flush=True)


if __name__ == "__main__":
    main()
