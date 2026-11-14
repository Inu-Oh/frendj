from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


class UserCreateForm(UserCreationForm):
    username = forms.CharField(
        required=True,
        label=_("Username"),
        help_text=_("A unique name to identify your user profile"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("inessoul2022")
        }),
    )
    email = forms.EmailField(
        required=True,
        label=_("Email"),
        help_text=_("Enter an email to associate with this account."),
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": _("your_name@example.com")
        }),
    )
    name = forms.CharField(
        required=True,
        max_length=25,
        label=_("Your name"),
        help_text=_("Name you want us to call you"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("Ines Sol")
        }),
    )
    password1 = forms.CharField(
        required=True,
        label=_("Password"),
        help_text=_("Choose a strong password with letters, numbers and special characters."),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": _("Enter your password"),
            "autocomplete": "new-password"
        }),
    )
    password2 = forms.CharField(
        required=True,
        label=_("Confirm password"),
        help_text=_("Make sure the passwords match"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": _("Enter your password again"),
            "autocomplete": "new-password"
        }),
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'name', 'password1', 'password2']