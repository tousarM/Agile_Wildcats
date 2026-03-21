from django import forms
from django.contrib.auth.models import User
from .models import Task

class RegisterForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    name = forms.CharField(
        label="Full Name",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )

    role = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    team = forms.CharField(
        label="Team / Project",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )


class TaskForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        can_assign = kwargs.pop("can_assign", False)
        assignable_users = kwargs.pop("assignable_users", User.objects.none())
        super().__init__(*args, **kwargs)

        if can_assign:
            self.fields["assigned_to"].queryset = assignable_users
        else:
            self.fields.pop("assigned_to")

    class Meta:
        model = Task
        fields = ["title", "description", "due_date", "status", "attachment", "assigned_to"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Task title"}),
            "description": forms.Textarea(attrs={"class": "form-control", "placeholder": "Task description"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "attachment": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }
