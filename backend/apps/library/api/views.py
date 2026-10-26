from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import User
from core.permissions import load_membership
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import Book, Copy, LibrarySettings, Loan

VIEW, MANAGE = Perm.LIBRARY_VIEW, Perm.LIBRARY_MANAGE
MAX_IMPORT_BYTES = 2 * 1024 * 1024


class CopySerializer(serializers.ModelSerializer[Copy]):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Copy
        fields: ClassVar = [
            "id",
            "accession_number",
            "status",
            "status_label",
            "condition",
            "added_on",
        ]
        read_only_fields: ClassVar = ["accession_number", "added_on"]

    def validate_status(self, value: str) -> str:
        # Lending and returning move a copy on and off loan; staff may only
        # withdraw a copy, put it back, or record it lost when it isn't on loan.
        if value == Copy.Status.ON_LOAN or (
            self.instance and self.instance.status == Copy.Status.ON_LOAN
        ):
            raise serializers.ValidationError("Use the desk to lend or return a copy.")
        return value


class BookSerializer(serializers.ModelSerializer[Book]):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    level_name = serializers.CharField(source="level.name", read_only=True, default="")
    subject_name = serializers.CharField(source="subject.name", read_only=True, default="")
    copies_total = serializers.IntegerField(read_only=True, default=0)
    copies_available = serializers.IntegerField(read_only=True, default=0)
    copies = serializers.IntegerField(
        write_only=True, required=False, min_value=1, max_value=services.MAX_COPIES_AT_ONCE
    )

    class Meta:
        model = Book
        fields: ClassVar = [
            "id",
            "title",
            "author",
            "isbn",
            "publisher",
            "category",
            "category_label",
            "subject",
            "subject_name",
            "level",
            "level_name",
            "shelf",
            "copies_total",
            "copies_available",
            "copies",
        ]

    def create(self, validated_data: dict[str, Any]) -> Book:
        count = validated_data.pop("copies", 1)
        book = super().create(validated_data)
        services.add_copies(book, count)
        return book

    def update(self, instance: Book, validated_data: dict[str, Any]) -> Book:
        validated_data.pop("copies", None)
        return super().update(instance, validated_data)


class BookViewSet(AuditedCrudViewSet):
    """The catalogue. Everyone with library access searches it; the desk edits it."""

    serializer_class = BookSerializer
    audit_name = "library_book"
    required_permissions: ClassVar = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
        "add_copies": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Book]:
        qs = Book.objects.select_related("level", "subject").annotate(
            copies_total=Count("copies", filter=~Q(copies__status=Copy.Status.WITHDRAWN)),
            copies_available=Count("copies", filter=Q(copies__status=Copy.Status.AVAILABLE)),
        )
        params = self.request.query_params
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(author__icontains=q)
                | Q(isbn__icontains=q)
                | Q(copies__accession_number__iexact=q)
            ).distinct()
        if category := params.get("category"):
            qs = qs.filter(category=category)
        if level := params.get("level"):
            qs = qs.filter(level_id=level)
        return qs[:500] if self.action == "list" else qs

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        book = self.get_object()
        data = BookSerializer(book).data
        if Perm.LIBRARY_MANAGE in getattr(request, "permissions", ()):
            data["copy_list"] = CopySerializer(book.copies.all(), many=True).data
        return Response(data)

    def perform_destroy(self, instance: Book) -> None:
        if Loan.objects.filter(copy__book=instance).exists():
            raise ValidationError(
                {"detail": "This book has been lent before. Withdraw its copies instead."}
            )
        super().perform_destroy(instance)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=CopySerializer(many=True))
    @action(detail=True, methods=["post"])
    def add_copies(self, request: Request, pk: str | None = None) -> Response:
        book = self.get_object()
        count = request.data.get("copies", 1)
        if not str(count).isdigit():
            raise ValidationError({"copies": "Enter a number."})
        copies = services.add_copies(book, int(count), request.data.get("accession_numbers"))
        return Response(CopySerializer(copies, many=True).data, status=status.HTTP_201_CREATED)


class CopyViewSet(mixins.UpdateModelMixin, TenantViewSet):
    """Withdraw a worn-out copy, note its condition, or put it back on the shelf."""

    serializer_class = CopySerializer
    queryset = Copy.objects.all()
    required_permissions: ClassVar = {"update": MANAGE, "partial_update": MANAGE}


class LoanSerializer(serializers.ModelSerializer[Loan]):
    accession_number = serializers.CharField(source="copy.accession_number", read_only=True)
    title = serializers.CharField(source="copy.book.title", read_only=True)
    book = serializers.UUIDField(source="copy.book_id", read_only=True)
    borrower = serializers.SerializerMethodField()
    borrower_class = serializers.SerializerMethodField()
    overdue_days = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields: ClassVar = [
            "id",
            "accession_number",
            "title",
            "book",
            "student",
            "staff_user_id",
            "borrower",
            "borrower_class",
            "borrowed_on",
            "due_on",
            "returned_on",
            "outcome",
            "renewals",
            "overdue_days",
            "reminded_on",
        ]

    def get_borrower(self, obj: Loan) -> str:
        if obj.student_id:
            return obj.student.full_name
        return str(self.context.get("staff_names", {}).get(obj.staff_user_id, "Staff member"))

    def get_borrower_class(self, obj: Loan) -> str:
        if obj.student_id and obj.student.arm_id:
            return str(obj.student.arm)
        return "" if obj.student_id else "Staff"

    def get_overdue_days(self, obj: Loan) -> int:
        if obj.outcome != Loan.Outcome.OPEN:
            return 0
        return max(0, (timezone.localdate() - obj.due_on).days)


class IssueSerializer(serializers.Serializer):  # type: ignore[type-arg]
    accession_number = serializers.CharField(max_length=30)
    student = serializers.UUIDField(required=False)
    staff_user = serializers.UUIDField(required=False)
    due_on = serializers.DateField(required=False)


class ReturnSerializer(serializers.Serializer):  # type: ignore[type-arg]
    accession_number = serializers.CharField(max_length=30)
    condition = serializers.ChoiceField(
        choices=Copy.Condition.choices, required=False, allow_blank=True
    )


class LoanViewSet(mixins.ListModelMixin, TenantViewSet):
    """Loans. The desk sees them all; others see their own and their children's
    (or pupils they teach)."""

    serializer_class = LoanSerializer
    required_permissions: ClassVar = {
        "list": VIEW,
        "issue": MANAGE,
        "give_back": MANAGE,
        "renew": MANAGE,
        "lost": MANAGE,
        "remind": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Loan]:
        user, roles, perms = self.actor()
        qs = Loan.objects.select_related("copy__book", "student__arm__level")
        if MANAGE not in perms:
            qs = qs.filter(
                Q(student__in=visible_students(user, roles, perms)) | Q(staff_user_id=user.pk)
            )
        params = self.request.query_params
        state = params.get("state", "open")
        if state == "open":
            qs = qs.filter(outcome=Loan.Outcome.OPEN)
        elif state == "overdue":
            qs = qs.filter(outcome=Loan.Outcome.OPEN, due_on__lt=timezone.localdate())
        elif state == "closed":
            qs = qs.exclude(outcome=Loan.Outcome.OPEN)
        if student := params.get("student"):
            qs = qs.filter(student_id=student)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(copy__book__title__icontains=q)
                | Q(copy__accession_number__iexact=q)
                | Q(student__first_name__icontains=q)
                | Q(student__last_name__icontains=q)
            )
        if state == "overdue":
            qs = qs.order_by("due_on")
        return qs

    def _context(self, loans: list[Loan]) -> dict[str, Any]:
        ids = {loan.staff_user_id for loan in loans if loan.staff_user_id}
        names = {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}
        return {"staff_names": names}

    def _one(self, loan: Loan, code: int = status.HTTP_200_OK) -> Response:
        return Response(LoanSerializer(loan, context=self._context([loan])).data, status=code)

    @extend_schema(
        parameters=[
            OpenApiParameter("state", OpenApiTypes.STR, enum=["open", "overdue", "closed", "all"]),
            OpenApiParameter("student", OpenApiTypes.UUID),
            OpenApiParameter("q", OpenApiTypes.STR),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        loans = list(self.get_queryset()[:500])
        return Response(LoanSerializer(loans, many=True, context=self._context(loans)).data)

    @extend_schema(request=IssueSerializer, responses=LoanSerializer)
    @action(detail=False, methods=["post"])
    def issue(self, request: Request) -> Response:
        data = IssueSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        student = get_object_or_404(Student, pk=v["student"]) if v.get("student") else None
        loan = services.issue(
            request=request,
            accession=v["accession_number"],
            student=student,
            staff_user_id=v.get("staff_user"),
            due_on=v.get("due_on"),
        )
        return self._one(loan, status.HTTP_201_CREATED)

    @extend_schema(request=ReturnSerializer, responses=LoanSerializer)
    @action(detail=False, methods=["post"], url_path="return")
    def give_back(self, request: Request) -> Response:
        data = ReturnSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        loan = services.return_copy(
            request=request,
            accession=data.validated_data["accession_number"],
            condition=data.validated_data.get("condition", ""),
        )
        return self._one(loan)

    @extend_schema(request=None, responses=LoanSerializer)
    @action(detail=True, methods=["post"])
    def renew(self, request: Request, pk: str | None = None) -> Response:
        return self._one(services.renew(loan=get_object_or_404(self.get_queryset(), pk=pk)))

    @extend_schema(request=None, responses=LoanSerializer)
    @action(detail=True, methods=["post"])
    def lost(self, request: Request, pk: str | None = None) -> Response:
        loan = get_object_or_404(Loan.objects.select_related("copy__book", "student"), pk=pk)
        return self._one(services.mark_lost(request=request, loan=loan))

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def remind(self, request: Request) -> Response:
        sms = bool(request.data.get("sms"))
        return Response({"pupils": services.remind_overdue(request=request, sms=sms)})


class LibrarySettingsSerializer(serializers.ModelSerializer[LibrarySettings]):
    class Meta:
        model = LibrarySettings
        fields: ClassVar = [
            "pupil_loan_days",
            "staff_loan_days",
            "pupil_limit",
            "staff_limit",
            "max_renewals",
        ]
        extra_kwargs: ClassVar = {
            "pupil_loan_days": {"min_value": 1, "max_value": 120},
            "staff_loan_days": {"min_value": 1, "max_value": 365},
            "pupil_limit": {"min_value": 1, "max_value": 20},
            "staff_limit": {"min_value": 1, "max_value": 50},
            "max_renewals": {"min_value": 0, "max_value": 10},
        }


class LibraryOverviewView(APIView):
    """GET: totals, popular books and the lending rules. PATCH: change the rules."""

    required_permissions: ClassVar = {"GET": VIEW, "PATCH": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        load_membership(request)
        rules = LibrarySettingsSerializer(LibrarySettings.load()).data
        if MANAGE not in getattr(request, "permissions", ()):
            return Response({"settings": rules})
        return Response({**services.summary(), "settings": rules})

    @extend_schema(request=LibrarySettingsSerializer, responses=LibrarySettingsSerializer)
    def patch(self, request: Request) -> Response:
        from control_plane.tenancy import tenant_atomic
        from core.audit.services import record_event

        rules = LibrarySettings.load()
        data = LibrarySettingsSerializer(rules, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            data.save()
            record_event(action="library.settings_changed", request=request, after=data.data)
        return Response(data.data)


class BorrowerSearchView(APIView):
    """Pupils and staff to lend to, by name or admission number (?q=)."""

    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(
        parameters=[OpenApiParameter("q", OpenApiTypes.STR)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        return Response(services.borrower_search(request.query_params.get("q", "")))


class BookImportView(APIView):
    """Add many books at once from a CSV file."""

    parser_classes: ClassVar = [MultiPartParser]
    required_permissions: ClassVar = {"POST": MANAGE}

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        },
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Choose a CSV file."})
        if upload.size > MAX_IMPORT_BYTES:
            raise ValidationError({"file": "The file is too large (2 MB at most)."})
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                {"file": "Save the spreadsheet as CSV (UTF-8) and try again."}
            ) from exc
        return Response(
            services.import_books(request=request, text=text), status=status.HTTP_201_CREATED
        )
