# Generated by Django 4.1.3 on 2022-11-29 15:48

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "organizations_ext",
            "0001_squashed_0003_alter_organization_id_alter_organization_users_and_more",
        ),
        ("teams", "0003_auto_20200613_2156"),
    ]

    operations = [
        migrations.AlterField(
            model_name="team",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="team",
            name="members",
            field=models.ManyToManyField(
                blank=True, to="organizations_ext.organizationuser"
            ),
        ),
    ]