import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.models.signals import post_save
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.test import TransactionTestCase
from django.test import override_settings
from django.urls import reverse

from .models import Profile, Sprint, Task, TaskUpdate, Team
from .signals import ensure_user_profile


class TaskAndBacklogTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media_root = Path(__file__).resolve().parents[1] / "test_media"
        cls._temp_media_root.mkdir(exist_ok=True)
        cls._media_override = override_settings(MEDIA_ROOT=str(cls._temp_media_root))
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._temp_media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.team = Team.objects.create(name="Alpha")
        self.manager = self._create_user("manager1", "manager", "Manager One")
        self.developer = self._create_user("dev1", "member", "Dev One")
        self.other_developer = self._create_user("dev2", "member", "Dev Two")
        self.general_user = self._create_user("member1", "member", "Member One")

    def _create_user(self, username, role, name):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass123",
        )
        profile = user.profile
        profile.name = name
        profile.role = role
        profile.team = self.team
        profile.email = user.email
        profile.save()
        return user

    def _create_task(self, **overrides):
        defaults = {
            "title": "Sample Task",
            "description": "Sample description",
            "status": "todo",
            "team": self.team,
            "priority": "medium",
            "backlog_state": "backlog",
            "item_type": "story",
            "acceptance_criteria": "",
            "assigned_to": None,
            "sprint": None,
        }
        defaults.update(overrides)
        return Task.objects.create(**defaults)

    def _create_sprint(self, **overrides):
        defaults = {
            "team": self.team,
            "name": "Sprint 1",
            "start_date": "2026-04-07",
            "end_date": "2026-04-18",
            "status": "planned",
        }
        defaults.update(overrides)
        return Sprint.objects.create(**defaults)

    def test_profile_is_created_for_new_user(self):
        user = User.objects.create_user(
            username="signaluser",
            email="signal@example.com",
            password="pass123",
        )

        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.email, "signal@example.com")

    def test_manager_can_assign_task_to_any_active_user(self):
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
        self.assertEqual(task.team, self.team)
        self.assertEqual(task.assigned_to, self.general_user)
        self.assertEqual(task.priority, "medium")
        self.assertEqual(task.backlog_state, "backlog")
        self.assertTrue(TaskUpdate.objects.filter(task=task, note="Task assigned to member1.").exists())

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Updates by manager1")
        self.assertContains(response, "Activity: Created the task.")
        self.assertContains(response, "Assignment:")
        self.assertContains(response, "Unassigned")
        self.assertContains(response, "member1.")

    def test_manager_reassignment_shows_previous_assignee_with_strikethrough(self):
        task = self._create_task(
            title="Reassign Me",
            description="Move ownership to a new person",
            assigned_to=self.developer,
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_assignment",
                "task_id": task.id,
                "assigned_to": self.general_user.id,
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.assigned_to, self.general_user)

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, '<del class="text-muted">dev1</del>')
        self.assertContains(response, "member1.")

    def test_manager_can_unassign_task_and_history_is_saved(self):
        task = self._create_task(
            title="Fix Bug",
            description="Investigate login issue",
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
        self.assertTrue(TaskUpdate.objects.filter(task=task, note="Task unassigned.").exists())

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Assignment:")
        self.assertContains(response, '<del class="text-muted">dev1</del>')
        self.assertContains(response, "Unassigned.")

    def test_manager_can_update_task_from_combined_task_form(self):
        task = self._create_task(
            title="Advance sprint work",
            description="Move this forward from the task page",
            assigned_to=self.developer,
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_task",
                "task_id": task.id,
                "assigned_to": self.general_user.id,
                "status": "in_progress",
                "note": "Picked up and started implementation.",
                "next": "task_page",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.assigned_to, self.general_user)
        self.assertEqual(task.status, "in_progress")

        update = TaskUpdate.objects.filter(task=task).latest("created_at")
        self.assertTrue(update.status_changed)
        self.assertEqual(update.previous_status, "todo")
        self.assertEqual(update.previous_assignee, "dev1")
        self.assertEqual(update.current_assignee, "member1")
        self.assertEqual(update.note, "Picked up and started implementation.")

    def test_manager_can_update_task_due_date_from_combined_task_form(self):
        task = self._create_task(
            title="Adjust due date",
            description="Manager needs to reschedule this task",
            assigned_to=self.developer,
            due_date=date(2026, 4, 20),
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_task",
                "task_id": task.id,
                "assigned_to": self.developer.id,
                "due_date": "2026-04-27",
                "status": "todo",
                "note": "Pushed back after planning review.",
                "next": "task_page",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.due_date, date(2026, 4, 27))

        update = TaskUpdate.objects.filter(task=task).latest("created_at")
        self.assertIn("Due date changed from 2026-04-20 to 2026-04-27.", update.note)
        self.assertIn("Pushed back after planning review.", update.note)

    def test_task_page_prefills_due_date_input_for_managers(self):
        task = self._create_task(
            title="Show existing due date",
            assigned_to=self.developer,
            due_date=date(2026, 4, 18),
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.get(reverse("task_page"))

        self.assertContains(
            response,
            f'id="due_date_{task.id}" type="date" name="due_date" value="2026-04-18"',
            html=False,
        )

    def test_task_page_renders_collapsible_activity_for_tasks_with_updates(self):
        task = self._create_task(
            title="Collapsible activity",
            assigned_to=self.general_user,
        )

        self.client.login(username="member1", password="pass123")
        self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_progress",
                "note": "Logged the first visible update.",
            },
        )

        response = self.client.get(reverse("task_page"))

        self.assertContains(response, 'data-bs-target="#task-activity-{}'.format(task.id), html=False)
        self.assertContains(response, 'id="task-activity-{}" class="collapse mt-3"'.format(task.id), html=False)
        self.assertContains(response, "Discussion &amp; Activity")
        self.assertContains(response, "Logged the first visible update.")

    def test_dashboard_uses_role_display_label(self):
        self.client.login(username="manager1", password="pass123")

        response = self.client.get(reverse("profile_dashboard"))

        self.assertContains(response, "<strong>Role:</strong> Manager", html=False)
        self.assertNotContains(response, "<strong>Role:</strong> manager", html=False)

    def test_manager_can_delete_task_item(self):
        task = self._create_task(
            title="Delete me from tasks",
            assigned_to=self.developer,
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "delete_task",
                "task_id": task.id,
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_assigned_user_can_update_progress_and_see_it_after_relogin(self):
        task = self._create_task(
            title="Frontend Polish",
            description="Tighten spacing and states",
            assigned_to=self.general_user,
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_progress",
                "note": "Working through the remaining styling issues.",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=task,
                author=self.general_user,
                status="in_progress",
                note="Working through the remaining styling issues.",
            ).exists()
        )
        update = TaskUpdate.objects.get(task=task, author=self.general_user)
        self.assertEqual(update.previous_status, "todo")

        self.client.logout()
        self.client.login(username="member1", password="pass123")
        response = self.client.get(reverse("task_page"))

        self.assertContains(response, "Frontend Polish")
        self.assertContains(response, "In Progress")
        self.assertContains(response, "Updates by member1")
        self.assertContains(response, '<del class="text-muted">To Do</del>')
        self.assertContains(response, "Note: Working through the remaining styling issues.")

        dashboard_response = self.client.get(reverse("profile_dashboard"))
        self.assertContains(dashboard_response, "Updates by member1")
        self.assertContains(dashboard_response, '<del class="text-muted">To Do</del>')
        self.assertContains(dashboard_response, "Note: Working through the remaining styling issues.")

    def test_multiple_progress_notes_are_logged_for_the_same_task(self):
        task = self._create_task(
            title="Sprint Story",
            description="Track implementation discussion",
            assigned_to=self.general_user,
        )

        self.client.login(username="member1", password="pass123")
        first_response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_progress",
                "note": "Started implementation and created the base view.",
            },
        )
        second_response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_progress",
                "note": "Completed the form wiring and began testing.",
            },
        )

        self.assertRedirects(first_response, reverse("task_page"))
        self.assertRedirects(second_response, reverse("task_page"))
        self.assertEqual(
            TaskUpdate.objects.filter(task=task, author=self.general_user).count(),
            2,
        )

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Note: Started implementation and created the base view.")
        self.assertContains(response, "Note: Completed the form wiring and began testing.")
        self.assertContains(response, '<del class="text-muted">To Do</del>')

    def test_progress_update_can_include_attachment(self):
        task = self._create_task(
            title="Artifact Review",
            description="Upload progress evidence",
            assigned_to=self.general_user,
        )
        attachment = SimpleUploadedFile(
            "progress-log.txt",
            b"latest progress details",
            content_type="text/plain",
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "todo",
                "note": "Attached the latest log file.",
                "attachment": attachment,
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        update = TaskUpdate.objects.get(task=task, author=self.general_user)
        self.assertTrue(update.attachment.name.endswith("progress-log.txt"))

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Note: Attached the latest log file.")
        self.assertContains(response, "Attachment:")
        self.assertContains(response, "progress-log.txt")

        dashboard_response = self.client.get(reverse("profile_dashboard"))
        self.assertContains(dashboard_response, "Attachment:")
        self.assertContains(dashboard_response, "progress-log.txt")

    def test_note_only_progress_update_does_not_claim_status_changed(self):
        task = self._create_task(
            title="Backlog Review",
            description="Capture backlog notes without changing state",
            assigned_to=self.general_user,
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "todo",
                "note": "Added acceptance criteria details.",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        update = TaskUpdate.objects.get(task=task, author=self.general_user)
        self.assertFalse(update.status_changed)
        self.assertIsNone(update.previous_status)

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Updates by member1")
        self.assertContains(response, "Note: Added acceptance criteria details.")
        self.assertNotContains(response, "To Do</del> -> To Do")

    def test_status_change_without_note_shows_only_status_line(self):
        task = self._create_task(
            title="Plain Status Update",
            description="Move the task without a note",
            assigned_to=self.general_user,
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_progress",
                "note": "",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        response = self.client.get(reverse("task_page"))
        self.assertContains(response, '<del class="text-muted">To Do</del>')
        self.assertContains(response, "In Progress")

    def test_assignee_cannot_mark_done_without_review_approval(self):
        task = self._create_task(
            title="Needs review first",
            assigned_to=self.general_user,
            status="in_progress",
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "done",
                "note": "",
            },
            follow=True,
        )

        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")
        self.assertContains(response, "must be approved by another teammate before it can be marked done")

    def test_assignee_can_request_review_from_another_teammate(self):
        task = self._create_task(
            title="Request review",
            assigned_to=self.general_user,
            status="in_progress",
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_review",
                "reviewer": self.developer.id,
                "note": "Ready for review.",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.status, "in_review")
        self.assertEqual(task.review_state, "requested")
        self.assertEqual(task.reviewer, self.developer)

        update = TaskUpdate.objects.filter(task=task).latest("created_at")
        self.assertIn("Review requested from dev1.", update.note)
        self.assertIn("Ready for review.", update.note)

    def test_reviewer_can_request_changes_and_owner_can_re_request_review(self):
        task = self._create_task(
            title="Review changes",
            assigned_to=self.general_user,
            status="in_progress",
        )

        self.client.login(username="member1", password="pass123")
        self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_review",
                "reviewer": self.developer.id,
                "note": "Initial review request.",
            },
        )

        self.client.logout()
        self.client.login(username="dev1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "review_task",
                "task_id": task.id,
                "review_decision": "changes_requested",
                "review_feedback": "Need stronger tests before this is ready.",
                "next": "task_page",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")
        self.assertEqual(task.review_state, "changes_requested")
        self.assertEqual(task.review_feedback, "Need stronger tests before this is ready.")

        self.client.logout()
        self.client.login(username="member1", password="pass123")
        second_response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_review",
                "reviewer": self.other_developer.id,
                "note": "Addressed the requested changes.",
            },
        )

        self.assertRedirects(second_response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.status, "in_review")
        self.assertEqual(task.review_state, "requested")
        self.assertEqual(task.reviewer, self.other_developer)

    def test_assignee_can_mark_done_after_review_approval(self):
        task = self._create_task(
            title="Ready to close",
            assigned_to=self.general_user,
            status="in_progress",
        )

        self.client.login(username="member1", password="pass123")
        self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "in_review",
                "reviewer": self.developer.id,
                "note": "Please approve this.",
            },
        )

        self.client.logout()
        self.client.login(username="dev1", password="pass123")
        self.client.post(
            reverse("task_page"),
            {
                "action": "review_task",
                "task_id": task.id,
                "review_decision": "approve",
                "review_feedback": "",
                "next": "task_page",
            },
        )

        self.client.logout()
        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "done",
                "note": "",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.status, "done")
        self.assertEqual(task.review_state, "approved")
        self.assertEqual(task.reviewed_by, self.developer)

    def test_manager_can_bypass_review_and_mark_done(self):
        task = self._create_task(
            title="Manager override",
            assigned_to=self.developer,
            status="in_progress",
        )

        self.client.login(username="manager1", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_task",
                "task_id": task.id,
                "assigned_to": self.developer.id,
                "status": "done",
                "reviewer": self.general_user.id,
                "note": "Closing this with manager approval.",
                "next": "task_page",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        task.refresh_from_db()
        self.assertEqual(task.status, "done")
        self.assertEqual(task.review_state, "approved")
        self.assertEqual(task.reviewed_by, self.manager)

    def test_task_without_updates_shows_empty_activity_message(self):
        self._create_task(
            title="Fresh Task",
            description="No updates have been logged yet",
            assigned_to=self.developer,
        )

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("task_page"))

        self.assertContains(response, "No discussion or activity yet.")
        self.assertNotContains(response, "Discussion &amp; Activity")

    def test_unrelated_user_cannot_update_someone_elses_task_progress(self):
        task = self._create_task(
            title="API Cleanup",
            description="Refactor the serializers",
            assigned_to=self.developer,
        )

        self.client.login(username="dev2", password="pass123")
        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_progress",
                "task_id": task.id,
                "status": "done",
                "note": "Tried to update another user's task.",
            },
        )

        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.status, "todo")

    def test_user_only_sees_their_assigned_tasks(self):
        self._create_task(title="Visible Task", assigned_to=self.developer)
        self._create_task(title="Hidden Task", assigned_to=self.other_developer)
        self._create_task(title="Unassigned Task", assigned_to=None)

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("task_page"))

        self.assertContains(response, "Visible Task")
        self.assertNotContains(response, "Hidden Task")
        self.assertNotContains(response, "Unassigned Task")

    def test_manager_can_create_backlog_item_with_priority_and_acceptance_criteria(self):
        sprint = self._create_sprint(name="Sprint Alpha")
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("backlog_page"),
            {
                "action": "create_backlog_item",
                "title": "Plan login story",
                "item_type": "story",
                "priority": "high",
                "backlog_state": "selected_for_sprint",
                "sprint": sprint.id,
                "description": "Plan the login flow and implementation work.",
                "acceptance_criteria": "Users can sign in with a valid username and password.",
                "due_date": "2026-04-10",
                "assigned_to": self.developer.id,
            },
        )

        self.assertRedirects(response, reverse("backlog_page"))
        task = Task.objects.get(title="Plan login story")
        self.assertEqual(task.team, self.team)
        self.assertEqual(task.item_type, "story")
        self.assertEqual(task.priority, "high")
        self.assertEqual(task.backlog_state, "selected_for_sprint")
        self.assertEqual(task.sprint, sprint)
        self.assertEqual(
            task.acceptance_criteria,
            "Users can sign in with a valid username and password.",
        )

        backlog_response = self.client.get(reverse("backlog_page"))
        self.assertContains(backlog_response, "Work alert")

        sprint_response = self.client.get(reverse("sprint_board_page"))
        self.assertContains(sprint_response, "Plan login story")
        self.assertContains(sprint_response, "Sprint Alpha")
        self.assertContains(sprint_response, "High")
        self.assertContains(sprint_response, "Users can sign in with a valid username and password.")

    def test_manager_can_groom_backlog_item(self):
        sprint = self._create_sprint(name="Sprint Beta")
        task = self._create_task(
            title="Refine board experience",
            description="Initial description",
            assigned_to=None,
            acceptance_criteria="Original criteria",
        )

        self.client.login(username="manager1", password="pass123")
        response = self.client.post(
            reverse("backlog_page"),
            {
                "action": "update_backlog_item",
                "task_id": task.id,
                "title": "Refine board experience",
                "item_type": "bug",
                "priority": "critical",
                "backlog_state": "selected_for_sprint",
                "sprint": sprint.id,
                "description": "Initial description with clarifications",
                "acceptance_criteria": "Board updates render correctly after saving.",
                "due_date": "2026-04-12",
                "assigned_to": self.general_user.id,
            },
        )

        self.assertRedirects(response, reverse("backlog_page"))
        task.refresh_from_db()
        self.assertEqual(task.item_type, "bug")
        self.assertEqual(task.priority, "critical")
        self.assertEqual(task.backlog_state, "selected_for_sprint")
        self.assertEqual(task.sprint, sprint)
        self.assertEqual(task.assigned_to, self.general_user)
        self.assertEqual(task.acceptance_criteria, "Board updates render correctly after saving.")

        update = TaskUpdate.objects.filter(task=task).exclude(note=TaskUpdate.SYSTEM_CREATED_NOTE).latest("created_at")
        self.assertIn("Priority changed from Medium to Critical.", update.note)
        self.assertIn("Backlog state moved from Backlog to Selected for Sprint.", update.note)
        self.assertIn("Sprint changed from Product Backlog to Sprint Beta.", update.note)
        self.assertIn("Acceptance criteria updated.", update.note)
        self.assertEqual(update.current_assignee, "member1")

    def test_manager_can_delete_backlog_item(self):
        task = self._create_task(title="Delete me from backlog")
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("backlog_page"),
            {
                "action": "delete_backlog_item",
                "task_id": task.id,
            },
        )

        self.assertRedirects(response, reverse("backlog_page"))
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_manager_can_create_sprint(self):
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "create_sprint",
                "name": "Release Sprint",
                "start_date": "2026-04-14",
                "end_date": "2026-04-28",
                "status": "planned",
            },
        )

        self.assertRedirects(response, reverse("sprint_board_page"))
        sprint = Sprint.objects.get(name="Release Sprint")
        self.assertEqual(sprint.team, self.team)
        self.assertEqual(sprint.status, "planned")

    def test_manager_can_update_sprint_state_from_dropdown(self):
        sprint = self._create_sprint(name="Release Sprint")
        self.client.login(username="manager1", password="pass123")

        active_response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "update_sprint_status",
                "sprint_id": sprint.id,
                "status": "active",
            },
        )
        self.assertRedirects(active_response, reverse("sprint_board_page"))
        sprint.refresh_from_db()
        self.assertEqual(sprint.status, "active")

        close_response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "update_sprint_status",
                "sprint_id": sprint.id,
                "status": "closed",
            },
        )
        self.assertRedirects(close_response, reverse("sprint_board_page"))
        sprint.refresh_from_db()
        self.assertEqual(sprint.status, "closed")

        reopen_response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "update_sprint_status",
                "sprint_id": sprint.id,
                "status": "active",
            },
        )
        self.assertRedirects(reopen_response, reverse("sprint_board_page"))
        sprint.refresh_from_db()
        self.assertEqual(sprint.status, "active")

    def test_manager_can_update_sprint_dates(self):
        sprint = self._create_sprint(
            name="Schedule Sprint",
            start_date="2026-04-07",
            end_date="2026-04-18",
            status="planned",
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "update_sprint_status",
                "sprint_id": sprint.id,
                "start_date": "2026-04-10",
                "end_date": "2026-04-24",
                "status": "active",
            },
        )

        self.assertRedirects(response, reverse("sprint_board_page"))
        sprint.refresh_from_db()
        self.assertEqual(sprint.start_date, date(2026, 4, 10))
        self.assertEqual(sprint.end_date, date(2026, 4, 24))
        self.assertEqual(sprint.status, "active")

    def test_manager_can_delete_sprint_and_return_tickets_to_backlog(self):
        sprint = self._create_sprint(name="Disposable Sprint", status="active")
        task = self._create_task(
            title="Return me to backlog",
            sprint=sprint,
            backlog_state="selected_for_sprint",
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "delete_sprint",
                "sprint_id": sprint.id,
            },
        )

        self.assertRedirects(response, reverse("sprint_board_page"))
        self.assertFalse(Sprint.objects.filter(id=sprint.id).exists())

        task.refresh_from_db()
        self.assertIsNone(task.sprint)
        self.assertEqual(task.backlog_state, "backlog")

        backlog_response = self.client.get(reverse("backlog_page"))
        self.assertContains(backlog_response, "Return me to backlog")

        update = TaskUpdate.objects.filter(task=task).latest("created_at")
        self.assertEqual(update.note, "Sprint changed from Disposable Sprint to Product Backlog.")

    def test_manager_can_remove_single_task_from_sprint(self):
        sprint = self._create_sprint(name="Focused Sprint", status="active")
        task = self._create_task(
            title="Move just me back",
            sprint=sprint,
            backlog_state="selected_for_sprint",
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "remove_task_from_sprint",
                "task_id": task.id,
                "selected_sprint": str(sprint.id),
            },
        )

        self.assertRedirects(response, f"{reverse('sprint_board_page')}?sprint={sprint.id}")
        task.refresh_from_db()
        self.assertIsNone(task.sprint)
        self.assertEqual(task.backlog_state, "backlog")

        backlog_response = self.client.get(reverse("backlog_page"))
        self.assertContains(backlog_response, "Move just me back")

        sprint_response = self.client.get(reverse("sprint_board_page"), {"sprint": str(sprint.id)})
        self.assertNotContains(sprint_response, "Move just me back")

        update = TaskUpdate.objects.filter(task=task).latest("created_at")
        self.assertEqual(update.note, "Sprint changed from Focused Sprint to Product Backlog.")

    def test_assigning_backlog_ticket_to_sprint_moves_it_to_sprint_board(self):
        sprint = self._create_sprint(name="Planning Sprint")
        task = self._create_task(title="Move me into sprint")
        self.client.login(username="manager1", password="pass123")

        response = self.client.post(
            reverse("backlog_page"),
            {
                "action": "update_backlog_item",
                "task_id": task.id,
                "title": task.title,
                "item_type": task.item_type,
                "priority": task.priority,
                "backlog_state": task.backlog_state,
                "sprint": sprint.id,
                "description": task.description,
                "acceptance_criteria": task.acceptance_criteria,
                "due_date": "",
                "assigned_to": "",
            },
        )

        self.assertRedirects(response, reverse("backlog_page"))
        task.refresh_from_db()
        self.assertEqual(task.sprint, sprint)
        self.assertEqual(task.backlog_state, "selected_for_sprint")

        backlog_response = self.client.get(reverse("backlog_page"))
        self.assertNotContains(backlog_response, "Move me into sprint")

        sprint_response = self.client.get(reverse("sprint_board_page"))
        self.assertContains(sprint_response, "Planning Sprint")
        self.assertContains(sprint_response, "Move me into sprint")

    def test_sprint_board_can_be_filtered_to_single_sprint(self):
        first_sprint = self._create_sprint(name="Sprint Alpha")
        second_sprint = self._create_sprint(
            name="Sprint Beta",
            start_date="2026-04-21",
            end_date="2026-05-02",
        )
        self._create_task(
            title="Alpha ticket",
            sprint=first_sprint,
            backlog_state="selected_for_sprint",
        )
        self._create_task(
            title="Beta ticket",
            sprint=second_sprint,
            backlog_state="selected_for_sprint",
        )

        self.client.login(username="manager1", password="pass123")
        response = self.client.get(
            reverse("sprint_board_page"),
            {"sprint": str(second_sprint.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["sprints"]), 1)
        self.assertEqual(response.context["sprints"][0].id, second_sprint.id)
        self.assertContains(response, "View by Sprint")
        self.assertContains(response, "Sprint Beta")
        self.assertContains(response, "Beta ticket")
        self.assertNotContains(response, "Alpha ticket")
        self.assertContains(response, "Clear Filters")

    def test_board_tab_can_be_filtered_to_single_sprint(self):
        first_sprint = self._create_sprint(name="Board Sprint Alpha")
        second_sprint = self._create_sprint(
            name="Board Sprint Beta",
            start_date="2026-04-21",
            end_date="2026-05-02",
        )
        self._create_task(
            title="Alpha board ticket",
            sprint=first_sprint,
            backlog_state="selected_for_sprint",
            status="todo",
        )
        self._create_task(
            title="Beta board ticket",
            sprint=second_sprint,
            backlog_state="selected_for_sprint",
            status="in_progress",
        )

        self.client.login(username="manager1", password="pass123")
        response = self.client.get(
            reverse("boards"),
            {"sprint": str(second_sprint.id)},
        )

        filtered_titles = [
            task.title
            for _, _, column_tasks in response.context["board_columns"]
            for task in column_tasks
        ]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View by Sprint")
        self.assertContains(response, "Track tickets by workflow state for Board Sprint Beta.")
        self.assertContains(response, "Beta board ticket")
        self.assertNotContains(response, "Alpha board ticket")
        self.assertIn("Beta board ticket", filtered_titles)
        self.assertNotIn("Alpha board ticket", filtered_titles)
        self.assertContains(response, "Clear Filters")

    def test_backlog_page_can_search_items(self):
        self._create_task(
            title="Needle backlog item",
            description="Searchable backlog work",
            assigned_to=self.developer,
        )
        self._create_task(
            title="Haystack backlog item",
            description="Unrelated backlog work",
            assigned_to=self.general_user,
        )

        self.client.login(username="manager1", password="pass123")
        response = self.client.get(
            reverse("backlog_page"),
            {"q": "Needle"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Backlog")
        self.assertContains(response, "Needle backlog item")
        self.assertNotContains(response, "Haystack backlog item")
        self.assertEqual(response.context["search_query"], "Needle")
        self.assertEqual(response.context["filtered_item_count"], 1)

    def test_board_page_can_search_tasks_without_any_sprints(self):
        self._create_task(
            title="Needle board task",
            description="Find me on the board",
            assigned_to=self.developer,
            status="todo",
        )
        self._create_task(
            title="Haystack board task",
            description="Leave me out of the results",
            assigned_to=self.general_user,
            status="in_progress",
        )

        self.client.login(username="manager1", password="pass123")
        response = self.client.get(
            reverse("boards"),
            {"q": "Needle"},
        )

        filtered_titles = [
            task.title
            for _, _, column_tasks in response.context["board_columns"]
            for task in column_tasks
        ]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Board")
        self.assertContains(response, "Needle board task")
        self.assertNotContains(response, "Haystack board task")
        self.assertEqual(response.context["search_query"], "Needle")
        self.assertIn("Needle board task", filtered_titles)
        self.assertNotIn("Haystack board task", filtered_titles)

    def test_member_can_view_sprint_board_but_cannot_manage_sprints(self):
        sprint = self._create_sprint(name="Visible Sprint")
        self._create_task(title="Sprint board ticket", sprint=sprint, backlog_state="selected_for_sprint")

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("sprint_board_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Sprint")
        self.assertContains(response, "Sprint board ticket")
        self.assertContains(response, "View-only sprint access")

        create_response = self.client.post(
            reverse("sprint_board_page"),
            {
                "action": "create_sprint",
                "name": "Blocked Sprint",
                "start_date": "2026-05-01",
                "end_date": "2026-05-15",
                "status": "planned",
            },
        )
        self.assertEqual(create_response.status_code, 403)

    def test_member_can_view_backlog_but_cannot_groom_it(self):
        task = self._create_task(
            title="Backlog visible item",
            priority="high",
            backlog_state="selected_for_sprint",
            assigned_to=self.developer,
        )

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("backlog_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, task.title)
        self.assertContains(response, "View-only backlog access")

        post_response = self.client.post(
            reverse("backlog_page"),
            {
                "action": "update_backlog_item",
                "task_id": task.id,
                "title": task.title,
                "item_type": task.item_type,
                "priority": "critical",
                "backlog_state": task.backlog_state,
                "description": task.description,
                "acceptance_criteria": task.acceptance_criteria,
                "due_date": "",
                "assigned_to": task.assigned_to_id,
            },
        )
        self.assertEqual(post_response.status_code, 403)


class NotificationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media_root = Path(__file__).resolve().parents[1] / "test_media_notifications"
        cls._temp_media_root.mkdir(exist_ok=True)
        cls._media_override = override_settings(MEDIA_ROOT=str(cls._temp_media_root))
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._temp_media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.team = Team.objects.create(name="Notifications")
        self.manager = self._create_user("manager1", "manager", "Manager One")
        self.member = self._create_user("member1", "member", "Member One")

    def _create_user(self, username, role, name):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass123",
        )
        profile = user.profile
        profile.name = name
        profile.role = role
        profile.team = self.team
        profile.email = user.email
        profile.save()
        return user

    def _create_task(self, **overrides):
        defaults = {
            "title": "Sample Notification Task",
            "description": "Sample description",
            "status": "todo",
            "team": self.team,
            "priority": "medium",
            "backlog_state": "backlog",
            "item_type": "story",
            "acceptance_criteria": "",
            "assigned_to": self.member,
            "sprint": None,
        }
        defaults.update(overrides)
        return Task.objects.create(**defaults)

    @patch("accounts.context_processors.timezone.localdate", return_value=date(2026, 4, 18))
    def test_deadline_notification_appears_in_the_navbar(self, mock_localdate):
        self._create_task(
            title="Deadline Reminder",
            due_date=date(2026, 4, 19),
            assigned_to=self.member,
        )
        self.client.login(username="member1", password="pass123")

        response = self.client.get(reverse("welcome"))

        self.assertContains(response, "Work alert")
        self.assertContains(response, "🔔")
        self.assertContains(response, "Deadline reminder: Deadline Reminder")
        self.assertContains(response, "Due Apr 19, 2026")

    @patch("accounts.context_processors.timezone.localdate", return_value=date(2026, 4, 18))
    def test_team_deadline_shows_even_when_assigned_to_someone_else(self, mock_localdate):
        self._create_task(
            title="Team Deadline",
            due_date=date(2026, 4, 19),
            assigned_to=self.member,
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.get(reverse("welcome"))

        self.assertContains(response, "Deadline reminder: Team Deadline")
        self.assertContains(response, "assigned to member1")

    def test_dashboard_can_edit_email(self):
        self.client.login(username="member1", password="pass123")
        response = self.client.post(
            reverse("profile_dashboard"),
            {
                "email": "new-member@example.com",
            },
        )

        self.assertRedirects(response, reverse("profile_dashboard"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "new-member@example.com")
        self.assertEqual(Profile.objects.get(user=self.member).email, "new-member@example.com")

    @patch("accounts.context_processors.timezone.localdate", return_value=date(2026, 4, 18))
    def test_completed_task_disappears_from_the_navbar(self, mock_localdate):
        task = self._create_task(
            title="Finish the release note",
            due_date=date(2026, 4, 18),
            assigned_to=self.member,
        )
        self.client.login(username="manager1", password="pass123")
        self.client.get(reverse("welcome"))

        response = self.client.post(
            reverse("task_page"),
            {
                "action": "update_task",
                "task_id": task.id,
                "assigned_to": self.member.id,
                "status": "done",
                "note": "Wrapped up the last item.",
                "next": "task_page",
            },
        )

        self.assertRedirects(response, reverse("task_page"))
        updated_response = self.client.get(reverse("welcome"))
        self.assertNotContains(updated_response, "Finish the release note")

    @patch("accounts.context_processors.timezone.localdate", return_value=date(2026, 4, 18))
    def test_review_request_notification_appears_for_reviewer(self, mock_localdate):
        self._create_task(
            title="Review my work",
            due_date=date(2026, 4, 20),
            assigned_to=self.member,
            reviewer=self.manager,
            status="in_review",
            review_state="requested",
        )
        self.client.login(username="manager1", password="pass123")

        response = self.client.get(reverse("welcome"))

        self.assertContains(response, "Review requested: Review my work")
        self.assertContains(response, "asked you to review Review my work")

    def test_dashboard_shows_review_sections(self):
        Task.objects.create(
            title="Awaiting my review",
            description="",
            status="in_review",
            team=self.team,
            assigned_to=self.member,
            reviewer=self.manager,
            review_state="requested",
        )
        Task.objects.create(
            title="Feedback received",
            description="",
            status="in_progress",
            team=self.team,
            assigned_to=self.member,
            reviewer=self.manager,
            reviewed_by=self.manager,
            review_state="changes_requested",
            review_feedback="Please add one more validation case.",
        )
        Task.objects.create(
            title="Ready to finish",
            description="",
            status="in_review",
            team=self.team,
            assigned_to=self.member,
            reviewer=self.manager,
            reviewed_by=self.manager,
            review_state="approved",
        )

        self.client.login(username="member1", password="pass123")
        response = self.client.get(reverse("profile_dashboard"))

        self.assertContains(response, "Feedback To Address")
        self.assertContains(response, "Feedback received")
        self.assertContains(response, "Ready To Finish")
        self.assertContains(response, "Ready to finish")

        self.client.logout()
        self.client.login(username="manager1", password="pass123")
        reviewer_response = self.client.get(reverse("profile_dashboard"))
        self.assertContains(reviewer_response, "Needs My Review")
        self.assertContains(reviewer_response, "Awaiting my review")

    @patch("accounts.context_processors.timezone.localdate", return_value=date(2026, 4, 18))
    def test_expired_task_is_marked_expired(self, mock_localdate):
        self._create_task(
            title="Late task",
            due_date=date(2026, 4, 17),
            assigned_to=self.member,
        )
        self.client.login(username="member1", password="pass123")

        response = self.client.get(reverse("boards"))

        self.assertContains(response, "Expired")


class TaskUpdateMigrationTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(ensure_user_profile, sender=User)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(ensure_user_profile, sender=User)
        super().tearDownClass()

    def test_previous_status_is_backfilled_for_existing_status_changes(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", "0008_taskupdate_status_changed")])
        old_apps = executor.loader.project_state([("accounts", "0008_taskupdate_status_changed")]).apps

        UserModel = old_apps.get_model("auth", "User")
        TaskModel = old_apps.get_model("accounts", "Task")
        TaskUpdateModel = old_apps.get_model("accounts", "TaskUpdate")

        user = UserModel.objects.create(username="legacyuser")
        task = TaskModel.objects.create(
            title="Legacy Task",
            description="Verify migration backfill",
            status="in_progress",
            assigned_to=user,
        )
        TaskUpdateModel.objects.create(
            task=task,
            author=user,
            status="todo",
            status_changed=False,
            note="Task created.",
        )
        TaskUpdateModel.objects.create(
            task=task,
            author=user,
            status="in_progress",
            status_changed=True,
            note="Legacy update",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", "0009_taskupdate_previous_status")])
        new_apps = executor.loader.project_state([("accounts", "0009_taskupdate_previous_status")]).apps
        MigratedTaskUpdate = new_apps.get_model("accounts", "TaskUpdate")

        migrated_update = MigratedTaskUpdate.objects.get(note="Legacy update")
        self.assertEqual(migrated_update.previous_status, "todo")

    def test_assignment_snapshot_is_backfilled_for_existing_assignment_updates(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", "0009_taskupdate_previous_status")])
        old_apps = executor.loader.project_state([("accounts", "0009_taskupdate_previous_status")]).apps

        UserModel = old_apps.get_model("auth", "User")
        TaskModel = old_apps.get_model("accounts", "Task")
        TaskUpdateModel = old_apps.get_model("accounts", "TaskUpdate")

        user = UserModel.objects.create(username="legacy_manager")
        task = TaskModel.objects.create(
            title="Legacy Assignment",
            description="Verify assignment backfill",
            status="todo",
            assigned_to=user,
        )
        TaskUpdateModel.objects.create(
            task=task,
            author=user,
            status="todo",
            status_changed=False,
            previous_status=None,
            note="Task assigned to dev1.",
        )
        TaskUpdateModel.objects.create(
            task=task,
            author=user,
            status="todo",
            status_changed=False,
            previous_status=None,
            note="Task assigned to member1.",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", "0010_taskupdate_assignment_snapshot")])
        new_apps = executor.loader.project_state([("accounts", "0010_taskupdate_assignment_snapshot")]).apps
        MigratedTaskUpdate = new_apps.get_model("accounts", "TaskUpdate")

        migrated_update = MigratedTaskUpdate.objects.get(note="Task assigned to member1.")
        self.assertEqual(migrated_update.previous_assignee, "dev1")
        self.assertEqual(migrated_update.current_assignee, "member1")
