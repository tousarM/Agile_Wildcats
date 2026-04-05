from django.contrib import admin
from django.utils.html import format_html
from .models import Profile, Sprint, Task, TaskUpdate, Team, TeamInvite

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'role', 'team')
    search_fields = ('name', 'role', 'user__username', 'team__name')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'item_type',
        'priority',
        'backlog_state',
        'colored_status',
        'assigned_to',
        'sprint',
        'team',
        'updated_at',
    )
    list_filter = ('item_type', 'priority', 'backlog_state', 'status', 'sprint', 'due_date', 'updated_at')
    search_fields = ('title', 'description', 'acceptance_criteria', 'assigned_to__username', 'team__name', 'sprint__name')

    def colored_status(self, obj):
        colors = {
            'todo': 'red',
            'in_progress': 'orange',
            'done': 'green'
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    colored_status.admin_order_field = 'status'
    colored_status.short_description = 'Status'


@admin.register(TaskUpdate)
class TaskUpdateAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('task__title', 'note', 'author__username')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'start_date', 'end_date')
    search_fields = ('name', 'team__name')


@admin.register(TeamInvite)
class TeamInviteAdmin(admin.ModelAdmin):
    list_display = ('team', 'sender', 'recipient', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('team__name', 'sender__username', 'recipient__username')
