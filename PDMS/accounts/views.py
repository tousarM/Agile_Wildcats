from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .forms import RegisterForm, TaskForm   # include TaskForm for tasks
from .models import Profile, Task, TaskUpdate


def _get_profile(user):
    return Profile.objects.get(user=user)


def _is_manager(profile):
    return 'manager' in profile.role.lower()


def _assignable_user_queryset():
    return User.objects.filter(is_active=True).order_by('username')


def _can_update_task(user, is_manager, task):
    return is_manager or task.assigned_to_id == user.id


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    'name': form.cleaned_data['name'],
                    'role': form.cleaned_data['role'],
                    'team': form.cleaned_data['team'],
                },
            )
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('welcome')   # Dashboard is now welcome
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    return render(request, 'login.html')


@login_required(login_url='login')
def welcome(request):
    # Treat welcome as the dashboard
    profile = _get_profile(request.user)
    return render(request, 'welcome.html', {
        'user': request.user,
        'name': profile.name,
        'role': profile.role,
        'team': profile.team
    })


@login_required(login_url='login')
def task_page(request):
    profile = _get_profile(request.user)
    is_manager = _is_manager(profile)
    assignable_users = _assignable_user_queryset()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_assignment':
            if not is_manager:
                raise PermissionDenied

            task = get_object_or_404(Task, pk=request.POST.get('task_id'))
            assigned_to_id = request.POST.get('assigned_to')
            previous_assignee = task.assigned_to
            task.assigned_to = assignable_users.filter(pk=assigned_to_id).first() if assigned_to_id else None
            task.save()

            if previous_assignee != task.assigned_to:
                if task.assigned_to:
                    note = f"{TaskUpdate.SYSTEM_ASSIGNED_PREFIX}{task.assigned_to.username}."
                else:
                    note = TaskUpdate.SYSTEM_UNASSIGNED_NOTE

                TaskUpdate.objects.create(
                    task=task,
                    author=request.user,
                    status=task.status,
                    status_changed=False,
                    previous_status=None,
                    previous_assignee=previous_assignee.username if previous_assignee else None,
                    current_assignee=task.assigned_to.username if task.assigned_to else None,
                    note=note,
                )

            return redirect('task_page')

        if action == 'update_progress':
            task = get_object_or_404(Task, pk=request.POST.get('task_id'))

            if not _can_update_task(request.user, is_manager, task):
                raise PermissionDenied

            new_status = request.POST.get('status', task.status)
            note = request.POST.get('note', '').strip()
            attachment = request.FILES.get('attachment')
            valid_statuses = {choice[0] for choice in Task.STATUS_CHOICES}

            if new_status not in valid_statuses:
                raise PermissionDenied

            previous_status = task.status
            task.status = new_status
            task.save()

            if note or previous_status != new_status or attachment:
                TaskUpdate.objects.create(
                    task=task,
                    author=request.user,
                    status=task.status,
                    status_changed=previous_status != new_status,
                    previous_status=previous_status if previous_status != new_status else None,
                    previous_assignee=None,
                    current_assignee=None,
                    note=note,
                    attachment=attachment,
                )

            return redirect('task_page')

        form = TaskForm(
            request.POST,
            request.FILES,
            can_assign=is_manager,
            assignable_users=assignable_users,
        )
        if form.is_valid():
            task = form.save(commit=False)
            if not is_manager:
                task.assigned_to = request.user
            task.save()

            TaskUpdate.objects.create(
                task=task,
                author=request.user,
                status=task.status,
                status_changed=False,
                previous_status=None,
                previous_assignee=None,
                current_assignee=None,
                note=TaskUpdate.SYSTEM_CREATED_NOTE,
            )

            if is_manager and task.assigned_to:
                TaskUpdate.objects.create(
                    task=task,
                    author=request.user,
                    status=task.status,
                    status_changed=False,
                    previous_status=None,
                    previous_assignee=None,
                    current_assignee=task.assigned_to.username,
                    note=f"{TaskUpdate.SYSTEM_ASSIGNED_PREFIX}{task.assigned_to.username}.",
                )

            return redirect('task_page')
    else:
        form = TaskForm(can_assign=is_manager, assignable_users=assignable_users)

    tasks = Task.objects.select_related('assigned_to').prefetch_related('updates__author')
    if not is_manager:
        tasks = tasks.filter(assigned_to=request.user)

    return render(request, 'tasks.html', {
        'form': form,
        'tasks': tasks.order_by('due_date', 'title'),
        'is_manager': is_manager,
        'assignable_users': assignable_users,
        'status_choices': Task.STATUS_CHOICES,
        'current_user_id': request.user.id,
    })


@login_required(login_url='login')
def profile_dashboard(request):
    # Full user profile dashboard
    profile = _get_profile(request.user)
    tasks = Task.objects.filter(assigned_to=request.user).select_related('assigned_to').prefetch_related('updates__author')

    return render(request, "profile_dashboard.html", {
        "profile": profile,
        "tasks": tasks.order_by('due_date', 'title'),
    })


def logout_view(request):
    logout(request)
    return redirect('login')


def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        # Mohammed will add logic to handle password reset
        return redirect('login')
    return render(request, 'forgot_password.html')
