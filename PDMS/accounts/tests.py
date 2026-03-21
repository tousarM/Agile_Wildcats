from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile, Task


class TaskAssignmentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager1", password="pass123")
        self.developer = User.objects.create_user(username="dev1", password="pass123")
        self.other_developer = User.objects.create_user(username="dev2", password="pass123")
        self.general_user = User.objects.create_user(username="member1", password="pass123")

        Profile.objects.filter(user=self.manager).update(name="Manager One", role="Manager", team="Alpha")
        Profile.objects.filter(user=self.developer).update(name="Dev One", role="Developer", team="Alpha")
        Profile.objects.filter(user=self.other_developer).update(name="Dev Two", role="Developer", team="Alpha")
        Profile.objects.filter(user=self.general_user).update(name="Member One", role="User", team="Alpha")

    def test_manager_can_assign_task_to_user_with_any_role(self):
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "create_task",
                "title": "Build API",
                "description": "Create the assignment endpoint",
                "due_date": "2026-03-25",
                "status": "todo",
                "assigned_to": self.general_user.id,
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task = Task.objects.get(title="Build API")
        self.assertEqual(task.assigned_to, self.general_user)

    def test_manager_can_unassign_task(self):
        task = Task.objects.create(
            title="Fix Bug",
            description="Investigate login issue",
            status="todo",
            assigned_to=self.developer,
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_assignment",
                "task_id": task.id,
                "assigned_to": "",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertIsNone(task.assigned_to)

    def test_developer_only_sees_their_assigned_tasks(self):
        Task.objects.create(title="Visible Task", status="todo", assigned_to=self.developer)
        Task.objects.create(title="Hidden Task", status="todo", assigned_to=self.other_developer)
        Task.objects.create(title="Unassigned Task", status="todo", assigned_to=None)

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("task_page"))

        self.assertContains(response, "Visible Task")
        self.assertNotContains(response, "Hidden Task")
        self.assertNotContains(response, "Unassigned Task")
