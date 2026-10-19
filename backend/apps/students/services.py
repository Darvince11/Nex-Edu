"""All writes to student records. Every change is audited."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.http import HttpRequest

from apps.academics.models import ClassArm
from apps.school.services import next_admission_number
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event, snapshot
from core.crypto import blind_index
from integrations.phone import normalize_gh_phone

from .models import Student, StudentGuardian

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 2 * 1024 * 1024


def _set_national_id_index(student: Student) -> None:
    student.national_id_bidx = (
        blind_index(
            student.national_id, tenant=require_tenant(), context="students.student.national_id"
        )
        if student.national_id
        else ""
    )


def create_student(
    *,
    request: HttpRequest | None,
    data: dict[str, Any],
    guardians: list[dict[str, Any]] | None = None,
    audit: bool = True,
) -> Student:
    with tenant_atomic():
        data = dict(data)
        if not data.get("admission_number"):
            data["admission_number"] = next_admission_number()
        student = Student(**data)
        _set_national_id_index(student)
        student.full_clean(exclude=["national_id_bidx"])
        student.save()
        for g in guardians or []:
            add_guardian(request=None, student=student, data=g, audit=False)
        if audit:
            record_event(
                action="student.created", request=request, target=student, after=snapshot(student)
            )
    return student


def update_student(
    *, request: HttpRequest | None, student: Student, data: dict[str, Any], reason: str = ""
) -> Student:
    with tenant_atomic():
        before = snapshot(student, list(data))
        for field_name, value in data.items():
            setattr(student, field_name, value)
        if "national_id" in data:
            _set_national_id_index(student)
        student.full_clean(exclude=["national_id_bidx"])
        student.save()
        record_event(
            action="student.updated",
            request=request,
            target=student,
            before=before,
            after=snapshot(student, list(data)),
            reason=reason,
        )
    return student


def add_guardian(
    *, request: HttpRequest | None, student: Student, data: dict[str, Any], audit: bool = True
) -> StudentGuardian:
    data = dict(data)
    if data.get("phone"):
        phone = normalize_gh_phone(data["phone"])
        if not phone:
            raise ValidationError({"phone": "Enter a valid Ghanaian mobile number."})
        data["phone"] = phone
    if not (data.get("phone") or data.get("email") or data.get("guardian_user_id")):
        raise ValidationError("A guardian needs a phone number, an email or a login.")
    with tenant_atomic():
        if data.get("is_primary"):
            student.guardians.update(is_primary=False)
        guardian = StudentGuardian.objects.create(student=student, **data)
        if audit:
            record_event(
                action="student.guardian_added",
                request=request,
                target=student,
                after={"guardian_id": guardian.pk, "relationship": guardian.relationship},
            )
    return guardian


# --- Bulk import ----------------------------------------------------------------

COLUMNS = [
    "admission_number",
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",
    "gender",
    "class",
    "guardian_name",
    "guardian_phone",
    "guardian_email",
    "guardian_relationship",
    "address",
    "hometown",
    "region",
]
REQUIRED = {"first_name", "last_name", "date_of_birth", "gender"}
_GENDERS = {
    "m": "male",
    "male": "male",
    "boy": "male",
    "f": "female",
    "female": "female",
    "girl": "female",
}


@dataclass
class ImportReport:
    dry_run: bool
    rows: int = 0
    created: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def error(self, row: int, column: str, message: str) -> None:
        self.errors.append({"row": row, "column": column, "message": message})


def _read_rows(filename: str, content: bytes) -> list[dict[str, str]]:
    if len(content) > MAX_IMPORT_BYTES:
        raise ValidationError("The file is larger than 2 MB. Split it into smaller files.")
    if filename.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        values = list(sheet.iter_rows(values_only=True)) if sheet is not None else []
        if not values:
            return []
        header = [str(h or "").strip().lower() for h in values[0]]
        return [
            {
                header[i]: ""
                if v is None
                else (v.date().isoformat() if isinstance(v, datetime) else str(v)).strip()
                for i, v in enumerate(row)
                if i < len(header)
            }
            for row in values[1:]
            if any(v not in (None, "") for v in row)
        ]
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [(f or "").strip().lower() for f in reader.fieldnames or []]
    return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def _parse_date(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _arm_lookup() -> dict[str, ClassArm]:
    arms = ClassArm.objects.select_related("level")
    return {re.sub(r"\s+", "", f"{a.level.name}{a.name}").lower(): a for a in arms}


def import_students(
    *, request: HttpRequest | None, filename: str, content: bytes, dry_run: bool
) -> ImportReport:
    """Validate every row first. If any row is invalid, nothing is written."""
    rows = _read_rows(filename, content)
    report = ImportReport(dry_run=dry_run, rows=len(rows))
    if len(rows) > MAX_IMPORT_ROWS:
        report.error(0, "", f"At most {MAX_IMPORT_ROWS} rows per file.")
        return report
    missing = REQUIRED - set(rows[0].keys()) if rows else REQUIRED
    if missing:
        report.error(1, ", ".join(sorted(missing)), "Missing required column(s).")
        return report

    arms = _arm_lookup()
    seen_numbers: set[str] = set()
    existing = set(Student.objects.values_list("admission_number", flat=True))
    prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

    for index, row in enumerate(rows, start=2):  # row 1 is the header
        data: dict[str, Any] = {}
        for column in REQUIRED:
            if not row.get(column):
                report.error(index, column, "Required.")
        number = row.get("admission_number", "")
        if number:
            if number in existing or number in seen_numbers:
                report.error(index, "admission_number", "Already used.")
            seen_numbers.add(number)
            data["admission_number"] = number
        dob = _parse_date(row.get("date_of_birth", ""))
        if row.get("date_of_birth") and not dob:
            report.error(index, "date_of_birth", "Use YYYY-MM-DD or DD/MM/YYYY.")
        gender = _GENDERS.get(row.get("gender", "").lower())
        if row.get("gender") and not gender:
            report.error(index, "gender", "Use male or female.")
        arm = None
        if row.get("class"):
            arm = arms.get(re.sub(r"\s+", "", row["class"]).lower())
            if arm is None:
                report.error(index, "class", f"No class called '{row['class']}'.")
        guardians: list[dict[str, Any]] = []
        if row.get("guardian_phone") or row.get("guardian_email"):
            phone = normalize_gh_phone(row.get("guardian_phone"))
            if row.get("guardian_phone") and not phone:
                report.error(index, "guardian_phone", "Not a valid Ghanaian mobile number.")
            guardians.append(
                {
                    "full_name": row.get("guardian_name", ""),
                    "phone": phone or "",
                    "email": row.get("guardian_email", ""),
                    "relationship": row.get("guardian_relationship") or "parent",
                    "is_primary": True,
                }
            )
        data.update(
            first_name=row.get("first_name", ""),
            middle_name=row.get("middle_name", ""),
            last_name=row.get("last_name", ""),
            date_of_birth=dob,
            gender=gender,
            arm=arm,
            address=row.get("address", ""),
            hometown=row.get("hometown", ""),
            region=row.get("region", ""),
        )
        prepared.append((data, guardians))

    if report.errors or dry_run:
        return report

    with tenant_atomic():
        for data, guardians in prepared:
            create_student(request=None, data=data, guardians=guardians, audit=False)
        report.created = len(prepared)
        record_event(
            action="student.bulk_imported",
            request=request,
            after={"file": filename[:100], "created": report.created},
        )
    return report
