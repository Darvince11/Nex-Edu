"""Online tests. Teachers write tests for the classes and subjects they teach and mark
short answers; pupils sit a test once, inside its window and time limit; parents see
results once released. Pupils never receive the answer key."""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.lms.api.views import can_teach, visible_homework
from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Attempt, Question, Test

TEACH, LEARN, VIEW, MANAGE = Perm.LMS_TEACH, Perm.LMS_LEARN, Perm.LMS_VIEW, Perm.LMS_MANAGE
ANYONE = (TEACH, LEARN, VIEW, MANAGE)


def extra_time_percent(attempt: Attempt) -> int:
    """Extra time from the pupil's learning support plan, while that module is on."""
    from apps.support.models import Plan
    from control_plane.modules import is_active

    if not is_active(require_tenant(), "special_ed"):
        return 0
    plan = Plan.objects.filter(student_id=attempt.student_id, status=Plan.Status.ACTIVE).first()
    return plan.extra_time_percent if plan else 0


def deadline(test: Test, attempt: Attempt) -> dt.datetime:
    extra = dt.timedelta(minutes=test.minutes * extra_time_percent(attempt) / 100)
    return min(
        attempt.started_at + dt.timedelta(minutes=test.minutes) + extra, test.closes_at + extra
    )


def auto_mark(test: Test, answers: dict[str, Any]) -> tuple[dict[str, int], bool]:
    """Marks for choice questions; whether any short answers still need a teacher."""
    awarded, pending = {}, False
    for q in test.questions.all():
        if q.kind == Question.Kind.SHORT:
            pending = True
            continue
        given = answers.get(str(q.pk))
        awarded[str(q.pk)] = q.marks if given is not None and given == q.answer else 0
    return awarded, pending


class QuestionSerializer(serializers.ModelSerializer[Question]):
    class Meta:
        model = Question
        fields: ClassVar = ["id", "order", "kind", "text", "options", "answer", "marks"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind = attrs.get("kind", Question.Kind.CHOICE)
        options = attrs.get("options") or []
        if kind == Question.Kind.TRUE_FALSE:
            attrs["options"] = ["True", "False"]
            options = attrs["options"]
        if kind in (Question.Kind.CHOICE, Question.Kind.TRUE_FALSE):
            if kind == Question.Kind.CHOICE and not 2 <= len(options) <= 6:
                raise serializers.ValidationError({"options": "Give 2 to 6 choices."})
            if not isinstance(attrs.get("answer"), int) or not 0 <= attrs["answer"] < len(options):
                raise serializers.ValidationError({"answer": "Say which choice is right."})
        return attrs


class PupilQuestionSerializer(serializers.ModelSerializer[Question]):
    """What a pupil sees: never the answer."""

    class Meta:
        model = Question
        fields: ClassVar = ["id", "order", "kind", "text", "options", "marks"]


class TestSerializer(serializers.ModelSerializer[Test]):
    arm_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    question_count = serializers.IntegerField(read_only=True, default=0)
    total_marks = serializers.SerializerMethodField()

    class Meta:
        model = Test
        fields: ClassVar = [
            "id",
            "arm",
            "arm_name",
            "subject",
            "subject_name",
            "title",
            "instructions",
            "opens_at",
            "closes_at",
            "minutes",
            "published",
            "results_released",
            "question_count",
            "total_marks",
        ]
        read_only_fields: ClassVar = ["published", "results_released"]
        extra_kwargs: ClassVar = {"minutes": {"min_value": 1, "max_value": 300}}

    def get_arm_name(self, obj: Test) -> str:
        return str(obj.arm)

    def get_total_marks(self, obj: Test) -> int:
        return sum(q.marks for q in obj.questions.all())

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        opens = attrs.get("opens_at", getattr(self.instance, "opens_at", None))
        closes = attrs.get("closes_at", getattr(self.instance, "closes_at", None))
        if opens and closes and closes <= opens:
            raise serializers.ValidationError({"closes_at": "It must close after it opens."})
        return attrs


class AnswersSerializer(serializers.Serializer):  # type: ignore[type-arg]
    answers = serializers.DictField()


class MarkAnswersSerializer(serializers.Serializer):  # type: ignore[type-arg]
    awarded = serializers.DictField(child=serializers.IntegerField(min_value=0))


def _pupil(request: Request) -> Student | None:
    return Student.objects.filter(user_id=request.user.pk, status=Student.Status.ACTIVE).first()


class TestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    TenantViewSet,
):
    serializer_class = TestSerializer
    required_permissions: ClassVar = {
        "list": ANYONE,
        "retrieve": ANYONE,
        "create": (TEACH, MANAGE),
        "update": (TEACH, MANAGE),
        "partial_update": (TEACH, MANAGE),
        "destroy": (TEACH, MANAGE),
        "questions": (TEACH, MANAGE),
        "publish": (TEACH, MANAGE),
        "release": (TEACH, MANAGE),
        "results": (TEACH, MANAGE),
        "mark": (TEACH, MANAGE),
        "start": LEARN,
        "save": LEARN,
        "submit": LEARN,
        "mine": (LEARN, VIEW),
    }

    def _teacher(self) -> bool:
        return bool(self.actor()[2] & {TEACH, MANAGE})

    def get_queryset(self) -> QuerySet[Test]:
        qs = (
            visible_homework(self, Test)
            .prefetch_related("questions")
            .annotate(question_count=Count("questions"))
        )
        if not self._teacher():
            qs = qs.filter(published=True)
        return qs

    def _editable(self, test: Test) -> None:
        user, _, perms = self.actor()
        if not can_teach(user, perms, test.arm_id, test.subject_id):
            raise PermissionDenied("Only the class's teachers change this test.")
        if test.attempts.exists():
            raise ValidationError(
                {"detail": "Pupils have started this test. It can't be changed now."}
            )

    def perform_create(self, serializer: Any) -> None:
        user, _, perms = self.actor()
        v = serializer.validated_data
        if not can_teach(user, perms, v["arm"].pk, v["subject"].pk):
            raise PermissionDenied("You can set tests only for classes and subjects you teach.")
        serializer.save(created_by=user.pk)

    def perform_update(self, serializer: Any) -> None:
        self._editable(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance: Test) -> None:
        self._editable(instance)
        instance.delete()

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        test = self.get_object()
        data = dict(TestSerializer(test).data)
        if self._teacher():
            data["questions"] = QuestionSerializer(test.questions.all(), many=True).data
        return Response(data)

    @extend_schema(request=QuestionSerializer(many=True), responses=QuestionSerializer(many=True))
    @action(detail=True, methods=["put"])
    def questions(self, request: Request, pk: str | None = None) -> Response:
        """Replace the test's questions (before anyone has started)."""
        test = self.get_object()
        self._editable(test)
        data = QuestionSerializer(data=request.data, many=True)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            test.questions.all().delete()
            for order, q in enumerate(data.validated_data):
                q.pop("order", None)
                Question.objects.create(test=test, order=order, **q)
        return Response(QuestionSerializer(test.questions.all(), many=True).data)

    @extend_schema(request=None, responses=TestSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        from apps.communication.services import notify_users

        test = self.get_object()
        user, _, perms = self.actor()
        if not can_teach(user, perms, test.arm_id, test.subject_id):
            raise PermissionDenied("Only the class's teachers publish this test.")
        if not test.questions.exists():
            raise ValidationError({"detail": "Add questions first."})
        test.published = True
        test.save(update_fields=["published"])
        pupils = Student.objects.filter(arm=test.arm, status=Student.Status.ACTIVE).exclude(
            user_id=None
        )
        notify_users(
            pupils.values_list("user_id", flat=True),
            kind="test",
            title=f"Online test: {test.subject.name}",
            body=f"{test.title} opens {timezone.localtime(test.opens_at):%a %d %b %H:%M}.",
            data={"test": str(test.pk)},
        )
        return Response(TestSerializer(test).data)

    @extend_schema(request=None, responses=TestSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request: Request, pk: str | None = None) -> Response:
        test = self.get_object()
        if (
            test.attempts.exclude(status=Attempt.Status.MARKED)
            .filter(status=Attempt.Status.SUBMITTED)
            .exists()
        ):
            raise ValidationError({"detail": "Mark the short answers first."})
        test.results_released = True
        test.save(update_fields=["results_released"])
        with tenant_atomic():
            record_event(action="exams.released", request=request, target=test)
        return Response(TestSerializer(test).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def results(self, request: Request, pk: str | None = None) -> Response:
        test = self.get_object()
        attempts = {a.student_id: a for a in test.attempts.all()}
        pupils = Student.objects.filter(arm=test.arm, status=Student.Status.ACTIVE).order_by(
            "last_name", "first_name"
        )
        return Response(
            [
                {
                    "student": str(p.pk),
                    "name": p.full_name,
                    "attempt": str(attempts[p.pk].pk) if p.pk in attempts else None,
                    "status": attempts[p.pk].status if p.pk in attempts else "",
                    "score": attempts[p.pk].score if p.pk in attempts else None,
                    "answers": attempts[p.pk].answers if p.pk in attempts else {},
                    "awarded": attempts[p.pk].awarded if p.pk in attempts else {},
                }
                for p in pupils
            ]
        )

    @extend_schema(
        request=MarkAnswersSerializer,
        responses=OpenApiTypes.OBJECT,
        parameters=[OpenApiParameter("attempt_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["post"], url_path=r"attempts/(?P<attempt_id>[^/.]+)/mark")
    def mark(
        self, request: Request, pk: str | None = None, attempt_id: str | None = None
    ) -> Response:
        test = self.get_object()
        attempt = get_object_or_404(Attempt, pk=attempt_id, test=test)
        if attempt.status == Attempt.Status.STARTED:
            raise ValidationError({"detail": "The pupil hasn't handed in yet."})
        data = MarkAnswersSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        short = {str(q.pk): q.marks for q in test.questions.filter(kind=Question.Kind.SHORT)}
        awarded = dict(attempt.awarded)
        for qid, marks in data.validated_data["awarded"].items():
            if qid not in short:
                raise ValidationError({"awarded": "Only short answers are marked by hand."})
            if marks > short[qid]:
                raise ValidationError({"awarded": f"At most {short[qid]} for that question."})
            awarded[qid] = marks
        attempt.awarded = awarded
        attempt.score = sum(awarded.values())
        if all(qid in awarded for qid in short):
            attempt.status = Attempt.Status.MARKED
        attempt.save(update_fields=["awarded", "score", "status"])
        return Response({"score": attempt.score, "status": attempt.status})

    def _attempt(self, test: Test, request: Request) -> tuple[Student, Attempt]:
        pupil = _pupil(request)
        if pupil is None or pupil.arm_id != test.arm_id:
            raise PermissionDenied("Only pupils in this class sit this test.")
        attempt = Attempt.objects.filter(test=test, student=pupil).first()
        if attempt is None:
            raise ValidationError({"detail": "Start the test first."})
        return pupil, attempt

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: str | None = None) -> Response:
        test = self.get_object()
        pupil = _pupil(request)
        if pupil is None or pupil.arm_id != test.arm_id:
            raise PermissionDenied("Only pupils in this class sit this test.")
        now = timezone.now()
        if now < test.opens_at:
            raise ValidationError({"detail": "This test hasn't opened yet."})
        attempt = Attempt.objects.filter(test=test, student=pupil).first()
        if attempt is None:
            if now >= test.closes_at:
                raise ValidationError({"detail": "This test has closed."})
            try:
                with transaction.atomic(using=require_tenant().db_alias):
                    attempt = Attempt.objects.create(test=test, student=pupil, started_at=now)
            except IntegrityError:
                attempt = Attempt.objects.get(test=test, student=pupil)
        if attempt.status != Attempt.Status.STARTED:
            raise ValidationError({"detail": "You've already handed this in."})
        return Response(
            {
                "attempt": str(attempt.pk),
                "ends_at": deadline(test, attempt),
                "answers": attempt.answers,
                "questions": PupilQuestionSerializer(test.questions.all(), many=True).data,
            }
        )

    @extend_schema(request=AnswersSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def save(self, request: Request, pk: str | None = None) -> Response:
        test = self.get_object()
        _, attempt = self._attempt(test, request)
        if attempt.status != Attempt.Status.STARTED or timezone.now() > deadline(test, attempt):
            raise ValidationError({"detail": "Time is up."})
        data = AnswersSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        valid = {str(q.pk) for q in test.questions.all()}
        attempt.answers = {k: v for k, v in data.validated_data["answers"].items() if k in valid}
        attempt.save(update_fields=["answers"])
        return Response({"saved": len(attempt.answers)})

    @extend_schema(request=AnswersSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str | None = None) -> Response:
        test = self.get_object()
        _, attempt = self._attempt(test, request)
        if attempt.status != Attempt.Status.STARTED:
            raise ValidationError({"detail": "You've already handed this in."})
        # Answers sent after time is up are ignored; what was saved in time counts.
        if timezone.now() <= deadline(test, attempt) and "answers" in request.data:
            data = AnswersSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            valid = {str(q.pk) for q in test.questions.all()}
            attempt.answers = {
                k: v for k, v in data.validated_data["answers"].items() if k in valid
            }
        awarded, pending = auto_mark(test, attempt.answers)
        attempt.awarded = awarded
        attempt.score = sum(awarded.values())
        attempt.submitted_at = timezone.now()
        attempt.status = Attempt.Status.SUBMITTED if pending else Attempt.Status.MARKED
        attempt.save()
        return Response({"status": attempt.status}, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def mine(self, request: Request) -> Response:
        """Pupils and parents: released results for their own (or their children's) tests."""
        user, roles, perms = self.actor()
        pupils = visible_students(user, roles, perms)
        attempts = Attempt.objects.filter(
            student__in=pupils, test__results_released=True
        ).select_related("test__subject", "student")
        return Response(
            [
                {
                    "test": str(a.test_id),
                    "title": a.test.title,
                    "subject": a.test.subject.name,
                    "student": a.student.first_name,
                    "score": a.score,
                    "out_of": sum(q.marks for q in a.test.questions.all()),
                    "closed": a.test.closes_at,
                }
                for a in attempts
            ]
        )
