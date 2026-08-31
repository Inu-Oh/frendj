from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=25,
        validators=[MinLengthValidator(1, "Choose a name I can call you")]
    )
    xp = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_valid_profile(self):
        User = get_user_model()
        user_test = User.objects.filter(username=self.user.username).exists()
        return self.xp >= 0 and len(self.name) >= 1 and user_test

    def __str__(self):
        return f"{self.user.username}'s Profile"


class Module(models.Model):
    name = models.CharField(
        unique=True,
        max_length=24,
        validators=[MinLengthValidator(3, "This name is too short")]
    )

    def is_valid_module(self):
        return 3 <= len(self.name) <= 24

    def __str__(self):
        return self.name


class Phrase(models.Model):
    FRENCH = "French"
    ENGLISH = "English"
    LANGUAGES = [
        (FRENCH, "French"),
        (ENGLISH, "English")
    ]
    language = models.CharField(max_length=12, choices=LANGUAGES, default=FRENCH)
    phrase = models.CharField(
        max_length=248,
        validators=[MinLengthValidator(1, "This phrase is too short")]
    )
    phrase_strength = models.ManyToManyField(settings.AUTH_USER_MODEL,
        through='UserPhraseStrength')
    module = models.ForeignKey(Module, null=True, on_delete=models.SET_NULL,
        related_name='phrases_in_module')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta: # Converted from unique_together to Meta.indexes - run: python -Wa manage.py test
        constraints = [ # models.functions.Lower('name'),
            models.UniqueConstraint(fields=['phrase', 'language'], name='unique_phrase_language')
        ]

    def is_valid_phrase(self):
        language_test = self.language in ["French", "English"]
        phrase_test = 1 <= len(self.phrase) <= 248
        module_test = Module.objects.filter(name=self.module.name).exists()
        module_name_test = (3 <= len(self.module.name) <= 24)
        return language_test and phrase_test and module_test and module_name_test

    def __str__(self):
        return self.phrase


class Translation(models.Model):
    FRENCH = "French"
    ENGLISH = "English"
    LANGUAGES = [
        (FRENCH, "French"),
        (ENGLISH, "English")
    ]
    language = models.CharField(max_length=12, choices=LANGUAGES, default=FRENCH)
    translation = models.CharField(
        max_length=248,
        validators=[MinLengthValidator(1, "This phrase is too short")]
    )
    phrase = models.ForeignKey(Phrase, null=True, on_delete=models.SET_NULL,
        related_name='phrase_translations')
    
    # For creation and update times, rely to phrase datetime data
    
    def is_valid_translation(self):
        valid_languages = ["French", "English"]
        translation_language_test = self.language in valid_languages
        phrase_language_test = self.phrase.language in valid_languages
        comparative_language_test = self.language != self.phrase.language
        translation_length_test = 1 <= len(self.translation) <= 248
        phrase_exists_test = Phrase.objects.filter(phrase=self.phrase.phrase).exists()
        phrase_length_test = 1 <= len(self.phrase.phrase) <= 248
        module_name_test = 3 <= len(self.phrase.module.name) <= 24
        return (translation_language_test and phrase_language_test
                and comparative_language_test and translation_length_test
                and phrase_exists_test and phrase_length_test and module_name_test)

    def __str__(self):
        return f'{self.translation} ({self.phrase})'


class UserPhraseStrength(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='user_phrase_strength')
    phrase = models.ForeignKey(Phrase, on_delete=models.CASCADE)
    learned = models.BooleanField(default=False)
    views = models.IntegerField(default=0)
    correct = models.IntegerField(default=0)
    strength = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'phrase'], name='unique_user_phrase_strength')
        ]
    
    def is_valid_user_phrase_strength(self):
        User = get_user_model()
        user_test = User.objects.filter(username=self.user.username).exists()
        phrase_test = Phrase.objects.filter(phrase=self.phrase.phrase).exists()
        phrase_length_test = 1 <= len(self.phrase.phrase) <= 248
        phrase_language_test = self.phrase.language in ["French", "English"]
        learned_test = self.learned in [True, False]
        views_count_test = self.views >= 0
        correct_count_test = self.correct >= 0
        strength_score_test = 0 <= self.strength <= 100
        return (user_test and phrase_test and phrase_length_test and learned_test
                and views_count_test and correct_count_test and strength_score_test
                and phrase_language_test)

    def __str__(self):
        return f'{self.user.username}  "{self.phrase.phrase}"'