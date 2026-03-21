from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, TaskForm   # include TaskForm for tasks
from .models import Profile, Task


def _get_profile(user):
    return Profile.objects.get(user=user)


def _is_manager(profile):
    return 'manager' in profile.role.lower()


def _assignable_user_queryset():
    return User.objects.filter(is_active=True).order_by('username')


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
        if request.POST.get('action') == 'update_assignment' and is_manager:
            task = get_object_or_404(Task, pk=request.POST.get('task_id'))
            assigned_to_id = request.POST.get('assigned_to')
            task.assigned_to = assignable_users.filter(pk=assigned_to_id).first() if assigned_to_id else None
            task.save(update_fields=['assigned_to'])
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
            return redirect('task_page')
    else:
        form = TaskForm(can_assign=is_manager, assignable_users=assignable_users)

    tasks = Task.objects.select_related('assigned_to')
    if not is_manager:
        tasks = tasks.filter(assigned_to=request.user)

    return render(request, 'tasks.html', {
        'form': form,
        'tasks': tasks.order_by('due_date', 'title'),
        'is_manager': is_manager,
        'assignable_users': assignable_users,
    })


@login_required(login_url='login')
def profile_dashboard(request):
    # Full user profile dashboard
    profile = _get_profile(request.user)
    tasks = Task.objects.filter(assigned_to=request.user)

    return render(request, "profile_dashboard.html", {
        "profile": profile,
        "tasks": tasks
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
