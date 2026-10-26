from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import SimpleRouter

from apps.academics.api import calendar_feed
from apps.academics.api import views as academics
from apps.accounting.api import views as accounting
from apps.admissions.api import views as admissions
from apps.alumni.api import views as alumni
from apps.assessments.api import views as assessments
from apps.assist.api import views as assist
from apps.attendance.api import views as attendance
from apps.canteen.api import views as canteen
from apps.clinic.api import views as clinic
from apps.clubs.api import views as clubs
from apps.communication.api import views as communication
from apps.compliance.api import views as compliance
from apps.discipline.api import views as discipline
from apps.exams.api import views as exams
from apps.facilities.api import views as facilities
from apps.finance.api import views as finance
from apps.hostel.api import views as hostel
from apps.inventory.api import views as inventory
from apps.library.api import views as library
from apps.lms.api import views as lms
from apps.meetings.api import views as meetings
from apps.payroll.api import views as payroll
from apps.procurement.api import views as procurement
from apps.school.api import views as school
from apps.staff.api import views as staff
from apps.students.api import views as students
from apps.support.api import views as support
from apps.transport.api import views as transport
from apps.visitors.api import views as visitors
from apps.website.api import views as website
from control_plane.api import console, custom_roles
from control_plane.api import developer as dev
from control_plane.api import push as push_api
from control_plane.api import subscriptions as subs
from control_plane.api.members import MemberViewSet
from control_plane.api.platform import (
    PlatformOverviewView,
    PlatformRegistrationApproveView,
    PlatformRegistrationDetailView,
    PlatformRegistrationListView,
    PlatformRegistrationRejectView,
    PlatformRegistrationRetryView,
    PlatformTenantDetailView,
    PlatformTenantListView,
)
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
router.register("staff/departments", staff.DepartmentViewSet, basename="department")
router.register("staff/leave", staff.LeaveViewSet, basename="leave")
router.register("staff", staff.StaffViewSet, basename="staff")
router.register("admissions/applications", admissions.ApplicationViewSet, basename="application")
router.register("assessments/components", assessments.ComponentViewSet, basename="component")
router.register("assessments/grade-bands", assessments.GradeBandViewSet, basename="grade-band")
router.register("assessments/report-cards", assessments.ReportCardViewSet, basename="report-card")
router.register("finance/fee-items", finance.FeeItemViewSet, basename="fee-item")
router.register("finance/fee-schedules", finance.FeeScheduleViewSet, basename="fee-schedule")
router.register("finance/invoices", finance.InvoiceViewSet, basename="invoice")
router.register("finance/payments", finance.PaymentViewSet, basename="payment")
router.register("finance/scholarships", finance.ScholarshipViewSet, basename="scholarship")
router.register(
    "communication/announcements", communication.AnnouncementViewSet, basename="announcement"
)
router.register(
    "communication/notifications", communication.NotificationViewSet, basename="notification"
)
router.register("communication/deliveries", communication.DeliveryViewSet, basename="delivery")
router.register(
    "communication/conversations", communication.ConversationViewSet, basename="conversation"
)
router.register("calendar/events", academics.CalendarEventViewSet, basename="calendar-event")
router.register("library/books", library.BookViewSet, basename="library-book")
router.register("library/copies", library.CopyViewSet, basename="library-copy")
router.register("library/loans", library.LoanViewSet, basename="library-loan")
router.register("clubs/activities", clubs.ActivityViewSet, basename="club-activity")
router.register("clubs", clubs.ClubViewSet, basename="club")
router.register("meetings", meetings.MeetingDayViewSet, basename="meeting-day")
router.register("clinic/visits", clinic.VisitViewSet, basename="clinic-visit")
router.register("transport/vehicles", transport.VehicleViewSet, basename="vehicle")
router.register("transport/routes", transport.RouteViewSet, basename="route")
router.register("canteen/menu", canteen.MenuItemViewSet, basename="menu-item")
router.register("inventory/items", inventory.ItemViewSet, basename="stock-item")
router.register("inventory/suppliers", inventory.SupplierViewSet, basename="supplier")
router.register("inventory/requests", inventory.RequestViewSet, basename="stores-request")
router.register("inventory/assets", inventory.AssetViewSet, basename="asset")
router.register("facilities/rooms", facilities.RoomViewSet, basename="room")
router.register("facilities/bookings", facilities.BookingViewSet, basename="booking")
router.register("facilities/repairs", facilities.RepairViewSet, basename="repair")
router.register("gate/visits", visitors.VisitViewSet, basename="gate-visit")
router.register("gate/collectors", visitors.CollectorViewSet, basename="collector")
router.register("gate/pickups", visitors.PickupViewSet, basename="pickup")
router.register("lms/homework", lms.HomeworkViewSet, basename="homework")
router.register("lms/submissions", lms.SubmissionViewSet, basename="submission")
router.register("lms/materials", lms.MaterialViewSet, basename="material")
router.register("exams/tests", exams.TestViewSet, basename="online-test")
router.register("support/plans", support.PlanViewSet, basename="support-plan")
router.register("alumni/people", alumni.AlumnusViewSet, basename="alumnus")
router.register("alumni/gifts", alumni.GiftViewSet, basename="gift")
router.register("website/pages", website.PageViewSet, basename="website-page")
router.register("website/news", website.NewsViewSet, basename="website-news")
router.register("compliance/items", compliance.RequirementViewSet, basename="compliance-item")
router.register("hostel/houses", hostel.HouseViewSet, basename="house")
router.register("hostel/rooms", hostel.HostelRoomViewSet, basename="hostel-room")
router.register("hostel/exeats", hostel.ExeatViewSet, basename="exeat")
router.register("accounting/transactions", accounting.TransactionViewSet, basename="transaction")
router.register("payroll/runs", payroll.PayRunViewSet, basename="pay-run")
router.register("procurement/requests", procurement.RequisitionViewSet, basename="requisition")
router.register("procurement/orders", procurement.PurchaseOrderViewSet, basename="purchase-order")
router.register("discipline/incidents", discipline.IncidentViewSet, basename="incident")
router.register(
    "discipline/counselling", discipline.CounsellingNoteViewSet, basename="counselling-note"
)

api_v1 = [
    path("me/", MeView.as_view(), name="me"),
    path("push/", push_api.PushView.as_view(), name="push"),
    path("calendar/feed/", calendar_feed.MyCalendarFeedView.as_view(), name="calendar-feed"),
    path(
        "public/calendar/<str:token>/",
        calendar_feed.PublicCalendarFeedView.as_view(),
        name="public-calendar",
    ),
    path(
        "accounting/export/<str:kind>/",
        accounting.AccountingExportView.as_view(),
        name="accounting-export",
    ),
    # Developer API: the proprietor's keys and webhooks, and the read API keys call.
    path("integrations/", dev.IntegrationsView.as_view(), name="integrations"),
    path("integrations/keys/", dev.ApiKeyListView.as_view(), name="integrations-keys"),
    path(
        "integrations/keys/<uuid:pk>/revoke/",
        dev.ApiKeyRevokeView.as_view(),
        name="integrations-key-revoke",
    ),
    path("integrations/webhooks/", dev.WebhookListView.as_view(), name="integrations-webhooks"),
    path(
        "integrations/webhooks/<uuid:pk>/",
        dev.WebhookDetailView.as_view(),
        name="integrations-webhook",
    ),
    path("developer/students/", dev.DevStudentsView.as_view(), name="developer-students"),
    path("developer/classes/", dev.DevClassesView.as_view(), name="developer-classes"),
    path("developer/attendance/", dev.DevAttendanceView.as_view(), name="developer-attendance"),
    path("developer/invoices/", dev.DevInvoicesView.as_view(), name="developer-invoices"),
    path("developer/payments/", dev.DevPaymentsView.as_view(), name="developer-payments"),
    path("assist/", assist.AssistStatusView.as_view(), name="assist-status"),
    path("assist/report-comment/", assist.CommentDraftView.as_view(), name="assist-comment"),
    path(
        "assist/announcement/", assist.AnnouncementDraftView.as_view(), name="assist-announcement"
    ),
    # The proprietor's own pages: billing, the closing export, support access
    path(
        "account/schools/<slug:slug>/billing/",
        subs.AccountBillingView.as_view(),
        name="account-billing",
    ),
    path(
        "account/schools/<slug:slug>/billing/pay/",
        subs.AccountPayView.as_view(),
        name="account-pay",
    ),
    path(
        "account/schools/<slug:slug>/billing/charges/<str:reference>/",
        subs.AccountChargeView.as_view(),
        name="account-charge",
    ),
    path(
        "account/schools/<slug:slug>/export/",
        subs.AccountExportView.as_view(),
        name="account-export",
    ),
    path(
        "account/schools/<slug:slug>/support/",
        subs.AccountSupportView.as_view(),
        name="account-support",
    ),
    path(
        "account/schools/<slug:slug>/support/<uuid:pk>/revoke/",
        subs.AccountSupportRevokeView.as_view(),
        name="account-support-revoke",
    ),
    path("school/profile/", school.SchoolProfileView.as_view(), name="school-profile"),
    path("school/logo/", school.SchoolLogoView.as_view(), name="school-logo"),
    path("school/insights/", school.InsightsView.as_view(), name="school-insights"),
    path("reports/<str:kind>/", school.ReportView.as_view(), name="report"),
    path("school/roles/", custom_roles.CustomRolesView.as_view(), name="custom-roles"),
    path("school/roles/<uuid:pk>/", custom_roles.CustomRoleView.as_view(), name="custom-role"),
    path(
        "school/roles/<uuid:pk>/holders/",
        custom_roles.CustomRoleHoldersView.as_view(),
        name="custom-role-holders",
    ),
    path("school/setup/", school.SetupChecklistView.as_view(), name="school-setup"),
    path("school/modules/", school.ModulesView.as_view(), name="school-modules"),
    path("guardians/", students.GuardianDirectoryView.as_view(), name="guardian-directory"),
    path("promotion/", students.PromotionView.as_view(), name="promotion"),
    path("staff-register/", staff.StaffRegisterView.as_view(), name="staff-register"),
    path(
        "staff-register/summary/",
        staff.StaffAttendanceSummaryView.as_view(),
        name="staff-register-summary",
    ),
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
    path("calendar/", academics.CalendarView.as_view(), name="calendar"),
    path("library/", library.LibraryOverviewView.as_view(), name="library"),
    path("clinic/summary/", clinic.ClinicSummaryView.as_view(), name="clinic-summary"),
    path("transport/riders/", transport.RiderListView.as_view(), name="transport-riders"),
    path("canteen/pupils/", canteen.TillSearchView.as_view(), name="canteen-pupils"),
    path("canteen/till/<uuid:student_id>/", canteen.TillView.as_view(), name="canteen-till"),
    path(
        "canteen/till/<uuid:student_id>/<str:what>/",
        canteen.TillActionView.as_view(),
        name="canteen-till-action",
    ),
    path("canteen/wallets/<uuid:student_id>/", canteen.WalletView.as_view(), name="canteen-wallet"),
    path("canteen/mine/", canteen.MyWalletsView.as_view(), name="canteen-mine"),
    path("canteen/plans/", canteen.MealPlanView.as_view(), name="canteen-plans"),
    path("canteen/summary/", canteen.CanteenSummaryView.as_view(), name="canteen-summary"),
    path("inventory/summary/", inventory.StoresSummaryView.as_view(), name="stores-summary"),
    path("gate/check/", visitors.GateCheckView.as_view(), name="gate-check"),
    path("hostel/boarders/", hostel.BoardersView.as_view(), name="hostel-boarders"),
    path("hostel/roll-call/", hostel.RollCallView.as_view(), name="hostel-roll-call"),
    path("hostel/mine/", hostel.MyBoardingView.as_view(), name="hostel-mine"),
    path("accounting/accounts/", accounting.AccountsView.as_view(), name="accounting-accounts"),
    path("accounting/budgets/", accounting.BudgetView.as_view(), name="accounting-budgets"),
    path("payroll/rules/", payroll.PayrollRulesView.as_view(), name="payroll-rules"),
    path(
        "procurement/settings/",
        procurement.ProcurementSettingsView.as_view(),
        name="procurement-settings",
    ),
    path("payroll/salaries/", payroll.SalariesView.as_view(), name="payroll-salaries"),
    path("payroll/mine/", payroll.MyPayslipsView.as_view(), name="payroll-mine"),
    path("payroll/payslips/<uuid:pk>/pdf/", payroll.PayslipPdfView.as_view(), name="payslip-pdf"),
    path(
        "accounting/reports/<str:kind>/",
        accounting.AccountingReportView.as_view(),
        name="accounting-report",
    ),
    path("transport/mine/", transport.MyTransportView.as_view(), name="transport-mine"),
    path("transport/drivers/", transport.DriverOptionsView.as_view(), name="transport-drivers"),
    path("clinic/pupils/<uuid:student_id>/", clinic.PupilHealthView.as_view(), name="clinic-pupil"),
    path(
        "discipline/summary/", discipline.BehaviourSummaryView.as_view(), name="behaviour-summary"
    ),
    path("library/borrowers/", library.BorrowerSearchView.as_view(), name="library-borrowers"),
    path("library/import/", library.BookImportView.as_view(), name="library-import"),
    path(
        "finance/reports/balances/", finance.BalancesReportView.as_view(), name="finance-balances"
    ),
    path(
        "finance/reports/collections/",
        finance.CollectionsReportView.as_view(),
        name="finance-collections",
    ),
    path("public/admissions/", admissions.PublicAdmissionView.as_view(), name="public-admissions"),
    path("public/school-logo/", school.PublicSchoolLogoView.as_view(), name="public-school-logo"),
    path("public/site/", website.PublicSiteView.as_view(), name="public-site"),
    path("website/settings/", website.SiteSettingsView.as_view(), name="website-settings"),
    path("webhooks/paystack/", finance.PaystackWebhookView.as_view(), name="webhook-paystack"),
    path(
        "webhooks/flutterwave/",
        finance.FlutterwaveWebhookView.as_view(),
        name="webhook-flutterwave",
    ),
    path("audit/events/", AuditEventListView.as_view(), name="audit-events"),
    path("audit/verify/", AuditVerifyView.as_view(), name="audit-verify"),
    path("platform/overview/", PlatformOverviewView.as_view(), name="platform-overview"),
    # Super Admin console: pricing and billing, audit logs, announcements, system
    path("platform/billing/pricing/", console.PricingView.as_view(), name="platform-pricing"),
    path(
        "platform/billing/bands/<slug:code>/",
        console.PriceBandView.as_view(),
        name="platform-price-band",
    ),
    path(
        "platform/billing/payments/", console.BillingHistoryView.as_view(), name="platform-payments"
    ),
    path(
        "platform/billing/modules/",
        console.ModulePricesView.as_view(),
        name="platform-module-prices",
    ),
    path(
        "platform/billing/modules/<slug:code>/",
        console.ModulePriceView.as_view(),
        name="platform-module-price",
    ),
    path(
        "platform/tenants/<slug:slug>/modules/",
        console.TenantModulesView.as_view(),
        name="platform-tenant-modules",
    ),
    path("platform/audit/", console.AuditLogView.as_view(), name="platform-audit"),
    path("platform/audit/groups/", console.AuditGroupsView.as_view(), name="platform-audit-groups"),
    path("platform/audit/mine/", console.MyAuditLogView.as_view(), name="platform-audit-mine"),
    path(
        "platform/audit/verify/", console.AuditIntegrityView.as_view(), name="platform-audit-verify"
    ),
    path(
        "platform/announcements/",
        console.AnnouncementListView.as_view(),
        name="platform-announcements",
    ),
    path(
        "platform/announcements/<uuid:pk>/",
        console.AnnouncementDetailView.as_view(),
        name="platform-announcement",
    ),
    path(
        "platform/announcements/<uuid:pk>/publish/",
        console.AnnouncementPublishView.as_view(),
        name="platform-announcement-publish",
    ),
    path("platform/system/", console.SystemStatusView.as_view(), name="platform-system"),
    path("platform/system/operations/", subs.OperationsView.as_view(), name="platform-operations"),
    path("platform/billing/invoices/", subs.InvoiceListView.as_view(), name="platform-invoices"),
    path(
        "platform/billing/invoices/<uuid:pk>/",
        subs.InvoiceDetailView.as_view(),
        name="platform-invoice",
    ),
    path("platform/billing/rules/", subs.BillingRulesView.as_view(), name="platform-billing-rules"),
    path(
        "platform/billing/sms-bundles/",
        subs.SmsBundleListView.as_view(),
        name="platform-sms-bundles",
    ),
    path(
        "platform/billing/sms-bundles/<slug:code>/",
        subs.SmsBundleDetailView.as_view(),
        name="platform-sms-bundle",
    ),
    path(
        "platform/tenants/<slug:slug>/lifecycle/",
        subs.TenantLifecycleView.as_view(),
        name="platform-tenant-lifecycle",
    ),
    path(
        "platform/tenants/<slug:slug>/sms/",
        subs.TenantSmsView.as_view(),
        name="platform-tenant-sms",
    ),
    path(
        "platform/tenants/<slug:slug>/support/",
        subs.TenantSupportView.as_view(),
        name="platform-tenant-support",
    ),
    path("platform/system/problems/", console.ProblemListView.as_view(), name="platform-problems"),
    path(
        "platform/system/problems/<int:pk>/",
        console.ProblemDetailView.as_view(),
        name="platform-problem",
    ),
    path(
        "platform/system/security/",
        console.SecurityActivityView.as_view(),
        name="platform-security",
    ),
    path(
        "platform/system/scan/",
        console.VulnerabilityScanView.as_view(),
        name="platform-vulnerability-scan",
    ),
    path("nexedu-announcements/", console.FromNexEduView.as_view(), name="nexedu-announcements"),
    path(
        "nexedu-announcements/<uuid:pk>/read/",
        console.FromNexEduReadView.as_view(),
        name="nexedu-announcement-read",
    ),
    path("problems/browser/", console.BrowserErrorView.as_view(), name="browser-error"),
    path("platform/tenants/", PlatformTenantListView.as_view(), name="platform-tenants"),
    path(
        "platform/tenants/<slug:slug>/",
        PlatformTenantDetailView.as_view(),
        name="platform-tenant",
    ),
    path(
        "platform/registrations/",
        PlatformRegistrationListView.as_view(),
        name="platform-registrations",
    ),
    path(
        "platform/registrations/<uuid:pk>/",
        PlatformRegistrationDetailView.as_view(),
        name="platform-registration",
    ),
    path(
        "platform/registrations/<uuid:pk>/approve/",
        PlatformRegistrationApproveView.as_view(),
        name="platform-registration-approve",
    ),
    path(
        "platform/registrations/<uuid:pk>/retry/",
        PlatformRegistrationRetryView.as_view(),
        name="platform-registration-retry",
    ),
    path(
        "platform/registrations/<uuid:pk>/reject/",
        PlatformRegistrationRejectView.as_view(),
        name="platform-registration-reject",
    ),
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
