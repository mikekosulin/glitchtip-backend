# Generated by Django 4.0.2 on 2022-02-26 17:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0004_auto_20210509_1658'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='type',
            field=models.CharField(default='', max_length=64),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='FileBlobIndex',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('offset', models.PositiveIntegerField()),
                ('blob', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='files.fileblob')),
                ('file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='files.file')),
            ],
            options={
                'unique_together': {('file', 'blob', 'offset')},
            },
        ),
    ]
