set -euo pipefail
export MSYS_NO_PATHCONV=1   # E51: Git Bash would turn /Workspace/... into a Windows path
FILES=/Workspace/Users/tanaygattani8@gmail.com/.bundle/healthcare-lakehouse/dev/files
PY=.venv/Scripts/python.exe
field() { $PY -c "import json, sys; d = json.load(sys.stdin); print($1)"; }

# $2, optional: the notebook's parameters as JSON, e.g. '{"as_of": "2021-01-01"}'.
params=${2:-}
[ -n "$params" ] || params='{}'
body="{\"run_name\": \"phase6-$1\", \"tasks\": [{\"task_key\": \"main\",
  \"notebook_task\": {\"notebook_path\": \"$FILES/notebooks/$1\",
  \"base_parameters\": $params}}]}"
run_id=$(databricks jobs submit --no-wait --output json --json "$body" | field "d['run_id']")
echo "run $run_id: $FILES/notebooks/$1"
while :; do
  state=$(databricks jobs get-run "$run_id" --output json | field "d['state']['life_cycle_state']")
  case $state in TERMINATED|INTERNAL_ERROR|SKIPPED) break ;; esac
  sleep 20
done
task=$(databricks jobs get-run "$run_id" --output json | field "d['tasks'][0]['run_id']")
databricks jobs get-run-output "$task" --output json | field \
  "d['metadata']['state'].get('result_state'), '\n', (d.get('notebook_output') or {}).get('result') or d.get('error', '')"