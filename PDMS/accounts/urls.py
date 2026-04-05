from django.urls import path
from . import views

urlpatterns = [
    path("", views.welcome, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("welcome/", views.welcome, name="welcome"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("backlog/", views.backlog_page, name="backlog_page"),
    path("tasks/", views.task_page, name="task_page"),   # <-- NEW added module
    path("dashboard/", views.profile_dashboard, name="profile_dashboard"), # <-- NEW added module
    path('team/', views.team_page, name='team_page'),
    path('team/create/', views.create_team, name='create_team'),
    path('invite/accept/<uuid:invite_id>/', views.accept_invite, name='accept_invite'),
    path('invite/reject/<uuid:invite_id>/', views.reject_invite, name='reject_invite'),
    path('team/remove/<int:user_id>/', views.remove_member, name='remove_member'),
    path('team/leave/', views.leave_team, name='leave_team'),
    path('team/delete/', views.delete_team, name='delete_team'),
]
