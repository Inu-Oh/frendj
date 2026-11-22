from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile
from frendj.models import Distractor


class DistractorUpdateViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        Profile.objects.create(user=user, name="Admin")
        self.client.force_login(user)

    def test_validation_error_shows_notice_before_redirecting_to_test(self):
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

    def test_post_rolls_back_updates_when_a_later_mutation_fails(self):
        distractor = Distractor.objects.create(
            language="English",
            core_vocab=False,
            word="original",
        )

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "distractor_id,language,core_vocab,word\n"
                f"{distractor.id},English,FALSE,changed\n"
                ",English,FALSE,bonjour\n",
                encoding="utf-8",
            )

            with (
                patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)),
                patch.object(
                    Distractor.objects,
                    "create",
                    side_effect=RuntimeError("CSV mutation failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "CSV mutation failed"):
                    self.client.post(reverse("staff:distractor_update"))

        distractor.refresh_from_db()
        self.assertEqual(distractor.word, "original")

    def test_post_reports_committed_database_when_export_fails(self):
        distractor = Distractor.objects.create(
            language="English",
            core_vocab=False,
            word="original",
        )

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "distractor_id,language,core_vocab,word\n"
                f"{distractor.id},English,TRUE,changed\n",
                encoding="utf-8",
            )

            with (
                patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)),
                patch("staff.views.settings.BASE_DIR", temp_dir),
                patch(
                    "staff.views.os.replace",
                    side_effect=OSError("disk full"),
                ),
            ):
                response = self.client.post(reverse("staff:distractor_update"))

            remaining_temp_files = list(Path(temp_dir).glob(".distractor_export_*.tmp"))

        distractor.refresh_from_db()
        self.assertEqual(distractor.word, "changed")
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("frendj:glossary"),
            fetch_redirect_response=False,
        )
        message_text = " ".join(
            str(message) for message in get_messages(response.wsgi_request)
        )
        self.assertIn("database update committed", message_text)
        self.assertIn("export failed", message_text)
        self.assertEqual(remaining_temp_files, [])

    def test_post_creates_updates_and_deletes_distractors(self):
        updated = Distractor.objects.create(
            language="English",
            core_vocab=False,
            word="original",
        )
        deleted = Distractor.objects.create(
            language="French",
            core_vocab=False,
            word="obsolete",
        )

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "distractor_id,language,core_vocab,word\n"
                f"{updated.id},English,TRUE,changed\n"
                ",French,FALSE,nouveau\n",
                encoding="utf-8",
            )

            with (
                patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)),
                patch("staff.views.settings.BASE_DIR", temp_dir),
            ):
                response = self.client.post(reverse("staff:distractor_update"))

        updated.refresh_from_db()
        self.assertEqual(updated.word, "changed")
        self.assertTrue(updated.core_vocab)
        self.assertFalse(Distractor.objects.filter(id=deleted.id).exists())
        self.assertTrue(
            Distractor.objects.filter(
                language="French",
                word="nouveau",
                core_vocab=False,
            ).exists()
            ,
            list(Distractor.objects.values("id", "language", "word", "core_vocab")),
        )
        self.assertEqual(response.status_code, 302)

    def test_post_rejects_duplicate_final_distractor_keys(self):
        first = Distractor.objects.create(
            language="English",
            core_vocab=False,
            word="first",
        )
        second = Distractor.objects.create(
            language="French",
            core_vocab=False,
            word="second",
        )

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "distractor_id,language,core_vocab,word\n"
                f"{first.id},English,FALSE,duplicate\n"
                f"{second.id},English,FALSE,duplicate\n",
                encoding="utf-8",
            )

            with patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)):
                response = self.client.post(reverse("staff:distractor_update"))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.word, "first")
        self.assertEqual(second.word, "second")
        self.assertTemplateUsed(
            response,
            "staff/distractor_error_redirect.html",
        )

    def test_post_allows_new_row_replacing_an_absent_database_key(self):
        replaced = Distractor.objects.create(
            language="French",
            core_vocab=False,
            word="bonjour",
        )

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "distractor_id,language,core_vocab,word\n"
                ",French,FALSE,bonjour\n",
                encoding="utf-8",
            )

            with (
                patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)),
                patch("staff.views.settings.BASE_DIR", temp_dir),
            ):
                response = self.client.post(reverse("staff:distractor_update"))

        self.assertFalse(Distractor.objects.filter(id=replaced.id).exists())
        self.assertTrue(
            Distractor.objects.filter(
                language="French",
                word="bonjour",
                core_vocab=False,
            ).exists()
        )
        self.assertEqual(response.status_code, 302)

    def test_post_redirects_to_test_when_database_integrity_conflicts(self):
        distractor = Distractor.objects.create(
            language="English",
            core_vocab=False,
            word="original",
        )

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "distractors.csv"
            csv_path.write_text(
                "distractor_id,language,core_vocab,word\n"
                f"{distractor.id},English,FALSE,changed\n",
                encoding="utf-8",
            )

            with (
                patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)),
                patch.object(
                    Distractor,
                    "save",
                    side_effect=IntegrityError("unique conflict"),
                ),
            ):
                response = self.client.post(reverse("staff:distractor_update"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("staff:distractor_test"),
            fetch_redirect_response=False,
        )
