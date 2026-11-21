from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile
from frendj.models import Distractor


class DistractorUpdateViewTests(TestCase):
    def test_validation_error_shows_notice_before_redirecting_to_test(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        Profile.objects.create(user=user, name="Admin")
        self.client.force_login(user)

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "id,language,core_vocab,distractor\n,German,FALSE,bonjour\n",
                encoding="utf-8",
            )
            with (
                patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)),
                patch.object(Distractor.objects, "all", return_value=[]),
            ):
                response = self.client.get(reverse("staff:distractor_update"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/distractor_error_redirect.html")
        self.assertContains(response, "One or more errors were encountered")
        self.assertContains(
            response,
            f'content="5;url={reverse("staff:distractor_test")}"',
        )
