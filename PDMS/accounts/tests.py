import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.test import TransactionTestCase
from django.test import override_settings
from django.urls import reverse

from .models import Profile, Task, TaskUpdate


class TaskProgressTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._temp_media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.manager = User.objects.create_user(username="manager1", password="pass123")
        self.developer = User.objects.create_user(username="dev1", password="pass123")
        self.other_developer = User.objects.create_user(username="dev2", password="pass123")
        self.general_user = User.objects.create_user(username="member1", password="pass123")

        Profile.objects.filter(user=self.manager).update(name="Manager One", role="Manager", team="Alpha")
        Profile.objects.filter(user=self.developer).update(name="Dev One", role="Developer", team="Alpha")
        Profile.objects.filter(user=self.other_developer).update(name="Dev Two", role="Developer", team="Alpha")
        Profile.objects.filter(user=self.general_user).update(name="Member One", role="User", team="Alpha")

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
        self.assertEqual(task.assigned_to, self.general_user)
        self.assertTrue(TaskUpdate.objects.filter(task=task, note="Task assigned to member1.").exists())

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Updates by manager1")
        self.assertContains(response, "Activity: Created the task.")
        self.assertContains(response, "Assignment:")
        self.assertContains(response, "Unassigned")
        self.assertContains(response, "→")
        self.assertContains(response, "member1.")

    def test_manager_reassignment_shows_previous_assignee_with_strikethrough(self):
        task = Task.objects.create(
            title="Reassign Me",
            description="Move ownership to a new person",
            status="todo",
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
        self.assertContains(response, "→")
        self.assertContains(response, "member1.")

    def test_manager_can_unassign_task_and_history_is_saved(self):
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
        self.assertTrue(TaskUpdate.objects.filter(task=task, note="Task unassigned.").exists())

        response = self.client.get(reverse("task_page"))
        self.assertContains(response, "Assignment:")
        self.assertContains(response, '<del class="text-muted">dev1</del>')
        self.assertContains(response, "→")
        self.assertContains(response, "Unassigned.")

    def test_assigned_user_can_update_progress_and_see_it_after_relogin(self):
        task = Task.objects.create(
            title="Frontend Polish",
            description="Tighten spacing and states",
            status="todo",
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
        self.assertContains(response, '<del class="text-muted">To Do</del> →')
        self.assertContains(response, "Note: Working through the remaining styling issues.")

        dashboard_response = self.client.get(reverse("profile_dashboard"))
        self.assertContains(dashboard_response, "Updates by member1")
        self.assertContains(dashboard_response, '<del class="text-muted">To Do</del> →')
        self.assertContains(dashboard_response, "Note: Working through the remaining styling issues.")

    def test_multiple_progress_notes_are_logged_for_the_same_task(self):
        task = Task.objects.create(
            title="Sprint Story",
            description="Track implementation discussion",
            status="todo",
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
        self.assertContains(response, '<del class="text-muted">To Do</del> →')

    def test_progress_update_can_include_attachment(self):
        task = Task.objects.create(
            title="Artifact Review",
            description="Upload progress evidence",
            status="todo",
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
        task = Task.objects.create(
            title="Backlog Review",
            description="Capture backlog notes without changing state",
            status="todo",
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
        self.assertNotContains(response, '<del class="text-muted">To Do</del> → To Do')

    def test_status_change_without_note_shows_only_status_line(self):
        task = Task.objects.create(
            title="Plain Status Update",
            description="Move the task without a note",
            status="todo",
            assigned_to=self.general_user,
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
        )

        self.assertRedirects(response, reverse("task_page"))
        response = self.client.get(reverse("task_page"))
        self.assertContains(response, '<del class="text-muted">To Do</del> →')
        self.assertContains(response, "Done")
        self.assertNotContains(response, "Note: Move the task without a note")

    def test_task_without_updates_shows_empty_activity_message(self):
        Task.objects.create(
            title="Fresh Task",
            description="No updates have been logged yet",
            status="todo",
            assigned_to=self.developer,
        )

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("task_page"))

        self.assertContains(response, "No discussion or activity yet.")
        self.assertNotContains(response, "Discussion & Activity")

    def test_unrelated_user_cannot_update_someone_elses_task_progress(self):
        task = Task.objects.create(
            title="API Cleanup",
            description="Refactor the serializers",
            status="todo",
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
        Task.objects.create(title="Visible Task", status="todo", assigned_to=self.developer)
        Task.objects.create(title="Hidden Task", status="todo", assigned_to=self.other_developer)
        Task.objects.create(title="Unassigned Task", status="todo", assigned_to=None)

        self.client.login(username="dev1", password="pass123")
        response = self.client.get(reverse("task_page"))

        self.assertContains(response, "Visible Task")
        self.assertNotContains(response, "Hidden Task")
        self.assertNotContains(response, "Unassigned Task")


class TaskUpdateMigrationTests(TransactionTestCase):
    reset_sequences = True

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
