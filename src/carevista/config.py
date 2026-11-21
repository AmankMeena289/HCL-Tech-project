"""Pipeline settings in one place.

Every job takes the same two parameters from the workflow:
  * input_path - folder that holds the four staged source CSV files
  * batch_id   - a label for this load, for example "B20260630"

lake_root is the base folder (local path, abfss://, s3:// or gs://) under
which the landing, bronze, silver, gold, quarantine and audit zones live.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The four raw extracts, by entity name.
SOURCE_FILES: dict[str, str] = {
    "patients": "patients.csv",
    "services": "services.csv",
    "encounters": "encounters.csv",
    "encounter_services": "encounter_services.csv",
}

# Expected header of each file, in order. Bronze stops with a clear error if a
# file arrives with different columns (schema drift).
SOURCE_COLUMNS: dict[str, list[str]] = {
    "patients": [
        "patient_id", "first_name", "last_name", "email", "phone", "date_of_birth",
        "gender", "city", "patient_category", "registration_date", "last_updated",
    ],
    "services": ["service_id", "service_name", "service_category", "department"],
    "encounters": [
        "encounter_id", "patient_id", "hospital_id", "hospital_name", "hospital_city",
        "hospital_region", "encounter_type", "admit_timestamp", "discharge_timestamp",
        "encounter_status",
    ],
    "encounter_services": [
        "encounter_service_id", "encounter_id", "service_id", "service_date",
        "quantity", "unit_price", "discount_pct",
    ],
}

# Reporting cutoff (Asia/Kolkata local time, no conversion needed).
REPORTING_CUTOFF = "2026-06-30 23:59:59"

# Allowed values after standardisation.
PATIENT_CATEGORIES = ("SelfPay", "Insured", "Corporate")
ENCOUNTER_TYPES = ("Inpatient", "Outpatient", "Emergency")
ENCOUNTER_STATUSES = ("Completed", "Discharged", "Open", "Cancelled")
ELIGIBLE_STATUSES = ("Completed", "Discharged")

ZONES = ("landing", "bronze", "silver", "gold", "quarantine", "audit")

_BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


@dataclass(frozen=True)
class PipelineConfig:
    input_path: str
    batch_id: str
    lake_root: str
    reporting_cutoff: str = REPORTING_CUTOFF

    def __post_init__(self) -> None:
        if not _BATCH_ID_PATTERN.match(self.batch_id or ""):
            raise ValueError(
                f"batch_id {self.batch_id!r} is not valid: use 1-64 letters, digits, '_' or '-'."
            )
        if not self.input_path:
            raise ValueError("input_path is required.")
        if not self.lake_root:
            raise ValueError("lake_root is required.")

    def zone(self, zone: str) -> str:
        if zone not in ZONES:
            raise ValueError(f"Unknown zone {zone!r}")
        return f"{self.lake_root.rstrip('/')}/{zone}"

    def table(self, zone: str, name: str) -> str:
        return f"{self.zone(zone)}/{name}"

    def landing_dir(self) -> str:
        """Each batch lands in its own folder so files are never overwritten by another batch."""
        return f"{self.zone('landing')}/batch_id={self.batch_id}"
