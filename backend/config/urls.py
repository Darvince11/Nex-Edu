from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import SimpleRouter

from apps.academics.api import views as academics
from apps.admissions.api import views as admissions
from apps.assessments.api import views as assessments
from apps.attendance.api import views as attendance
from apps.communication.api import views as communication
from apps.finance.api import views as finance
from apps.school.api import views as school
from apps.staff.api import views as staff
from apps.students.api import views as students
from control_plane.api.members import MemberViewSet
from control_plane.api.platform import PlatformTenantListView
from control_plane.api.registrations import RegistrationListCreateView, SlugAvailabilityView
from control_plane.api.views import MeView
from core.audit.api.views import AuditEventListView, AuditVerifyView

router = SimpleRouter(trailing_slash=True)
router.register("members", MemberViewSet, basename="member")
router.register("academics/sessions", academics.SessionViewSet, basename="session")
router.register("academics/terms", academics.TermViewSet, basename="term")
router.register("academics/levels", academics.LevelViewSet, basename="level")
router.register("academics/arms", academics.ArmViewSet, basename="arm")
router.register("academics/subjects", academics.SubjectViewSet, basename="subject")
router.register("academics/assignments", academics.AssignmentViewSet, basename="assignment")
router.register("academics/periods", academics.PeriodViewSet, basename="period")
router.register("staff", staff.StaffViewSet, basename="staff")
router.register("admissions/applications", admissions.ApplicationViewSet, basename="application")
router.register("assessments/components", assessments.ComponentViewSet, basename="component")
router.register("assessments/grade-bands", assessments.GradeBandViewSet, basename="grade-band")
router.register("assessments/report-cards", assessments.ReportCardViewSet, basename="report-card")
router.register("finance/fee-items", finance.FeeItemViewSet, basename="fee-item")
router.register("finance/fee-schedules", finance.FeeScheduleViewSet, basename="fee-schedule")
router.register("finance/invoices", finance.InvoiceViewSet, basename="invoice")
router.register("finance/payments", finance.PaymentViewSet, basename="payment")
router.register(
    "communication/announcements", communication.AnnouncementViewSet, basename="announcement"
)
router.register(
    "communication/notifications", communication.NotificationViewSet, basename="notification"
)
router.register("communication/deliveries", communication.DeliveryViewSet, basename="delivery")

api_v1 = [
    path("me/", MeView.as_view(), name="me"),
    path("school/profile/", school.SchoolProfileView.as_view(), name="school-profile"),
    path("school/payment-settings/", school.PaymentSettingsView.as_view(), name="payment-settings"),
    path(
        "school/messaging-settings/",
        school.MessagingSettingsView.as_view(),
        name="messaging-settings",
    ),
    path("students/", students.StudentListCreateView.as_view(), name="student-list"),
    path("students/import/", students.StudentImportView.as_view(), name="student-import"),
    path("students/<uuid:pk>/", students.StudentDetailView.as_view(), name="student-detail"),
    path(
        "students/<uuid:pk>/guardians/",
        students.StudentGuardiansView.as_view(),
        name="student-guardians",
    ),
    path(
        "students/<uuid:student_id>/attendance/",
        attendance.StudentAttendanceView.as_view(),
        name="student-attendance",
    ),
    path("attendance/register/", attendance.RegisterView.as_view(), name="attendance-register"),
    path("attendance/summary/", attendance.ArmSummaryView.as_view(), name="attendance-summary"),
    path("assessments/scores/", assessments.ScoreSheetView.as_view(), name="score-sheet"),
    path("assessments/scores/amend/", assessments.AmendScoreView.as_view(), name="score-amend"),
    path(
        "assessments/results/compute/",
        assessments.ComputeResultsView.as_view(),
        name="results-compute",
    ),
    path(
        "assessments/results/publish/",
        assessments.PublishResultsView.as_view(),
        name="results-publish",
    ),
    path("finance/summary/", finance.TermSummaryView.as_view(), name="finance-summary"),
    path("public/admissions/", admissions.PublicAdmissionView.as_view(), name="public-admissions"),
    path("webhooks/paystack/", finance.PaystackWebhookView.as_view(), name="webhook-paystack"),
    path(
        "webhooks/flutterwave/",
        finance.FlutterwaveWebhookView.as_view(),
        name="webhook-flutterwave",
    ),
    path("audit/events/", AuditEventListView.as_view(), name="audit-events"),
    path("audit/verify/", AuditVerifyView.as_view(), name="audit-verify"),
    path("platform/tenants/", PlatformTenantListView.as_view(), name="platform-tenants"),
    path("registrations/", RegistrationListCreateView.as_view(), name="registrations"),
    path(
        "registrations/slug-check/", SlugAvailabilityView.as_view(), name="registration-slug-check"
    ),
    path("", include(router.urls)),
]

urlpatterns = [
    path("_allauth/", include("allauth.headless.urls")),
    path("api/v1/", include(api_v1)),
]

if settings.ADMIN_ENABLED:
    urlpatterns.append(path("admin/", admin.site.urls))

if settings.DEBUG:
    urlpatterns.append(path("api/schema/", SpectacularAPIView.as_view(), name="schema"))
