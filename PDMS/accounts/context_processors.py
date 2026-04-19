from django.utils import timezone

from .models import Profile, Task

DEADLINE_WARNING_DAYS = 3


def notification_summary(request):
    if not request.user.is_authenticated:
        return {
            "notification_unread_count": 0,
            "recent_notifications": [],
        }

    profile, _ = Profile.objects.get_or_create(user=request.user)
    team = profile.team
    if not team:
        return {
            "notification_unread_count": 0,
            "recent_notifications": [],
        }

    today = timezone.localdate()
    alerts = []

    tasks = (
        Task.objects.filter(team=team, due_date__isnull=False)
        .exclude(status="done")
        .select_related("team")
        .order_by("due_date", "title")
    )

    for task in tasks:
        days_remaining = (task.due_date - today).days
        if days_remaining > DEADLINE_WARNING_DAYS:
            continue

        team_name = task.team.name if task.team else "your team"
        assignee_name = task.assigned_to.username if task.assigned_to else "unassigned"
        label = task.deadline_label.lower()
        alerts.append(
            {
                "title": f"Deadline reminder: {task.title}",
                "message": f"{task.title} is {label} for {team_name} and assigned to {assignee_name}. Due date: {task.due_date.isoformat()}.",
                "due_date": task.due_date,
                "notification_type": task.deadline_state,
            }
        )

    return {
        "notification_unread_count": len(alerts),
        "recent_notifications": alerts[:5],
    }
