from django.test import TestCase
from django.contrib.auth.models import User
from .models import Task

# Create your tests here

# -----------------------------
# Unit tests for PDMS accounts app
# -----------------------------

class UserModelTest(TestCase):
    # Test that a user can be created successfully
    def test_user_creation(self):
        user = User.objects.create_user(username="dev1", password="pass123")
        # Verify username is stored correctly
        self.assertEqual(user.username, "dev1")
        # Verify password hashing works
        self.assertTrue(user.check_password("pass123"))

class TaskModelTest(TestCase):
    # Test that a task can be created with all required fields
    def test_task_creation(self):
        # Create a user to assign the task to
        user = User.objects.create_user(username="dev1", password="pass123")

        # Create a task with title, description, due_date, status, and assigned_to
        task = Task.objects.create(
            title="Test Task",
            description="This is a sample task",
            due_date="2026-03-20",
            status="Backlog",
            assigned_to=user
        )

        # Verify task attributes are saved correctly
        self.assertEqual(task.title, "Test Task")
        self.assertEqual(task.status, "Backlog")
        self.assertEqual(task.assigned_to.username, "dev1")
        self.assertEqual(str(task.due_date), "2026-03-20")

class AuthViewsTest(TestCase):
    # Setup: create a test user for login
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass123")

    # Test login view with valid credentials
    def test_login_view(self):
        response = self.client.post("/login/", {"username": "tester", "password": "pass123"})
        # Expect redirect (status 302) after successful login
        self.assertEqual(response.status_code, 302)

    # Test register view with valid data
    def test_register_view(self):
        # Include all required fields (username, email, password1, password2)
        response = self.client.post("/register/", {
            "username": "newuser",
            "email": "newuser@example.com",   # add if required by your form
            "password1": "strongpass123",
            "password2": "strongpass123"
        })
        # Expect redirect (status 302) after successful registration
        self.assertEqual(response.status_code, 302)
