from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator
from django.db import models


User._meta.get_field('email').blank = False


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=25,
        validators=[MinLengthValidator(1, "Choose a name I can call you")]
    )
    xp = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "frendj_profile"

    def is_valid_profile(self):
        User = get_user_model()
        user_test = User.objects.filter(username=self.user.username).exists()
        return self.xp >= 0 and len(self.name) >= 1 and user_test

    def __str__(self):
        return f"{self.user.username}'s Profile"