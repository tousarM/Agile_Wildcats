from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from .forms import RegisterForm
from .models import Profile


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

        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('welcome')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})

    return render(request, 'login.html')


def welcome(request):

    profile = Profile.objects.get(user=request.user)

    return render(request, 'welcome.html', {
        'name': profile.name
    })


def logout_view(request):
    logout(request)
    return redirect('login')

def forgot_password(request):
    return render(request, 'forgot_password.html')    