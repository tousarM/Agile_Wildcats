from django import forms
from django.contrib.auth.models import User
from .models import Sprint, Task, Team


def _add_form_control_css(fields):
    for field in fields.values():
        existing_classes = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing_classes} form-control".strip()

class RegisterForm(forms.Form):
    username = forms.CharField(max_length=150)
    name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_form_control_css(self.fields)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already taken.")
        return username


class BacklogItemForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    sprint = forms.ModelChoiceField(
        queryset=Sprint.objects.none(),
        required=False,
        empty_label="Backlog (no sprint)",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "item_type",
            "priority",
            "backlog_state",
            "sprint",
            "description",
            "acceptance_criteria",
            "due_date",
            "assigned_to",
            "attachment",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Backlog item title"}),
            "item_type": forms.Select(attrs={"class": "form-control"}),
            "priority": forms.Select(attrs={"class": "form-control"}),
            "backlog_state": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe the work item"}),
            "acceptance_criteria": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "What must be true for this item to be complete?"}
            ),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "attachment": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        assignable_users = kwargs.pop("assignable_users", User.objects.none())
        available_sprints = kwargs.pop("available_sprints", Sprint.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = assignable_users
        self.fields["sprint"].queryset = available_sprints
        _add_form_control_css(self.fields)


class BacklogGroomForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    sprint = forms.ModelChoiceField(
        queryset=Sprint.objects.none(),
        required=False,
        empty_label="Backlog (no sprint)",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "item_type",
            "priority",
            "backlog_state",
            "sprint",
            "description",
            "acceptance_criteria",
            "due_date",
            "assigned_to",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "item_type": forms.Select(attrs={"class": "form-control"}),
            "priority": forms.Select(attrs={"class": "form-control"}),
            "backlog_state": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "acceptance_criteria": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        assignable_users = kwargs.pop("assignable_users", User.objects.none())
        available_sprints = kwargs.pop("available_sprints", Sprint.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = assignable_users
        self.fields["sprint"].queryset = available_sprints
        _add_form_control_css(self.fields)


class SprintForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.team = kwargs.pop("team", None)
        super().__init__(*args, **kwargs)
        _add_form_control_css(self.fields)

    class Meta:
        model = Sprint
        fields = ["name", "start_date", "end_date", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Sprint name"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if self.team and Sprint.objects.filter(team=self.team, name__iexact=name).exists():
            raise forms.ValidationError("A sprint with that name already exists for this team.")

        return name


class SprintStatusForm(forms.ModelForm):
    class Meta:
        model = Sprint
        fields = ["start_date", "end_date", "status"]
        widgets = {
            "start_date": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
        }

class CreateTeamForm(forms.Form):
    name = forms.CharField(max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_form_control_css(self.fields)

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Team.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("A team with that name already exists.")
        return name

class InviteForm(forms.Form):
    username = forms.CharField(max_length=150)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_form_control_css(self.fields)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if not User.objects.filter(username=username).exists():
            raise forms.ValidationError("No user with that username exists.")
        return username


class ProfileSettingsForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}),
    )
