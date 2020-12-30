# Generated by Django 3.1.4 on 2020-12-29 16:22

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0008_event_release"),
    ]

    database_operations = [
        migrations.AlterModelTable("Event", "events_event"),
        migrations.AlterModelTable("EventTagKey", "events_eventtagkey"),
        migrations.AlterModelTable("EventTag", "events_eventtag"),
    ]

    state_operations = [
        migrations.DeleteModel("Event"),
        migrations.DeleteModel("EventTagKey"),
        migrations.DeleteModel("EventTag"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations, state_operations=state_operations
        )
    ]
