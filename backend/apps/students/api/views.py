from __future__ import annotations

from dataclasses import asdict
from typing import Any, ClassVar

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import ClassArm
from apps.academics.selectors import is_form_teacher
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
        queryset = selectors.visible_students(
            self.request.user, roles, getattr(self.request, "permissions", ())
        )
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


ADD_PUPILS = (Perm.STUDENTS_MANAGE, Perm.STUDENTS_ADD_OWN_CLASS)


def check_own_class(request: Request, arm_id: Any) -> None:
    """Class teachers (no students.manage) may only add pupils to their own class."""
    if has_perm(request, Perm.STUDENTS_MANAGE):
        return
    if not arm_id or not is_form_teacher(request.user, arm_id):
        raise PermissionDenied("Class teachers can add pupils only to their own class.")


class StudentListCreateView(StudentScopedMixin, generics.ListCreateAPIView[Student]):
    serializer_class = StudentSerializer
    required_permissions: ClassVar = {"GET": Perm.STUDENTS_VIEW, "POST": ADD_PUPILS}

    def perform_create(self, serializer: StudentSerializer) -> None:  # type: ignore[override]
        arm = serializer.validated_data.get("arm")
        check_own_class(self.request, arm.pk if arm else None)
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
    required_permissions: ClassVar = {"GET": Perm.STUDENTS_VIEW, "POST": ADD_PUPILS}

    def get(self, request: Request, pk: str) -> Response:
        student = generics.get_object_or_404(self.get_queryset(), pk=pk)
        return Response(GuardianSerializer(student.guardians.all(), many=True).data)

    def post(self, request: Request, pk: str) -> Response:
        student = generics.get_object_or_404(self.get_queryset(), pk=pk)
        check_own_class(request, student.arm_id)
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


class GuardianInviteSerializer(serializers.Serializer):  # type: ignore[type-arg]
    key = serializers.CharField(max_length=80)


class GuardianDirectoryView(APIView):
    """Every parent and guardian of the pupils the viewer can see, each listed once
    (?q=, ?arm=). Staff only. POST {key} invites one to Nex Edu as a parent, linked
    to all their children."""

    required_permissions: ClassVar = {
        "GET": Perm.STUDENTS_VIEW,
        "POST": (Perm.MEMBERS_MANAGE, Perm.STUDENTS_MANAGE, Perm.ADMISSIONS_MANAGE),
    }

    def _students(self, request: Request) -> Any:
        from core.rbac import STAFF_ROLES

        roles = load_membership(request)
        if not roles & STAFF_ROLES:
            raise PermissionDenied("The guardian directory is for school staff.")
        return selectors.visible_students(request.user, roles, getattr(request, "permissions", ()))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        from apps.students.guardians import directory

        params = request.query_params
        return Response(
            directory(
                self._students(request),
                q=params.get("q", "").strip(),
                arm=params.get("arm") or None,
            )
        )

    @extend_schema(request=GuardianInviteSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        from apps.students.guardians import invite

        data = GuardianInviteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        linked = invite(
            request=request,
            granter_roles=load_membership(request),
            students=self._students(request),
            key=data.validated_data["key"],
        )
        return Response({"linked_children": linked}, status=status.HTTP_201_CREATED)


class PromotionSerializer(serializers.Serializer):  # type: ignore[type-arg]
    overrides = serializers.DictField(
        child=serializers.CharField(max_length=10), required=False, default=dict
    )
    confirm = serializers.BooleanField(required=False, default=False)


class PromotionView(APIView):
    """End of year. GET: each class, where it goes and its pupils. POST: move them
    (per-pupil overrides: promote, repeat, graduate or leave)."""

    required_permissions: ClassVar = {"GET": Perm.STUDENTS_MANAGE, "POST": Perm.STUDENTS_MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        from apps.students.promotion import plan

        return Response(plan())

    @extend_schema(request=PromotionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        from apps.students.promotion import apply

        data = PromotionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run = apply(request=request, **data.validated_data)
        return Response(
            {"summary": run.summary, "moves": run.moves}, status=status.HTTP_201_CREATED
        )
