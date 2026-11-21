#!/usr/bin/env bash
# One-time: create the IAM user that deploys and operates CareVista.
# Run with an administrator login (e.g. after `aws login` or `aws configure`).
#
#   group  carevista-deployers  -> AWS managed policies for Glue, Step Functions,
#                                  Athena, SNS, CloudWatch Logs (read) + an inline
#                                  policy limited to carevista-* roles and buckets
#   user   carevista-deployer   -> member of the group; access key stored in the
#                                  local AWS CLI profile "carevista"
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"

REGION="${AWS_REGION:-ap-southeast-2}"
GROUP=carevista-deployers
USER_NAME=carevista-deployer
PROFILE=carevista
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "Account $ACCOUNT, region $REGION"

mkdir -p build
sed "s/__ACCOUNT__/$ACCOUNT/g" iam/deployer-policy.template.json > build/deployer-policy.json

aws iam get-user --user-name "$USER_NAME" >/dev/null 2>&1 || \
  aws iam create-user --user-name "$USER_NAME" --tags Key=project,Value=carevista >/dev/null

MANAGED="AWSGlueConsoleFullAccess AWSStepFunctionsFullAccess AmazonAthenaFullAccess AmazonSNSFullAccess CloudWatchLogsReadOnlyAccess"
if aws iam get-group --group-name "$GROUP" >/dev/null 2>&1 || aws iam create-group --group-name "$GROUP" >/dev/null 2>&1; then
  for p in $MANAGED; do aws iam attach-group-policy --group-name "$GROUP" --policy-arn "arn:aws:iam::aws:policy/$p"; done
  aws iam put-group-policy --group-name "$GROUP" --policy-name carevista-deployer-scoped \
    --policy-document file://build/deployer-policy.json
  aws iam add-user-to-group --user-name "$USER_NAME" --group-name "$GROUP"
  echo "Permissions granted through group $GROUP"
else
  # Some organisations block iam:CreateGroup with an SCP: attach to the user instead.
  for p in $MANAGED; do aws iam attach-user-policy --user-name "$USER_NAME" --policy-arn "arn:aws:iam::aws:policy/$p"; done
  aws iam put-user-policy --user-name "$USER_NAME" --policy-name carevista-deployer-scoped \
    --policy-document file://build/deployer-policy.json
  echo "Groups not allowed in this account; permissions attached directly to $USER_NAME"
fi
echo "User $USER_NAME ready"

if aws configure get aws_access_key_id --profile "$PROFILE" >/dev/null 2>&1; then
  echo "Profile '$PROFILE' already has a key; not creating another."
else
  KEYS=$(aws iam create-access-key --user-name "$USER_NAME" \
    --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text)
  KEY_ID=$(echo "$KEYS" | awk '{print $1}')
  SECRET=$(echo "$KEYS" | awk '{print $2}')
  aws configure set aws_access_key_id "$KEY_ID" --profile "$PROFILE"
  aws configure set aws_secret_access_key "$SECRET" --profile "$PROFILE"
  aws configure set region "$REGION" --profile "$PROFILE"
  echo "Access key created and saved to AWS CLI profile '$PROFILE' (~/.aws/credentials)."
fi

echo "Waiting for the new key to become active..."
for i in $(seq 1 20); do
  if aws sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
    aws sts get-caller-identity --profile "$PROFILE" --query Arn --output text
    exit 0
  fi
  sleep 3
done
echo "Key not active yet; retry deploy.sh in a minute." >&2
