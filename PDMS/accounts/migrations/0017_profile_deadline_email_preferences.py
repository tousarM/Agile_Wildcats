from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_sprint_task_sprint"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="deadline_email_last_sent",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="deadline_email_notifications",
            field=models.BooleanField(default=False),
        ),
    ]
