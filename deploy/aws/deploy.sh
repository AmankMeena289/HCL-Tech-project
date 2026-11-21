#!/usr/bin/env bash
# Deploy CareVista on AWS: S3 + Glue (PySpark, Delta Lake) + Step Functions + SNS + Athena.
# Safe to rerun: existing resources are updated, not duplicated.
#
#   AWS_PROFILE=carevista bash deploy/aws/deploy.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
# pwd -W (Git Bash on Windows) gives C:/... so the Windows aws.exe can open the files;
# MSYS_NO_PATHCONV=1 above stops /c/... paths from being converted automatically.
ROOT="$(cd "$HERE/../.." && (pwd -W 2>/dev/null || pwd))"
ROOT="$(cygpath -m "$ROOT" 2>/dev/null || echo "$ROOT")"  # Windows Git Bash: native path for aws.exe / python
cd "$HERE"

export AWS_PROFILE="${AWS_PROFILE:-carevista}"
REGION="${AWS_REGION:-ap-southeast-2}"
export AWS_DEFAULT_REGION="$REGION"
PREFIX=carevista
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
STAGING="$PREFIX-$ACCOUNT-staging"
LAKE="$PREFIX-$ACCOUNT-lake"
ARTIFACTS="$PREFIX-$ACCOUNT-artifacts"
GLUE_ROLE="$PREFIX-glue-role"
SFN_ROLE="$PREFIX-sfn-role"
TOPIC_NAME="$PREFIX-pipeline-alerts"
SM_NAME="$PREFIX-daily"
BATCH_DATE=2026-06-30
PY=$(command -v python || command -v python3)
mkdir -p build
echo "== Account $ACCOUNT | region $REGION | profile $AWS_PROFILE"

render() {  # render <template> <output>
  sed -e "s|__ACCOUNT__|$ACCOUNT|g" -e "s|__REGION__|$REGION|g" -e "s|__PREFIX__|$PREFIX|g" \
      -e "s|__STAGING_BUCKET__|$STAGING|g" -e "s|__LAKE_BUCKET__|$LAKE|g" \
      -e "s|__ARTIFACTS_BUCKET__|$ARTIFACTS|g" -e "s|__TOPIC_ARN__|${TOPIC_ARN:-}|g" "$1" > "$2"
}

# ---------------------------------------------------------------- S3 ----
for b in "$STAGING" "$LAKE" "$ARTIFACTS"; do
  if ! aws s3api head-bucket --bucket "$b" >/dev/null 2>&1; then
    aws s3api create-bucket --bucket "$b" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  fi
  aws s3api put-public-access-block --bucket "$b" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$b" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-bucket-tagging --bucket "$b" --tagging 'TagSet=[{Key=project,Value=carevista}]'
  echo "bucket s3://$b ready"
done

# Source files go to staging unchanged.
for f in patients services encounters encounter_services; do
  aws s3 cp "$ROOT/data/source/$f.csv" "s3://$STAGING/carevista/$BATCH_DATE/$f.csv" --only-show-errors
done
echo "source CSVs uploaded to s3://$STAGING/carevista/$BATCH_DATE/"

# Code: the carevista package as a zip, plus the Glue entry script.
"$PY" package_code.py "$ROOT/src" build/carevista.zip
aws s3 cp build/carevista.zip "s3://$ARTIFACTS/code/carevista.zip" --only-show-errors
aws s3 cp glue_job.py "s3://$ARTIFACTS/code/glue_job.py" --only-show-errors
echo "code uploaded to s3://$ARTIFACTS/code/"

# ---------------------------------------------------------------- SNS ----
TOPIC_ARN=$(aws sns create-topic --name "$TOPIC_NAME" --tags Key=project,Value=carevista --query TopicArn --output text)
echo "SNS topic $TOPIC_ARN"

# ---------------------------------------------------------------- IAM roles ----
ensure_role() {  # ensure_role <name> <trust-file>
  if ! aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam create-role --role-name "$1" --assume-role-policy-document "file://$2" \
      --tags Key=project,Value=carevista >/dev/null
    echo "role $1 created"
  fi
}
ensure_role "$GLUE_ROLE" iam/glue-trust.json
aws iam attach-role-policy --role-name "$GLUE_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
render iam/glue-s3-policy.template.json build/glue-s3-policy.json
aws iam put-role-policy --role-name "$GLUE_ROLE" --policy-name carevista-s3 --policy-document file://build/glue-s3-policy.json

ensure_role "$SFN_ROLE" iam/sfn-trust.json
render iam/sfn-policy.template.json build/sfn-policy.json
aws iam put-role-policy --role-name "$SFN_ROLE" --policy-name carevista-run-glue --policy-document file://build/sfn-policy.json
GLUE_ROLE_ARN="arn:aws:iam::$ACCOUNT:role/$GLUE_ROLE"
SFN_ROLE_ARN="arn:aws:iam::$ACCOUNT:role/$SFN_ROLE"
echo "roles ready; waiting 10 s for IAM propagation"
sleep 10

# ---------------------------------------------------------------- Glue jobs ----
TASKS=(landing bronze silver gold)
for i in 0 1 2 3; do
  task=${TASKS[$i]}
  name="$PREFIX-0$((i+1))-$task"
  "$PY" build_job_json.py "$name" "$task" "$GLUE_ROLE_ARN" "$ARTIFACTS" "$STAGING" "$LAKE" "$BATCH_DATE" "build/job-$task"
  if aws glue get-job --job-name "$name" >/dev/null 2>&1; then
    aws glue update-job --cli-input-json "file://build/job-$task-update.json" >/dev/null
    echo "glue job $name updated"
  else
    aws glue create-job --cli-input-json "file://build/job-$task-create.json" >/dev/null
    echo "glue job $name created"
  fi
done

# ---------------------------------------------------------------- Step Functions ----
render state_machine.asl.json build/state_machine.json
SM_ARN="arn:aws:states:$REGION:$ACCOUNT:stateMachine:$SM_NAME"
if aws stepfunctions describe-state-machine --state-machine-arn "$SM_ARN" >/dev/null 2>&1; then
  aws stepfunctions update-state-machine --state-machine-arn "$SM_ARN" \
    --definition file://build/state_machine.json --role-arn "$SFN_ROLE_ARN" >/dev/null
  echo "state machine $SM_NAME updated"
else
  created=no
  for attempt in 1 2 3 4 5 6; do  # a brand-new role can take a few seconds to be assumable
    if aws stepfunctions create-state-machine --name "$SM_NAME" --definition file://build/state_machine.json \
         --role-arn "$SFN_ROLE_ARN" --tags key=project,value=carevista >/dev/null; then
      created=yes; break
    fi
    sleep 10
  done
  [ "$created" = yes ] || { echo "could not create state machine" >&2; exit 1; }
  echo "state machine $SM_NAME created"
fi

# ---------------------------------------------------------------- Athena ----
aws glue get-database --name carevista_gold >/dev/null 2>&1 || \
  aws glue create-database --database-input '{"Name":"carevista_gold","Description":"CareVista star schema and KPIs"}'
aws glue get-database --name carevista_ops >/dev/null 2>&1 || \
  aws glue create-database --database-input '{"Name":"carevista_ops","Description":"CareVista audit and run history"}'
aws athena get-work-group --work-group "$PREFIX" >/dev/null 2>&1 || \
  aws athena create-work-group --name "$PREFIX" --configuration \
    "ResultConfiguration={OutputLocation=s3://$ARTIFACTS/athena-results/},EnforceWorkGroupConfiguration=true,PublishCloudWatchMetricsEnabled=true" \
    --tags Key=project,Value=carevista
echo "Athena workgroup '$PREFIX' and Glue databases ready"

cat > build/outputs.env <<OUT
ACCOUNT=$ACCOUNT
REGION=$REGION
STAGING=$STAGING
LAKE=$LAKE
ARTIFACTS=$ARTIFACTS
TOPIC_ARN=$TOPIC_ARN
SM_ARN=$SM_ARN
OUT
echo "== Deploy complete. Outputs in deploy/aws/build/outputs.env"
