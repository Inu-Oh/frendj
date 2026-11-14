from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Profile
from frendj.models import Phrase, UserPhraseStrength


User = get_user_model()


class ProfileTestCase(TestCase):

    def setUp(self):
        
        # Create users
        user = User.objects.create_user(username="foo", password="dj39&*d2", email="foo@cb-bc.gc.ca")
        admin = User.objects.create_superuser(username="bar", password="jd93*&2d", email="bar@cb-bc.gc.ca")
        noname = User.objects.create_user(username="baz", password="2fcv2$@1", email="baz@gmail.com")
        less_than_zero = User.objects.create_user(username="minusone", password="-13f23%^jd", email="minusone@cb-bc.gc.ca")

        # Create profiles
        Profile.objects.create(user=user, name="Foo")
        Profile.objects.create(user=admin, name="Bar", xp=0)
        Profile.objects.create(user=noname, name="", xp=999_999_999)
        Profile.objects.create(user=less_than_zero, name="Minus One", xp=-1)
    
    def test_profile_count(self):
        profiles = Profile.objects.all()
        self.assertEqual(profiles.count(), 4)

    def test_valid_profile1(self):
        user_profile = Profile.objects.get(name="Foo")
        self.assertTrue(user_profile.is_valid_profile())
    
    def test_valid_profile2(self):
        admin_profile = Profile.objects.get(name="Bar")
        self.assertTrue(admin_profile.is_valid_profile())

    def test_invalid_profile_no_name(self):
        noname_profile = Profile.objects.get(name="")
        self.assertFalse(noname_profile.is_valid_profile())
    
    def test_invalid_profile_negative_xp(self):
        negative_xp_profile = Profile.objects.get(name="Minus One")
        self.assertFalse(negative_xp_profile.is_valid_profile())


class RegisterViewTests(TestCase):

    def test_registration_rejects_name_longer_than_profile_limit(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "long-name@example.com",
                "username": "long-name-user",
                "name": "x" * 26,
                "password1": "StrongPass!93821",
                "password2": "StrongPass!93821",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="long-name-user").exists())

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
                "name": "New User",
                "password1": "StrongPass!93821",
                "password2": "StrongPass!93821",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("frendj:home"))
        user = User.objects.get(username="new-user")
        self.assertTrue(user.check_password("StrongPass!93821"))
        self.assertEqual(Profile.objects.get(user=user).name, "New User")
        self.assertTrue(
            UserPhraseStrength.objects.filter(user=user, phrase=phrase).exists()
        )

    def test_duplicate_registration_does_not_create_another_user_or_progress(self):
        user = User.objects.create_user(
            username="existing-user",
            email="existing@example.com",
            password="ExistingPass!93821",
        )
        Profile.objects.create(user=user, name="Existing User")
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
                "name": "Changed Name",
                "password1": "AnotherPass!93821",
                "password2": "AnotherPass!93821",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="existing-user").count(), 1)
        self.assertEqual(Profile.objects.get(user=user).name, "Existing User")
        self.assertEqual(UserPhraseStrength.objects.filter(user=user).count(), 1)
