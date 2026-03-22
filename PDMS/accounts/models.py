import uuid
from django.db import models
from django.contrib.auth.models import User
from pathlib import PurePath

class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Profile(models.Model):
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('manager', 'Manager'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.user.username

class Task(models.Model):
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('done', 'Done')
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='todo'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    team = models.ForeignKey(
        'Team', null=True, blank=True, on_delete=models.SET_NULL, related_name='tasks'
    )

    #  New field for file uploads
    attachment = models.FileField(
        upload_to="task_files/",   # files will be stored in MEDIA_ROOT/task_files/
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.status})"


class TaskUpdate(models.Model):
    SYSTEM_CREATED_NOTE = "Task created."
    SYSTEM_ASSIGNED_PREFIX = "Task assigned to "
    SYSTEM_UNASSIGNED_NOTE = "Task unassigned."

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_updates",
    )
    status = models.CharField(max_length=20, choices=Task.STATUS_CHOICES)
    status_changed = models.BooleanField(default=False)
    previous_status = models.CharField(
        max_length=20,
        choices=Task.STATUS_CHOICES,
        null=True,
        blank=True,
    )
    previous_assignee = models.CharField(max_length=150, null=True, blank=True)
    current_assignee = models.CharField(max_length=150, null=True, blank=True)
    note = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to="task_update_files/",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task.title} update ({self.status})"

    @property
    def actor_name(self):
        return self.author.username if self.author else "System"

    @property
    def is_system_activity(self):
        return (
            self.note == self.SYSTEM_CREATED_NOTE
            or self.note == self.SYSTEM_UNASSIGNED_NOTE
            or self.note.startswith(self.SYSTEM_ASSIGNED_PREFIX)
        )

    @property
    def activity_detail(self):
        if self.note == self.SYSTEM_CREATED_NOTE:
            return "Created the task."

        if not self.status_changed and not self.note and not self.has_assignment_line and not self.has_attachment_line:
            return "Updated the task."

        return ""

    @property
    def note_detail(self):
        if self.note and not self.is_system_activity:
            return self.note
        return ""

    @property
    def previous_status_display(self):
        if not self.previous_status:
            return ""
        return dict(Task.STATUS_CHOICES).get(self.previous_status, self.previous_status)

    @property
    def has_status_line(self):
        return self.status_changed

    @property
    def has_assignment_line(self):
        return self.previous_assignee is not None or self.current_assignee is not None

    @property
    def previous_assignee_display(self):
        return self.previous_assignee or "Unassigned"

    @property
    def current_assignee_display(self):
        return self.current_assignee or "Unassigned"

    @property
    def has_attachment_line(self):
        return bool(self.attachment)

    @property
    def attachment_name(self):
        if not self.attachment:
            return ""
        return PurePath(self.attachment.name).name

class TeamInvite(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invites')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invites')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('team', 'recipient')

    def __str__(self):
        return f"{self.sender} → {self.recipient} ({self.team.name})"