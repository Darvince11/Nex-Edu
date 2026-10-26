"""Database-level enforcement that platform audit events are append-only (PostgreSQL only)."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION platform_audit_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'control_plane_platformauditevent is append-only'
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER platform_audit_event_append_only
    BEFORE UPDATE OR DELETE ON control_plane_platformauditevent
    FOR EACH ROW EXECUTE FUNCTION platform_audit_block_mutation();

CREATE TRIGGER platform_audit_event_no_truncate
    BEFORE TRUNCATE ON control_plane_platformauditevent
    FOR EACH STATEMENT EXECUTE FUNCTION platform_audit_block_mutation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS platform_audit_event_no_truncate ON control_plane_platformauditevent;
DROP TRIGGER IF EXISTS platform_audit_event_append_only ON control_plane_platformauditevent;
DROP FUNCTION IF EXISTS platform_audit_block_mutation();
"""


def forward(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD)


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [("control_plane", "0003_platform_staff_audit_registrations")]
    operations = [migrations.RunPython(forward, reverse)]
