from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, TaskForm   # include TaskForm for tasks
from .models import Profile, Task


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )
            Profile.objects.create(
                user=user,
                name=form.cleaned_data['name'],
                role=form.cleaned_data['role'],
                team=form.cleaned_data['team']
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
    profile = Profile.objects.get(user=request.user)
    return render(request, 'welcome.html', {
        'user': request.user,
        'name': profile.name,
        'role': profile.role,
        'team': profile.team
    })


@login_required(login_url='login')
def task_page(request):
    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES)  # handle file uploads
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_to = request.user
            task.save()
            return redirect('task_page')
    else:
        form = TaskForm()

    tasks = Task.objects.filter(assigned_to=request.user)
    return render(request, 'tasks.html', {'form': form, 'tasks': tasks})


@login_required(login_url='login')
def profile_dashboard(request):
    # Full user profile dashboard
    profile = Profile.objects.get(user=request.user)
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
