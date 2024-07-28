# Generated by Django 5.0.7 on 2024-07-27 18:49

from django.db import migrations


import base64

from allauth.mfa.adapter import get_adapter


def migrate_mfa(apps, schema_editor):
    UserKey = apps.get_model("django_rest_mfa", "UserKey")
    Authenticator = apps.get_model("mfa", "Authenticator")

    adapter = get_adapter()
    authenticators = []
    for totp in UserKey.objects.filter(key_type="TOTP").iterator():
        recovery_codes = set()
        # for sdevice in StaticDevice.objects.filter(
        #     confirmed=True, user_id=totp.user_id
        # ).iterator():
        #     recovery_codes.update(sdevice.token_set.values_list("token", flat=True))
        secret = totp.properties["secret_key"]
        # secret = base64.b32encode(bytes.fromhex(totp.key)).decode("ascii")
        totp_authenticator = Authenticator(
            user_id=totp.user_id,
            type="totp",
            data={"secret": adapter.encrypt(secret)},
        )
        authenticators.append(totp_authenticator)
        # authenticators.append(
        #     Authenticator(
        #         user_id=totp.user_id,
        #         type=Authenticator.Type.RECOVERY_CODES,
        #         data={
        #             "migrated_codes": [adapter.encrypt(c) for c in recovery_codes],
        #         },
        #     )
        # )
    Authenticator.objects.bulk_create(authenticators)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0011_alter_user_email"),
    ]

    operations = [migrations.RunPython(migrate_mfa)]
