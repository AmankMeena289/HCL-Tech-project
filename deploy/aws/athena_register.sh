#!/usr/bin/env bash
# Register the gold and audit Delta tables in the Glue Data Catalog so they can
# be queried in Athena (workgroup "carevista"). Run after the first successful pipeline run.
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/build/outputs.env"
export AWS_PROFILE="${AWS_PROFILE:-carevista}" AWS_DEFAULT_REGION="$REGION"
BASE="s3://$LAKE/carevista"

athena() {  # athena "<sql>"  -> waits, prints state; returns query id in $QID
  QID=$(aws athena start-query-execution --work-group carevista --query-string "$1" --query QueryExecutionId --output text)
  while true; do
    STATE=$(aws athena get-query-execution --query-execution-id "$QID" --query QueryExecution.Status.State --output text)
    case "$STATE" in QUEUED|RUNNING) sleep 2 ;; *) break ;; esac
  done
  if [ "$STATE" != SUCCEEDED ]; then
    aws athena get-query-execution --query-execution-id "$QID" --query QueryExecution.Status.StateChangeReason --output text >&2
    return 1
  fi
}

GOLD="dim_patient dim_service dim_hospital fct_encounter fct_billing_line
kpi1_revenue_by_department_month kpi2_hospital_encounter_type kpi3_top10_patients
kpi4_patient_category_profile kpi5_inpatient_length_of_stay kpi6_region_service_category_mix"
for t in $GOLD; do
  # dim_/fct_ tables hold TIMESTAMP_NTZ columns (Delta reader feature timestampNtz), which Athena cannot read yet.
  if athena "CREATE EXTERNAL TABLE IF NOT EXISTS carevista_gold.$t LOCATION '$BASE/gold/$t' TBLPROPERTIES ('table_type'='DELTA')" 2>/dev/null; then
    echo "registered carevista_gold.$t"
  else
    echo "skipped    carevista_gold.$t (Delta feature not supported by Athena)"
  fi
done
for t in pipeline_audit run_history; do
  if athena "CREATE EXTERNAL TABLE IF NOT EXISTS carevista_ops.$t LOCATION '$BASE/audit/$t' TBLPROPERTIES ('table_type'='DELTA')" 2>/dev/null; then
    echo "registered carevista_ops.$t"
  else
    echo "skipped    carevista_ops.$t (Delta feature not supported by Athena)"
  fi
done

echo "-- check: eligible encounters and billed revenue"
athena "SELECT sum(eligible_encounters) AS eligible_encounters, round(sum(billed_amount), 2) AS billed_revenue FROM carevista_gold.kpi4_patient_category_profile"
aws athena get-query-results --query-execution-id "$QID" --query 'ResultSet.Rows[*].Data[*].VarCharValue' --output text
echo "-- audit (silver step):"
athena "SELECT source_file, rows_read, rows_accepted, rows_rejected FROM carevista_ops.pipeline_audit WHERE step = 'silver' ORDER BY source_file"
aws athena get-query-results --query-execution-id "$QID" --query 'ResultSet.Rows[*].Data[*].VarCharValue' --output text
