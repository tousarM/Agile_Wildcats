from django import forms
from django.contrib.auth.models import User
from .models import Task, Team

class RegisterForm(forms.Form):
    username = forms.CharField(max_length=150)
    name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already taken.")
        return username


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
