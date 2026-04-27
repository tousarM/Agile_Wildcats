def can_delete_task(profile, task):
    if not profile or not task:
        return False

    return profile.role.lower() == "manager" or task.assigned_to_id == profile.user_id
