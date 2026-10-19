from __future__ import annotations

from dataclasses import asdict
from typing import Any, ClassVar

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import ClassArm
from apps.students import selectors, services
from apps.students.models import Student, StudentGuardian
from core.permissions import has_perm, load_membership
from core.rbac import Perm

SENSITIVE_FIELDS = ("medical_notes", "national_id")


class GuardianSerializer(serializers.ModelSerializer[StudentGuardian]):
    class Meta:
        model = StudentGuardian
        fields: ClassVar = [
            "id",
            "full_name",
            "phone",
            "email",
            "relationship",
            "is_primary",
            "receives_sms",
            "guardian_user_id",
        ]
        read_only_fields: ClassVar = ["guardian_user_id"]


class StudentSerializer(serializers.ModelSerializer[Student]):
    arm = serializers.PrimaryKeyRelatedField(
        queryset=ClassArm.objects.none(), allow_null=True, required=False
    )
    arm_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(max_length=30, required=False, allow_blank=True)

    class Meta:
        model = Student
        fields: ClassVar = [
            "id",
            "admission_number",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "arm",
            "arm_name",
            "status",
            "admitted_on",
            "address",
            "hometown",
            "region",
            "medical_notes",
            "national_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["id", "created_at", "updated_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Querysets are evaluated per request, inside the current school's context.
        self.fields["arm"].queryset = ClassArm.objects.all()  # type: ignore[attr-defined]
        request: Request | None = self.context.get("request")
        if request is None or not has_perm(request, Perm.STUDENTS_VIEW_SENSITIVE):
            for name in SENSITIVE_FIELDS:
                self.fields.pop(name, None)

    def validate_admission_number(self, value: str) -> str:
        qs = Student.objects.filter(admission_number=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if value and qs.exists():
            raise serializers.ValidationError("This admission number is already used.")
        return value

    def get_arm_name(self, obj: Student) -> str | None:
        return str(obj.arm) if obj.arm else None


class StudentScopedMixin:
    request: Request

    def get_queryset(self):  # type: ignore[no-untyped-def]
        roles = load_membership(self.request)
        queryset = selectors.visible_students(self.request.user, roles)
        params = self.request.query_params
        if arm := params.get("arm"):
            queryset = queryset.filter(arm_id=arm)
        if status_ := params.get("status"):
            queryset = queryset.filter(status=status_)
        if q := params.get("q"):
            queryset = queryset.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(admission_number__icontains=q)
            )
        return queryset


class StudentListCreateView(StudentScopedMixin, generics.ListCreateAPIView[Student]):
    serializer_class = StudentSerializer
    required_permissions: ClassVar = {"GET": Perm.STUDENTS_VIEW, "POST": Perm.STUDENTS_MANAGE}

    def perform_create(self, serializer: StudentSerializer) -> None:  # type: ignore[override]
        serializer.instance = services.create_student(
            request=self.request, data=dict(serializer.validated_data)
        )


class StudentDetailView(StudentScopedMixin, generics.RetrieveUpdateAPIView[Student]):
    """Students outside the user's scope return 404, so their existence isn't revealed."""

    serializer_class = StudentSerializer
    required_permissions: ClassVar = {
        "GET": Perm.STUDENTS_VIEW,
        "PATCH": Perm.STUDENTS_MANAGE,
        "PUT": Perm.STUDENTS_MANAGE,
    }

    def perform_update(self, serializer: StudentSerializer) -> None:  # type: ignore[override]
        serializer.instance = services.update_student(
            request=self.request,
            student=serializer.instance,  # type: ignore[arg-type]
            data=dict(serializer.validated_data),
            reason=self.request.headers.get("X-Change-Reason", ""),
        )


class StudentGuardiansView(StudentScopedMixin, generics.GenericAPIView[Student]):
    serializer_class = GuardianSerializer
    required_permissions: ClassVar = {"GET": Perm.STUDENTS_VIEW, "POST": Perm.STUDENTS_MANAGE}

    def get(self, request: Request, pk: str) -> Response:
        student = generics.get_object_or_404(self.get_queryset(), pk=pk)
        return Response(GuardianSerializer(student.guardians.all(), many=True).data)

    def post(self, request: Request, pk: str) -> Response:
        student = generics.get_object_or_404(self.get_queryset(), pk=pk)
        data = GuardianSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        guardian = services.add_guardian(
            request=request, student=student, data=dict(data.validated_data)
        )
        return Response(GuardianSerializer(guardian).data, status=status.HTTP_201_CREATED)


class StudentImportView(APIView):
    """Upload a CSV or Excel (.xlsx) file. ``dry_run=1`` validates without writing."""

    parser_classes = [MultiPartParser]
    required_permissions: ClassVar = {"POST": Perm.STUDENTS_MANAGE}

    @extend_schema(
        request={"multipart/form-data": OpenApiTypes.OBJECT}, responses=OpenApiTypes.OBJECT
    )
    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Attach a file named 'file'."}, status=400)
        if not upload.name.lower().endswith((".csv", ".xlsx")):
            return Response({"detail": "Upload a .csv or .xlsx file."}, status=400)
        report = services.import_students(
            request=request,
            filename=upload.name,
            content=upload.read(),
            dry_run=request.data.get("dry_run") in ("1", "true", "True"),
        )
        code = status.HTTP_201_CREATED if report.created else (400 if report.errors else 200)
        return Response(asdict(report), status=code)
