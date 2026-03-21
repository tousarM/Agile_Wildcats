from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.utils.html import format_html
from .models import Profile, Task, TaskUpdate

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'role', 'team')
    search_fields = ('name', 'role', 'team')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'colored_status', 'due_date', 'assigned_to', 'updated_at')
    list_filter = ('status', 'due_date', 'updated_at')
    search_fields = ('title', 'description')

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
