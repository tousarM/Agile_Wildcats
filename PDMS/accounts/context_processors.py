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
        Task.objects.filter(team=team)
        .exclude(status="done")
        .select_related("team", "assigned_to", "reviewer", "reviewed_by")
        .order_by("due_date", "title")
    )

    for task in tasks:
        if task.due_date:
            days_remaining = (task.due_date - today).days
            if days_remaining <= DEADLINE_WARNING_DAYS:
                team_name = task.team.name if task.team else "your team"
                assignee_name = task.assigned_to.username if task.assigned_to else "unassigned"
                label = task.deadline_label.lower()
                alerts.append(
                    {
                        "title": f"Deadline reminder: {task.title}",
                        "message": f"{task.title} is {label} for {team_name} and assigned to {assignee_name}. Due date: {task.due_date.isoformat()}.",
                        "display_date": task.due_date,
                        "date_prefix": "Due",
                        "notification_type": task.deadline_state,
                    }
                )

        if task.is_review_pending and task.reviewer_id == request.user.id:
            requester_name = task.assigned_to.username if task.assigned_to else "A teammate"
            alerts.append(
                {
                    "title": f"Review requested: {task.title}",
                    "message": f"{requester_name} asked you to review {task.title}.",
                    "display_date": task.review_requested_at.date() if task.review_requested_at else today,
                    "date_prefix": "Requested",
                    "notification_type": "review_requested",
                }
            )

        if task.assigned_to_id == request.user.id and task.review_state == "changes_requested":
            reviewer_name = task.reviewed_by.username if task.reviewed_by else "Your reviewer"
            alerts.append(
                {
                    "title": f"Review feedback: {task.title}",
                    "message": f"{reviewer_name} requested changes. {task.review_feedback}",
                    "display_date": task.reviewed_at.date() if task.reviewed_at else today,
                    "date_prefix": "Updated",
                    "notification_type": "changes_requested",
                }
            )

        if task.assigned_to_id == request.user.id and task.review_state == "approved":
            reviewer_name = task.reviewed_by.username if task.reviewed_by else "Your reviewer"
            alerts.append(
                {
                    "title": f"Review approved: {task.title}",
                    "message": f"{reviewer_name} approved this task. You can now mark it done.",
                    "display_date": task.reviewed_at.date() if task.reviewed_at else today,
                    "date_prefix": "Updated",
                    "notification_type": "approved",
                }
            )

    return {
        "notification_unread_count": len(alerts),
        "recent_notifications": alerts[:5],
    }
