# Generated by Django 5.1.5 on 2025-03-19 00:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tada', '0004_notificationmessage_title'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationlog',
            name='title',
            field=models.CharField(default='', max_length=50),
        ),
    ]
