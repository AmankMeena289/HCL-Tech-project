#!/usr/bin/env bash
# Start the CareVista Step Functions workflow and wait for it to finish.
#
#   bash deploy/aws/run_pipeline.sh                    # batch B20260630 with defaults
#   bash deploy/aws/run_pipeline.sh B20260630 silver   # make 'silver' fail once to show the retry
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/build/outputs.env"
export AWS_PROFILE="${AWS_PROFILE:-carevista}" AWS_DEFAULT_REGION="$REGION"

BATCH_ID="${1:-B20260630}"
FAIL_ONCE="${2:-none}"
NAME="run-$(date +%Y%m%dT%H%M%S)-$BATCH_ID"
INPUT="{\"batch_id\":\"$BATCH_ID\",\"fail_once\":\"$FAIL_ONCE\"}"

EXEC_ARN=$(aws stepfunctions start-execution --state-machine-arn "$SM_ARN" --name "$NAME" \
  --input "$INPUT" --query executionArn --output text)
echo "started $NAME"
echo "console: https://$REGION.console.aws.amazon.com/states/home?region=$REGION#/v2/executions/details/$EXEC_ARN"

while true; do
  STATUS=$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query status --output text)
  [ "$STATUS" = RUNNING ] || break
  echo "  $(date +%H:%M:%S) still running..."
  sleep 30
done
echo "execution $NAME finished: $STATUS"

echo "-- task attempts (from Step Functions history):"
aws stepfunctions get-execution-history --execution-arn "$EXEC_ARN" --max-items 500 \
  --query "events[?type=='TaskStateEntered' || type=='TaskSucceeded' || type=='TaskFailed'].[timestamp,type,stateEnteredEventDetails.name]" \
  --output text

[ "$STATUS" = SUCCEEDED ]
