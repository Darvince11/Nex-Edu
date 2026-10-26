"""Browser-test fixtures (run by api.mjs, e2e settings only).

A super admin, the demo proprietor and the demo head teacher with known TOTP secrets, so tests can
complete two-step sign-in, and one pending school registration to review.
"""

from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal.auth import TOTP
from django.conf import settings

from control_plane.models import (
    Membership,
    PlatformRole,
    PlatformStaff,
    Role,
    SchoolRegistration,
    Tenant,
    User,
)
from control_plane.tenancy import tenant_context

assert settings.SETTINGS_MODULE == "config.settings.e2e", "browser-test fixtures only"

OPS_EMAIL = "ops@nexedu.test"
OPS_PASSWORD = "platform-ops-e2e-password"  # noqa: S105 - throwaway e2e data
OPS_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # base32; mirrored in web/e2e/totp.ts

ops = User.objects.create_user(OPS_EMAIL, OPS_PASSWORD, first_name="Kwame", last_name="Ops")
EmailAddress.objects.create(user=ops, email=OPS_EMAIL, verified=True, primary=True)
PlatformStaff.objects.create(user=ops, role=PlatformRole.SUPER_ADMIN)
TOTP.activate(ops, OPS_TOTP_SECRET)

HEAD_TOTP_SECRET = "KRSXG5CTMVRXEZLUKRSXG5CTMVRXEZLU"  # mirrored in web/e2e/totp.ts
TOTP.activate(User.objects.get(email="head@greenfield.test"), HEAD_TOTP_SECRET)

OWNER_TOTP_SECRET = "ONSWG4TFOQYTEMZUONSWG4TFOQYTEMZU"  # mirrored in web/e2e/totp.ts
TOTP.activate(User.objects.get(email="owner@greenfield.test"), OWNER_TOTP_SECRET)

# A class teacher of JHS 2 A with an app already set up (the demo teacher is
# left without one for the set-up test).
CLASS_TEACHER_TOTP_SECRET = "MNWGC43TORSWCY3IMVZDEMBSGZQXGZLT"  # mirrored in web/e2e/totp.ts
greenfield = Tenant.objects.get(slug="greenfield")
class_teacher = User.objects.create_user(
    "classteacher@greenfield.test", "NexEdu-demo-2026!", first_name="Efua", last_name="Boateng"
)
EmailAddress.objects.create(user=class_teacher, email=class_teacher.email, verified=True, primary=True)
for role in (Role.FORM_TEACHER, Role.TEACHER):
    Membership.objects.create(user=class_teacher, tenant=greenfield, role=role)
TOTP.activate(class_teacher, CLASS_TEACHER_TOTP_SECRET)
with tenant_context(greenfield):
    from apps.academics.models import ClassArm, TeachingAssignment

    jhs2 = ClassArm.objects.get(level__name="JHS 2", name="A")
    TeachingAssignment.objects.create(teacher_user_id=class_teacher.pk, arm=jhs2, is_form_teacher=True)

# A teacher used only by the authenticator set-up test (mfa.e2e.ts), which turns
# an app on for good: on the shared demo teacher it would stop every later test
# that signs in as them.
mfa_teacher = User.objects.create_user(
    "newapp@greenfield.test", "NexEdu-demo-2026!", first_name="Yaw", last_name="Darko"
)
EmailAddress.objects.create(user=mfa_teacher, email=mfa_teacher.email, verified=True, primary=True)
Membership.objects.create(user=mfa_teacher, tenant=greenfield, role=Role.TEACHER)

# A second proprietor without an authenticator app (it's optional), for the
# announcement banner test, so it never competes with OWNER's one-time codes.
director = User.objects.create_user(
    "director@greenfield.test", "NexEdu-demo-2026!", first_name="Kwesi", last_name="Owusu"
)
EmailAddress.objects.create(user=director, email=director.email, verified=True, primary=True)
Membership.objects.create(user=director, tenant=greenfield, role=Role.OWNER)

applicant = User.objects.create_user("applicant@example.test", "applicant-e2e-password", first_name="Abena")
EmailAddress.objects.create(user=applicant, email=applicant.email, verified=True, primary=True)
SchoolRegistration.objects.create(
    owner=applicant,
    school_name="Harmattan Hills School",
    slug="harmattan-hills",
    school_type=SchoolRegistration.SchoolType.BASIC,
    region="northern",
    town="Tamale",
    phone="+233244123456",
    expected_pupils=240,
)
print("Seeded platform staff and one pending registration for browser tests.")
