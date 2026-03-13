from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=100)
    team = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20, blank=True)  # optional

    def __str__(self):
        return self.name or self.user.username


class Task(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('todo', 'To Do'),
            ('in_progress', 'In Progress'),
            ('done', 'Done')
        ],
        default='todo'
    )
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE)

    #  New field for file uploads
    attachment = models.FileField(
        upload_to="task_files/",   # files will be stored in MEDIA_ROOT/task_files/
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.title} ({self.status})"
