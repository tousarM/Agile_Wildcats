from django.urls import path
from . import views

urlpatterns = [
    path("", views.welcome, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("welcome/", views.welcome, name="welcome"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("tasks/", views.task_page, name="task_page"),   # <-- NEW added module
    path("dashboard/", views.profile_dashboard, name="profile_dashboard"), # <-- NEW added module

]

