# Generated by Django 3.1.2 on 2020-10-11 17:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations_ext', '0008_remove_organizationuser_pending'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='scrub_ip_addresses',
            field=models.BooleanField(default=True, help_text='Default for whether projects should script IP Addresses'),
        ),
    ]