"""Homework and learning materials. Who does what:

- Teachers (``lms.teach``) set homework and share materials for the classes and
  subjects they teach (class teachers: any subject in their class), and mark work.
- Pupils with a login (``lms.learn``) see their class's homework and hand work in.
- Parents (``lms.view``) see their children's homework, what was handed in and the
  marks and feedback.
- School leaders (``lms.manage``) see every class.
"""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, ClassVar

from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.models import TeachingAssignment
from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import User
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.files import save_tenant_file, tenant_file_response
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Homework, Material, Submission

TEACH, LEARN, VIEW, MANAGE = Perm.LMS_TEACH, Perm.LMS_LEARN, Perm.LMS_VIEW, Perm.LMS_MANAGE
ANYONE = (TEACH, LEARN, VIEW, MANAGE)
MAX_FILE = 5 * 1024 * 1024
ALLOWED = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain",
}


def _clean_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]", "_", PurePath(name).name)[:100]
    return stem or "file"


def _store(upload: Any, folder: str) -> tuple[str, str]:
    """Save an upload under the school's prefix; returns (key, display name)."""
    suffix = PurePath(upload.name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValidationError(
            {"file": "Upload a PDF, Word, PowerPoint, Excel, picture or text file."}
        )
    if upload.size > MAX_FILE:
        raise ValidationError({"file": "The file is too large (5 MB at most)."})
    name = _clean_name(upload.name)
    key = save_tenant_file(f"{folder}/{timezone.now():%Y%m%d%H%M%S}-{name}", upload.read())
    return key, name


def _download(request: Request, key: str, name: str) -> Any:
    if not key:
        raise ValidationError({"detail": "There is no file."})
    suffix = PurePath(name).suffix.lower()
    return tenant_file_response(
        key,
        filename=name,
        content_type=ALLOWED.get(suffix, "application/octet-stream"),
        as_link=request.query_params.get("link") == "1",
    )


def can_teach(user: Any, perms: Any, arm_id: Any, subject_id: Any) -> bool:
    if MANAGE in perms:
        return True
    if TEACH not in perms:
        return False
    mine = TeachingAssignment.objects.filter(teacher_user_id=user.pk, arm_id=arm_id)
    return mine.filter(Q(subject_id=subject_id) | Q(is_form_teacher=True)).exists()


def visible_homework(view: TenantViewSet, model: Any) -> QuerySet[Any]:
    user, roles, perms = view.actor()
    qs = model.objects.select_related("arm__level", "subject")
    if MANAGE in perms:
        return qs
    condition = Q(pk__in=[])
    if TEACH in perms:
        taught = TeachingAssignment.objects.filter(teacher_user_id=user.pk)
        condition |= Q(arm_id__in=taught.filter(is_form_teacher=True).values("arm_id"))
        for arm_id, subject_id in taught.exclude(subject=None).values_list("arm_id", "subject_id"):
            condition |= Q(arm_id=arm_id, subject_id=subject_id)
    if perms & {LEARN, VIEW}:
        arms = visible_students(user, roles, perms).exclude(arm=None).values("arm_id")
        condition |= Q(arm_id__in=arms)
    return qs.filter(condition)


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


class HomeworkSerializer(serializers.ModelSerializer[Homework]):
    arm_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    set_by_name = serializers.SerializerMethodField()
    handed_in = serializers.IntegerField(read_only=True, default=None)
    has_attachment = serializers.SerializerMethodField()

    class Meta:
        model = Homework
        fields: ClassVar = [
            "id",
            "arm",
            "arm_name",
            "subject",
            "subject_name",
            "title",
            "instructions",
            "due_on",
            "max_score",
            "hand_in_online",
            "attachment_name",
            "has_attachment",
            "video_url",
            "set_by_name",
            "handed_in",
            "created_at",
        ]
        read_only_fields: ClassVar = ["attachment_name"]

    def get_arm_name(self, obj: Homework) -> str:
        return str(obj.arm)

    def get_set_by_name(self, obj: Homework) -> str:
        return str(self.context.get("names", {}).get(obj.set_by, ""))

    def get_has_attachment(self, obj: Homework) -> bool:
        return bool(obj.attachment_key)


class SubmissionSerializer(serializers.ModelSerializer[Submission]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields: ClassVar = [
            "id",
            "homework",
            "student",
            "student_name",
            "text",
            "file_name",
            "has_file",
            "submitted_at",
            "late",
            "score",
            "feedback",
            "marked_at",
        ]

    def get_has_file(self, obj: Submission) -> bool:
        return bool(obj.file_key)


class HomeworkMarkSerializer(serializers.Serializer):  # type: ignore[type-arg]
    score = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    feedback = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


def _pupil_of(request: Request) -> Student | None:
    return Student.objects.filter(user_id=request.user.pk, status=Student.Status.ACTIVE).first()


class HomeworkViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    TenantViewSet,
):
    serializer_class = HomeworkSerializer
    parser_classes: ClassVar = [JSONParser, MultiPartParser, FormParser]
    required_permissions: ClassVar = {
        "list": ANYONE,
        "retrieve": ANYONE,
        "create": (TEACH, MANAGE),
        "update": (TEACH, MANAGE),
        "partial_update": (TEACH, MANAGE),
        "destroy": (TEACH, MANAGE),
        "attachment": ANYONE,
        "submit": LEARN,
        "submissions": (TEACH, MANAGE),
    }

    def get_queryset(self) -> QuerySet[Homework]:
        qs = visible_homework(self, Homework).annotate(handed_in=Count("submissions"))
        params = self.request.query_params
        if arm := params.get("arm"):
            qs = qs.filter(arm_id=arm)
        if params.get("upcoming") == "1":
            qs = qs.filter(due_on__gte=timezone.localdate())
        return qs

    def _context(self, rows: list[Homework]) -> dict[str, Any]:
        return {"names": _names({h.set_by for h in rows}), "request": self.request}

    @extend_schema(
        parameters=[
            OpenApiParameter("arm", OpenApiTypes.UUID),
            OpenApiParameter("upcoming", OpenApiTypes.STR),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:300])
        data = HomeworkSerializer(rows, many=True, context=self._context(rows)).data
        # Pupils and parents see what's been handed in, by whom of theirs.
        user, roles, perms = self.actor()
        if perms & {LEARN, VIEW} and not perms & {TEACH, MANAGE}:
            mine = visible_students(user, roles, perms)
            done = {
                (str(s.homework_id), str(s.student_id)): s
                for s in Submission.objects.filter(homework__in=rows, student__in=mine)
            }
            for row in data:
                row["mine"] = [
                    SubmissionSerializer(s).data for (h, _), s in done.items() if h == row["id"]
                ]
        return Response(data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        homework = self.get_object()
        return Response(HomeworkSerializer(homework, context=self._context([homework])).data)

    def perform_create(self, serializer: Any) -> None:
        from apps.communication.services import notify_guardians, notify_users

        user, _, perms = self.actor()
        v = serializer.validated_data
        if not can_teach(user, perms, v["arm"].pk, v["subject"].pk):
            raise PermissionDenied("You can set homework only for classes and subjects you teach.")
        key, name = ("", "")
        if upload := self.request.FILES.get("file"):
            key, name = _store(upload, "homework")
        with tenant_atomic():
            homework = serializer.save(set_by=user.pk, attachment_key=key, attachment_name=name)
            record_event(action="lms.homework_set", request=self.request, target=homework)
        pupils = list(Student.objects.filter(arm=homework.arm, status=Student.Status.ACTIVE))
        message = {
            "kind": "homework",
            "title": f"Homework: {homework.subject.name}",
            "body": f"{homework.title}, due {homework.due_on:%a %d %b}.",
            "data": {"homework": str(homework.pk)},
        }
        notify_users([p.user_id for p in pupils if p.user_id], **message)
        notify_guardians(pupils, **message)

    def perform_update(self, serializer: Any) -> None:
        user, _, perms = self.actor()
        homework = serializer.instance
        if homework.set_by != user.pk and MANAGE not in perms:
            raise PermissionDenied("Only the teacher who set it can change it.")
        if upload := self.request.FILES.get("file"):
            key, name = _store(upload, "homework")
            serializer.save(attachment_key=key, attachment_name=name)
        else:
            serializer.save()

    def perform_destroy(self, instance: Homework) -> None:
        user, _, perms = self.actor()
        if instance.set_by != user.pk and MANAGE not in perms:
            raise PermissionDenied("Only the teacher who set it can remove it.")
        if instance.submissions.exists():
            raise ValidationError(
                {"detail": "Pupils have handed work in. It can't be removed now."}
            )
        instance.delete()

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def attachment(self, request: Request, pk: str | None = None) -> Any:
        homework = self.get_object()
        return _download(request, homework.attachment_key, homework.attachment_name)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str | None = None) -> Response:
        homework = self.get_object()
        pupil = _pupil_of(request)
        if pupil is None or pupil.arm_id != homework.arm_id:
            raise PermissionDenied("Only pupils in this class can hand this in.")
        if not homework.hand_in_online:
            raise ValidationError({"detail": "Hand this one in on paper."})
        text = str(request.data.get("text", "")).strip()[:8000]
        upload = request.FILES.get("file")
        if not text and upload is None:
            raise ValidationError({"text": "Write something or attach a file."})
        existing = Submission.objects.filter(homework=homework, student=pupil).first()
        if existing and existing.marked_at:
            raise ValidationError({"detail": "Your teacher has already marked this."})
        key, name = (
            _store(upload, "submissions")
            if upload
            else (getattr(existing, "file_key", ""), getattr(existing, "file_name", ""))
        )
        now = timezone.now()
        submission, _ = Submission.objects.update_or_create(
            homework=homework,
            student=pupil,
            defaults={
                "text": text,
                "file_key": key,
                "file_name": name,
                "submitted_at": now,
                "late": timezone.localdate() > homework.due_on,
            },
        )
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def submissions(self, request: Request, pk: str | None = None) -> Response:
        """The class list with each pupil's work, for the teacher marking it."""
        homework = self.get_object()
        user, _, perms = self.actor()
        if not can_teach(user, perms, homework.arm_id, homework.subject_id):
            raise PermissionDenied("Only the class's teachers see the work.")
        handed = {s.student_id: s for s in homework.submissions.select_related("student")}
        pupils = Student.objects.filter(arm=homework.arm, status=Student.Status.ACTIVE).order_by(
            "last_name", "first_name"
        )
        return Response(
            [
                {
                    "student": str(p.pk),
                    "name": p.full_name,
                    "submission": SubmissionSerializer(handed[p.pk]).data
                    if p.pk in handed
                    else None,
                }
                for p in pupils
            ]
        )


class SubmissionViewSet(mixins.RetrieveModelMixin, TenantViewSet):
    """One pupil's work: download it, or mark it."""

    serializer_class = SubmissionSerializer
    required_permissions: ClassVar = {"retrieve": ANYONE, "file": ANYONE, "mark": (TEACH, MANAGE)}

    def get_queryset(self) -> QuerySet[Submission]:
        user, roles, perms = self.actor()
        qs = Submission.objects.select_related("homework", "student")
        if perms & {TEACH, MANAGE}:
            homework = visible_homework(self, Homework)
            return qs.filter(homework__in=homework)
        return qs.filter(student__in=visible_students(user, roles, perms))

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request: Request, pk: str | None = None) -> Any:
        submission = self.get_object()
        return _download(request, submission.file_key, submission.file_name)

    @extend_schema(request=HomeworkMarkSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def mark(self, request: Request, pk: str | None = None) -> Response:
        from apps.communication.services import notify_guardians, notify_users

        submission = self.get_object()
        homework = submission.homework
        user, _, perms = self.actor()
        if not can_teach(user, perms, homework.arm_id, homework.subject_id):
            raise PermissionDenied("Only the class's teachers mark the work.")
        data = HomeworkMarkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        score = data.validated_data.get("score")
        if score is not None and homework.max_score is not None and score > homework.max_score:
            raise ValidationError({"score": f"The most is {homework.max_score}."})
        submission.score = score
        submission.feedback = data.validated_data["feedback"]
        submission.marked_by = user.pk
        submission.marked_at = timezone.now()
        submission.save(update_fields=["score", "feedback", "marked_by", "marked_at"])
        pupil = submission.student
        out_of = f"/{homework.max_score}" if homework.max_score else ""
        message = {
            "kind": "homework",
            "title": f"Homework marked: {homework.title}",
            "body": (f"Mark: {score}{out_of}. " if score is not None else "")
            + (submission.feedback or ""),
            "data": {"homework": str(homework.pk)},
        }
        if pupil.user_id:
            notify_users([pupil.user_id], **message)
        notify_guardians([pupil], **message)
        return Response(SubmissionSerializer(submission).data)


class MaterialSerializer(serializers.ModelSerializer[Material]):
    arm_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields: ClassVar = [
            "id",
            "arm",
            "arm_name",
            "subject",
            "subject_name",
            "title",
            "note",
            "link",
            "file_name",
            "has_file",
            "created_at",
        ]
        read_only_fields: ClassVar = ["file_name"]

    def get_arm_name(self, obj: Material) -> str:
        return str(obj.arm)

    def get_has_file(self, obj: Material) -> bool:
        return bool(obj.file_key)


class MaterialViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, TenantViewSet
):
    serializer_class = MaterialSerializer
    parser_classes: ClassVar = [JSONParser, MultiPartParser, FormParser]
    required_permissions: ClassVar = {
        "list": ANYONE,
        "create": (TEACH, MANAGE),
        "destroy": (TEACH, MANAGE),
        "file": ANYONE,
    }

    def get_queryset(self) -> QuerySet[Material]:
        qs = visible_homework(self, Material)
        if arm := self.request.query_params.get("arm"):
            qs = qs.filter(arm_id=arm)
        return qs

    @extend_schema(parameters=[OpenApiParameter("arm", OpenApiTypes.UUID)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(MaterialSerializer(self.get_queryset()[:300], many=True).data)

    def perform_create(self, serializer: Any) -> None:
        user, _, perms = self.actor()
        v = serializer.validated_data
        if not can_teach(user, perms, v["arm"].pk, v["subject"].pk):
            raise PermissionDenied("You can share materials only with classes you teach.")
        key, name = ("", "")
        if upload := self.request.FILES.get("file"):
            key, name = _store(upload, "materials")
        if not (key or v.get("link") or v.get("note", "").strip()):
            raise ValidationError({"note": "Add a note, a link or a file."})
        serializer.save(shared_by=user.pk, file_key=key, file_name=name)

    def perform_destroy(self, instance: Material) -> None:
        user, _, perms = self.actor()
        if instance.shared_by != user.pk and MANAGE not in perms:
            raise PermissionDenied("Only the teacher who shared it can remove it.")
        instance.delete()

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request: Request, pk: str | None = None) -> Any:
        material = get_object_or_404(self.get_queryset(), pk=pk)
        return _download(request, material.file_key, material.file_name)
