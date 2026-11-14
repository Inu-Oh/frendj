from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from frendj.models import Phrase, UserPhraseStrength


User = get_user_model()


class RegisterViewTests(TestCase):

    def test_registration_creates_user_and_initializes_phrase_progress(self):
        phrase = Phrase.objects.create(
            language="French",
            phrase="Bonjour",
            module=None,
        )

        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "new-user@example.com",
                "username": "new-user",
                "password1": "StrongPass!93821",
                "password2": "StrongPass!93821",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("frendj:home"))
        user = User.objects.get(username="new-user")
        self.assertTrue(user.check_password("StrongPass!93821"))
        self.assertTrue(
            UserPhraseStrength.objects.filter(user=user, phrase=phrase).exists()
        )

    def test_duplicate_registration_does_not_create_another_user_or_progress(self):
        user = User.objects.create_user(
            username="existing-user",
            email="existing@example.com",
            password="ExistingPass!93821",
        )
        phrase = Phrase.objects.create(
            language="French",
            phrase="Bonjour",
            module=None,
        )
        UserPhraseStrength.objects.create(user=user, phrase=phrase)

        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "existing@example.com",
                "username": "existing-user",
                "password1": "AnotherPass!93821",
                "password2": "AnotherPass!93821",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="existing-user").count(), 1)
        self.assertEqual(UserPhraseStrength.objects.filter(user=user).count(), 1)
