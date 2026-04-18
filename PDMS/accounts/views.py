from urllib import request
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Value, When
from .forms import (
    BacklogGroomForm,
    BacklogItemForm,
    CreateTeamForm,
    InviteForm,
    RegisterForm,
    SprintForm,
    SprintStatusForm,
    TaskForm,
)
from .models import Profile, Sprint, Task, TaskUpdate, Team, TeamInvite
from datetime import date, timedelta


def _get_profile(user):
    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={"email": user.email, "role": "member"},
    )

    if user.email and profile.email != user.email:
        profile.email = user.email
        profile.save(update_fields=["email"])

    return profile


def _is_manager(profile):
    return 'manager' in profile.role.lower()


def _can_update_task(user, is_manager, task):
    return is_manager or task.assigned_to_id == user.id


def _assignable_users_for_team(team):
    return User.objects.filter(profile__team=team, is_active=True).order_by('username')


def _available_sprints_for_team(team, include_closed=False):
    sprints = Sprint.objects.filter(team=team).order_by('start_date', 'name')
    if not include_closed:
        sprints = sprints.exclude(status='closed')
    return sprints


def _team_tasks(team):
    return (
        Task.objects.filter(team=team)
        .select_related('assigned_to')
        .select_related('sprint')
        .prefetch_related('updates__author')
    )


def _ordered_tasks(queryset):
    priority_rank = Case(
        When(priority='critical', then=Value(0)),
        When(priority='high', then=Value(1)),
        When(priority='medium', then=Value(2)),
        When(priority='low', then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )
    backlog_state_rank = Case(
        When(backlog_state='backlog', then=Value(0)),
        When(backlog_state='selected_for_sprint', then=Value(1)),
        When(backlog_state='ready_for_test', then=Value(2)),
        When(backlog_state='done', then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )
    return queryset.annotate(
        priority_rank=priority_rank,
        backlog_state_rank=backlog_state_rank,
    ).order_by('backlog_state_rank', 'priority_rank', 'due_date', 'title')


def _backlog_queryset(team):
    return _ordered_tasks(_team_tasks(team).filter(sprint__isnull=True))


def _sprint_queryset(team):
    status_rank = Case(
        When(status='active', then=Value(0)),
        When(status='planned', then=Value(1)),
        When(status='closed', then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    return Sprint.objects.filter(team=team).annotate(
        status_rank=status_rank,
    ).order_by('status_rank', 'start_date', 'name')


def _sync_task_backlog_state(task):
    if task.sprint_id and task.backlog_state == 'backlog':
        task.backlog_state = 'selected_for_sprint'
    elif not task.sprint_id and task.backlog_state == 'selected_for_sprint':
        task.backlog_state = 'backlog'


def _redirect_to_sprint_board(request, selected_sprint_id=""):
    if selected_sprint_id:
        return redirect(f"{request.path}?sprint={selected_sprint_id}")
    return redirect('sprint_board_page')


def _log_task_created(task, author):
    TaskUpdate.objects.create(
        task=task,
        author=author,
        status=task.status,
        status_changed=False,
        previous_status=None,
        previous_assignee=None,
        current_assignee=None,
        note=TaskUpdate.SYSTEM_CREATED_NOTE,
    )

    if task.assigned_to:
        TaskUpdate.objects.create(
            task=task,
            author=author,
            status=task.status,
            status_changed=False,
            previous_status=None,
            previous_assignee=None,
            current_assignee=task.assigned_to.username,
            note=f"{TaskUpdate.SYSTEM_ASSIGNED_PREFIX}{task.assigned_to.username}.",
        )


def _log_task_note(task, author, note):
    TaskUpdate.objects.create(
        task=task,
        author=author,
        status=task.status,
        status_changed=False,
        previous_status=None,
        previous_assignee=None,
        current_assignee=None,
        note=note,
    )


def _format_choice(choice_map, value, empty_label):
    if not value:
        return empty_label
    return choice_map.get(value, value)


def _format_sprint_name(sprint_name):
    return sprint_name or "Product Backlog"


def _build_backlog_change_note(original_values, task):
    item_type_choices = dict(Task.ITEM_TYPE_CHOICES)
    priority_choices = dict(Task.PRIORITY_CHOICES)
    backlog_state_choices = dict(Task.BACKLOG_STATE_CHOICES)
    changes = []

    if original_values["title"] != task.title:
        changes.append(f'Title updated from "{original_values["title"]}" to "{task.title}".')
    if original_values["item_type"] != task.item_type:
        changes.append(
            "Item type changed from "
            f'{_format_choice(item_type_choices, original_values["item_type"], "Unspecified")} '
            f'to {task.get_item_type_display()}.'
        )
    if original_values["priority"] != task.priority:
        changes.append(
            "Priority changed from "
            f'{_format_choice(priority_choices, original_values["priority"], "Unspecified")} '
            f'to {task.get_priority_display()}.'
        )
    if original_values["backlog_state"] != task.backlog_state:
        changes.append(
            "Backlog state moved from "
            f'{_format_choice(backlog_state_choices, original_values["backlog_state"], "Unspecified")} '
            f'to {task.get_backlog_state_display()}.'
        )
    if original_values["sprint_id"] != task.sprint_id:
        changes.append(
            "Sprint changed from "
            f'{_format_sprint_name(original_values["sprint_name"])} '
            f'to {_format_sprint_name(task.sprint.name if task.sprint else None)}.'
        )
    if original_values["description"] != task.description:
        changes.append("Description updated.")
    if original_values["acceptance_criteria"] != task.acceptance_criteria:
        changes.append("Acceptance criteria updated.")
    if original_values["due_date"] != task.due_date:
        previous_due_date = original_values["due_date"].isoformat() if original_values["due_date"] else "No due date"
        current_due_date = task.due_date.isoformat() if task.due_date else "No due date"
        changes.append(f"Due date changed from {previous_due_date} to {current_due_date}.")

    return " ".join(changes)


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
            )
            profile = _get_profile(user)
            profile.name = form.cleaned_data.get('name', '')
            profile.role = 'member'
            profile.team = None
            profile.email = form.cleaned_data['email']
            profile.save()
            login(request, user)
            return redirect('welcome')
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
    profile = _get_profile(request.user)
    pending_invites = TeamInvite.objects.filter(
        recipient=request.user, status='pending'
    ).select_related('team', 'sender')
    return render(request, 'welcome.html', {
        'name': profile.name or request.user.username,
        'role': profile.role,
        'team': profile.team,
        'pending_invites': pending_invites,
    })


@login_required(login_url='login')
def boards(request):
    profile = _get_profile(request.user)
    is_manager = _is_manager(profile)

    if not profile.team:
        return render(request, 'boards.html', {'no_team': True})

    team = profile.team
    filter_sprints = list(_sprint_queryset(team))
    selected_sprint_id = request.GET.get('sprint', '').strip()
    selected_sprint = next((sprint for sprint in filter_sprints if str(sprint.id) == selected_sprint_id), None)

    tasks = _team_tasks(team)

    # if not is_manager:
    #     tasks = tasks.filter(assigned_to=request.user)

    if selected_sprint is not None:
        tasks = tasks.filter(sprint=selected_sprint)
    else:
        selected_sprint_id = ''

    tasks = tasks.order_by('due_date', 'title')

    board_columns = [
        (key, label, [t for t in tasks if t.status == key])
        for key, label in Task.STATUS_CHOICES
    ]

    assignable_users = User.objects.filter(
        profile__team=profile.team, is_active=True
    ).order_by('username')

    return render(request, 'boards.html', {
        'board_columns': board_columns,
        'status_choices': Task.STATUS_CHOICES,
        'is_manager': is_manager,
        'team': team,
        'assignable_users': assignable_users,
        'today': date.today(),
        'soon': date.today() + timedelta(days=3),
        'filter_sprints': filter_sprints,
        'selected_sprint_id': selected_sprint_id,
        'selected_sprint': selected_sprint,
    })

@login_required(login_url='login')
def task_page(request):
    profile = _get_profile(request.user)
    is_manager = _is_manager(profile)

    if not profile.team:
        return render(request, 'tasks.html', {'no_team': True})

    team = profile.team
    assignable_users = _assignable_users_for_team(team)

    if request.method == 'POST':
        action = request.POST.get('action')

        # Create new task
        if action == 'create_task':
            form = TaskForm(
                request.POST,
                request.FILES,
                can_assign=is_manager,
                assignable_users=assignable_users,
            )
            if form.is_valid():
                task = form.save(commit=False)
                task.team = team
                if not is_manager:
                    task.assigned_to = request.user
                task.save()
                _log_task_created(task, request.user)
                return redirect('task_page')

        #  Manager assignment / unassignment
        if action == 'update_assignment':
            if not is_manager:
                raise PermissionDenied
            task = get_object_or_404(Task, pk=request.POST.get('task_id'))
            previous_assignee = task.assigned_to
            assigned_to_id = request.POST.get('assigned_to')
            task.assigned_to = assignable_users.filter(pk=assigned_to_id).first() if assigned_to_id else None
            task.save()

            note = (
                f"{TaskUpdate.SYSTEM_ASSIGNED_PREFIX}{task.assigned_to.username}."
                if task.assigned_to else TaskUpdate.SYSTEM_UNASSIGNED_NOTE
            )
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

        # Progress updates
        if action == 'update_progress':
            task = get_object_or_404(Task, pk=request.POST.get('task_id'))
            if not _can_update_task(request.user, is_manager, task):
                raise PermissionDenied

            new_status = request.POST.get('status', task.status)
            note = request.POST.get('note', '').strip()
            attachment = request.FILES.get('attachment')
            valid_statuses = {choice[0] for choice in Task.STATUS_CHOICES}

            if new_status in valid_statuses:
                previous_status = task.status
                task.status = new_status
                task.save()

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

        # Delete task
        if action == 'delete_task':
            if not is_manager:
                raise PermissionDenied
            task = get_object_or_404(Task, pk=request.POST.get('task_id'), team=team)
            task.delete()
            return redirect('task_page')

    else:
        form = TaskForm(can_assign=is_manager, assignable_users=assignable_users)

    #  Build the queryset of tasks
    tasks = _team_tasks(team)
    if not is_manager:
        tasks = tasks.filter(assigned_to=request.user)

    # Finally render the page
    return render(request, 'tasks.html', {
        'form': form,
        'tasks': tasks.order_by('due_date', 'title'),
        'is_manager': is_manager,
        'assignable_users': assignable_users,
        'status_choices': Task.STATUS_CHOICES,
        'current_user_id': request.user.id,
    })



@login_required(login_url='login')
def backlog_page(request):
    profile = _get_profile(request.user)
    is_manager = _is_manager(profile)

    if not profile.team:
        return render(request, 'backlog.html', {'no_team': True})

    team = profile.team
    assignable_users = _assignable_users_for_team(team)
    available_sprints = _available_sprints_for_team(team)
    create_form = BacklogItemForm(
        assignable_users=assignable_users,
        available_sprints=available_sprints,
    )
    invalid_groom_task_id = None
    invalid_groom_form = None

    if request.method == 'POST':
        if not is_manager:
            raise PermissionDenied

        action = request.POST.get('action')
        if action == 'create_backlog_item':
            create_form = BacklogItemForm(
                request.POST,
                request.FILES,
                assignable_users=assignable_users,
                available_sprints=available_sprints,
            )
            if create_form.is_valid():
                task = create_form.save(commit=False)
                task.team = team
                _sync_task_backlog_state(task)
                task.save()
                _log_task_created(task, request.user)
                return redirect('backlog_page')
        elif action == 'update_backlog_item':
            task = get_object_or_404(Task, pk=request.POST.get('task_id'), team=team, sprint__isnull=True)
            original_values = {
                "title": task.title,
                "item_type": task.item_type,
                "priority": task.priority,
                "backlog_state": task.backlog_state,
                "sprint_id": task.sprint_id,
                "sprint_name": task.sprint.name if task.sprint else None,
                "description": task.description,
                "acceptance_criteria": task.acceptance_criteria,
                "due_date": task.due_date,
                "assigned_to_id": task.assigned_to_id,
                "assigned_to_username": task.assigned_to.username if task.assigned_to else None,
            }
            invalid_groom_task_id = task.id
            invalid_groom_form = BacklogGroomForm(
                request.POST,
                instance=task,
                assignable_users=assignable_users,
                available_sprints=available_sprints,
            )

            if invalid_groom_form.is_valid():
                task = invalid_groom_form.save(commit=False)
                _sync_task_backlog_state(task)
                task.save()
                note = _build_backlog_change_note(original_values, task)
                assignee_changed = original_values["assigned_to_id"] != task.assigned_to_id

                if note or assignee_changed:
                    TaskUpdate.objects.create(
                        task=task,
                        author=request.user,
                        status=task.status,
                        status_changed=False,
                        previous_status=None,
                        previous_assignee=original_values["assigned_to_username"] if assignee_changed else None,
                        current_assignee=task.assigned_to.username if assignee_changed and task.assigned_to else None,
                        note=note,
                    )

                return redirect('backlog_page')
        elif action == 'delete_backlog_item':
            task = get_object_or_404(Task, pk=request.POST.get('task_id'), team=team, sprint__isnull=True)
            task.delete()
            return redirect('backlog_page')

    backlog_items = list(_backlog_queryset(team))
    backlog_sections = []

    for state_value, state_label in Task.BACKLOG_STATE_CHOICES:
        items_in_state = [item for item in backlog_items if item.backlog_state == state_value]
        if is_manager:
            for item in items_in_state:
                if invalid_groom_form is not None and item.id == invalid_groom_task_id:
                    item.groom_form = invalid_groom_form
                else:
                    item.groom_form = BacklogGroomForm(
                        instance=item,
                        assignable_users=assignable_users,
                        available_sprints=available_sprints,
                    )

        backlog_sections.append(
            {
                "value": state_value,
                "label": state_label,
                "items": items_in_state,
            }
        )

    return render(
        request,
        'backlog.html',
        {
            'create_form': create_form,
            'backlog_sections': backlog_sections,
            'is_manager': is_manager,
            'sprint_count': Sprint.objects.filter(team=team).count(),
        },
    )


@login_required(login_url='login')
def sprint_board_page(request):
    profile = _get_profile(request.user)
    is_manager = _is_manager(profile)

    if not profile.team:
        return render(request, 'sprints.html', {'no_team': True})

    team = profile.team
    filter_sprints = list(_sprint_queryset(team))
    selected_sprint_id = request.GET.get('sprint', '').strip()
    selected_sprint = next((sprint for sprint in filter_sprints if str(sprint.id) == selected_sprint_id), None)
    if selected_sprint is None:
        selected_sprint_id = ''

    create_form = SprintForm(team=team)
    invalid_status_sprint_id = None
    invalid_status_form = None

    if request.method == 'POST':
        if not is_manager:
            raise PermissionDenied

        action = request.POST.get('action')
        if action == 'create_sprint':
            create_form = SprintForm(request.POST, team=team)
            if create_form.is_valid():
                sprint = create_form.save(commit=False)
                sprint.team = team
                sprint.save()
                return _redirect_to_sprint_board(
                    request,
                    request.POST.get('selected_sprint', '').strip(),
                )
        elif action == 'update_sprint_status':
            sprint = get_object_or_404(Sprint, pk=request.POST.get('sprint_id'), team=team)
            invalid_status_sprint_id = sprint.id
            invalid_status_form = SprintStatusForm(request.POST, instance=sprint)
            if invalid_status_form.is_valid():
                invalid_status_form.save()
                return _redirect_to_sprint_board(
                    request,
                    request.POST.get('selected_sprint', '').strip(),
                )
        elif action == 'delete_sprint':
            sprint = get_object_or_404(Sprint, pk=request.POST.get('sprint_id'), team=team)
            sprint_tasks = list(_team_tasks(team).filter(sprint=sprint))

            for task in sprint_tasks:
                task.sprint = None
                _sync_task_backlog_state(task)
                task.save(update_fields=['sprint', 'backlog_state', 'updated_at'])
                _log_task_note(
                    task,
                    request.user,
                    f"Sprint changed from {sprint.name} to Product Backlog.",
                )

            selected_sprint_id = request.POST.get('selected_sprint', '').strip()
            if selected_sprint_id == str(sprint.id):
                selected_sprint_id = ''
            sprint.delete()
            return _redirect_to_sprint_board(request, selected_sprint_id)

    sprints = [selected_sprint] if selected_sprint else filter_sprints
    for sprint in sprints:
        sprint.board_tasks = list(_ordered_tasks(_team_tasks(team).filter(sprint=sprint)))
        if is_manager:
            if invalid_status_form is not None and sprint.id == invalid_status_sprint_id:
                sprint.status_form = invalid_status_form
            else:
                sprint.status_form = SprintStatusForm(instance=sprint)

    return render(
        request,
        'sprints.html',
        {
            'create_form': create_form,
            'is_manager': is_manager,
            'sprints': sprints,
            'filter_sprints': filter_sprints,
            'selected_sprint_id': selected_sprint_id,
            'backlog_count': Task.objects.filter(team=team, sprint__isnull=True).count(),
        },
    )


@login_required(login_url='login')
def profile_dashboard(request):
    profile = _get_profile(request.user)
    tasks = (
        Task.objects.filter(assigned_to=request.user)
        .select_related('assigned_to')
        .prefetch_related('updates__author')
    )

    return render(request, "profile_dashboard.html", {
        "profile": profile,
        "tasks": tasks.order_by('due_date', 'title'),
    })


def logout_view(request):
    logout(request)
    return redirect('login')


def forgot_password(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')

        try:
            user = User.objects.get(username=username, email=email)
        except User.DoesNotExist:
            return render(request, 'forgot_password.html', {'error': 'No account matches that username and email.'})

        if not user.check_password(old_password):
            return render(request, 'forgot_password.html', {'error': 'Current password is incorrect.'})

        user.set_password(new_password)
        user.save()
        return redirect('login')

    return render(request, 'forgot_password.html')

@login_required
def create_team(request):
    if request.method == 'POST':
        form = CreateTeamForm(request.POST)
        if form.is_valid():
            team = Team.objects.create(name=form.cleaned_data['name'])
            profile = _get_profile(request.user)
            profile.team = team
            profile.role = 'manager'
            profile.save()
            return redirect('team_page')
    else:
        form = CreateTeamForm()
    return render(request, 'create_team.html', {'form': form})


@login_required
def team_page(request):
    profile = _get_profile(request.user)
    if not profile.team:
        return redirect('home')

    team = profile.team
    members = Profile.objects.filter(team=team).select_related('user')
    tasks = _backlog_queryset(team)
    invite_form = None
    invite_error = None

    if is_manager := _is_manager(profile):
        if request.method == 'POST':
            invite_form = InviteForm(request.POST)
            if invite_form.is_valid():
                username = invite_form.cleaned_data['username']
                recipient = User.objects.get(username=username)
                recipient_profile = _get_profile(recipient)

                if recipient_profile.team == team:
                    invite_error = "That user is already in your team."
                elif TeamInvite.objects.filter(team=team, recipient=recipient, status='pending').exists():
                    invite_error = "That user already has a pending invite."
                else:
                    TeamInvite.objects.create(
                        team=team,
                        sender=request.user,
                        recipient=recipient,
                    )
                    invite_error = None
                    invite_form = InviteForm()
        else:
            invite_form = InviteForm()

    return render(request, 'team_page.html', {
        'team': team,
        'members': members,
        'tasks': tasks,
        'invite_form': invite_form,
        'invite_error': invite_error,
        'is_manager': is_manager,
    })


@login_required
def accept_invite(request, invite_id):
    invite = get_object_or_404(TeamInvite, id=invite_id, recipient=request.user, status='pending')
    profile = _get_profile(request.user)
    profile.team = invite.team
    profile.role = 'member'
    profile.save()
    invite.status = 'accepted'
    invite.save()
    return redirect('team_page')


@login_required
def reject_invite(request, invite_id):
    invite = get_object_or_404(TeamInvite, id=invite_id, recipient=request.user, status='pending')
    invite.status = 'rejected'
    invite.save()
    return redirect('home')

@login_required
def remove_member(request, user_id):
    profile = _get_profile(request.user)
    if not _is_manager(profile):
        raise PermissionDenied

    target = get_object_or_404(Profile, user_id=user_id, team=profile.team)
    if target.user == request.user:
        raise PermissionDenied

    target.team = None
    target.role = 'member'
    target.save()
    return redirect('team_page')


@login_required
def leave_team(request):
    profile = _get_profile(request.user)
    if not profile.team:
        return redirect('home')
    if _is_manager(profile):
        raise PermissionDenied

    profile.team = None
    profile.save()
    return redirect('home')


@login_required
def delete_team(request):
    profile = _get_profile(request.user)
    if not _is_manager(profile):
        raise PermissionDenied

    team = profile.team
    if not team:
        return redirect('home')

    member_count = Profile.objects.filter(team=team).count()
    if member_count > 1:
        raise PermissionDenied

    profile.team = None
    profile.role = 'member'
    profile.save()
    team.delete()
    return redirect('home')
