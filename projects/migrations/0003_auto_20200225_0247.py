# Generated by Django 3.0.3 on 2020-02-25 02:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0003_field_fix_and_editable'),
        ('projects', '0002_auto_20191215_1550'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='projects', to='organizations.Organization'),
        ),
    ]
