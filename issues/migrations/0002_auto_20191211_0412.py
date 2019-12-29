# Generated by Django 3.0 on 2019-12-11 04:12

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('issues', '0001_initial'),
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='issue',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='projects.Project'),
        ),
        migrations.AddField(
            model_name='event',
            name='issue',
            field=models.ForeignKey(help_text='Sentry calls this a group', on_delete=django.db.models.deletion.CASCADE, to='issues.Issue'),
        ),
        migrations.AddField(
            model_name='event',
            name='tags',
            field=models.ManyToManyField(blank=True, to='issues.EventTag'),
        ),
    ]