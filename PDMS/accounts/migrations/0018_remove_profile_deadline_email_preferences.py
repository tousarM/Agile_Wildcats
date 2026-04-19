from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_profile_deadline_email_preferences"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="profile",
            name="deadline_email_last_sent",
        ),
        migrations.RemoveField(
            model_name="profile",
            name="deadline_email_notifications",
        ),
    ]
