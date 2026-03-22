from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .forms import RegisterForm, TaskForm, CreateTeamForm, InviteForm   # include TaskForm for tasks
from .models import Profile, Task, TaskUpdate, Team, TeamInvite


def _get_profile(user):
    return Profile.objects.get(user=user)


def _is_manager(profile):
    return 'manager' in profile.role.lower()



def _can_update_task(user, is_manager, task):
    return is_manager or task.assigned_to_id == user.id


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
            )
            Profile.objects.create(
                user=user,
                name=form.cleaned_data.get('name', ''),
                role='member',
                team=None,
            )
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
    profile = request.user.profile
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
def task_page(request):
    profile = _get_profile(request.user)
    is_manager = _is_manager(profile)

    if not profile.team:
        return render(request, 'tasks.html', {'no_team': True})

    team = profile.team

    assignable_users = User.objects.filter(profile__team=team, is_active=True).order_by('username')

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
            task.team = team
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

    tasks = Task.objects.filter(team=team).select_related('assigned_to').prefetch_related('updates__author')
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

@login_required
def create_team(request):
    if request.method == 'POST':
        form = CreateTeamForm(request.POST)
        if form.is_valid():
            team = Team.objects.create(name=form.cleaned_data['name'])
            profile = request.user.profile
            profile.team = team
            profile.role = 'manager'
            profile.save()
            return redirect('team_page')
    else:
        form = CreateTeamForm()
    return render(request, 'create_team.html', {'form': form})


@login_required
def team_page(request):
    profile = request.user.profile
    if not profile.team:
        return redirect('home')

    team = profile.team
    members = Profile.objects.filter(team=team).select_related('user')
    tasks = Task.objects.filter(team=team).select_related('assigned_to').order_by('status', 'due_date')
    invite_form = None
    invite_error = None

    if profile.role == 'manager':
        if request.method == 'POST':
            invite_form = InviteForm(request.POST)
            if invite_form.is_valid():
                username = invite_form.cleaned_data['username']
                recipient = User.objects.get(username=username)
                recipient_profile = recipient.profile

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
        'is_manager': profile.role == 'manager',
    })


@login_required
def accept_invite(request, invite_id):
    invite = get_object_or_404(TeamInvite, id=invite_id, recipient=request.user, status='pending')
    profile = request.user.profile
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
    profile = request.user.profile
    if profile.role != 'manager':
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
    profile = request.user.profile
    if not profile.team:
        return redirect('home')
    if profile.role == 'manager':
        raise PermissionDenied

    profile.team = None
    profile.save()
    return redirect('home')


@login_required
def delete_team(request):
    profile = request.user.profile
    if profile.role != 'manager':
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