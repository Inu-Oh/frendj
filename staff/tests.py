import csv
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile
from frendj.models import Distractor, Module, Phrase, Translation


class PhraseCsvTestViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        Profile.objects.create(user=user, name="Admin")
        self.client.force_login(user)

    def post_csv(self, csv_content):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        csv_path = Path(temp_dir.name) / "phrases.csv"
        csv_path.write_text(csv_content, encoding="utf-8")
        patcher = patch("staff.views.PHRASE_CSV_PATH", str(csv_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.client.post(reverse("staff:phrase_csv_test"))

    def post_rows(self, *rows):
        csv_file = StringIO()
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(
            ["phrase_id", "module_name", "phrase", "phrase_lang", "translations"]
        )
        for phrase_id, module_name, phrase, language, translations in rows:
            csv_writer.writerow(
                [
                    phrase_id,
                    module_name,
                    phrase,
                    language,
                    json.dumps(translations),
                ]
            )
        return self.post_csv(csv_file.getvalue())

    def test_get_renders_the_test_form(self):
        response = self.client.get(reverse("staff:phrase_csv_test"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/phrase_csv_test.html")
        self.assertIsNotNone(response.context["test_form"])

    def test_post_redirects_to_update_when_csv_is_valid(self):
        response = self.post_csv(
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            ',Basics,bonjour,English,"[""hello"", ""hi""]"\n'
        )

        self.assertRedirects(
            response,
            reverse("staff:phrase_import"),
            fetch_redirect_response=False,
        )

    def test_post_reports_malformed_row(self):
        response = self.post_csv(
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            ",Basics,bonjour,English\n"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There was an error reading row 2")
        self.assertEqual(response.context["error_sections"][0]["title"], "CSV file")

    def test_post_accepts_blank_id_for_new_phrase(self):
        response = self.post_csv(
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            ',Basics,bonjour,English,"[""hello""]"\n'
        )

        self.assertRedirects(
            response,
            reverse("staff:phrase_import"),
            fetch_redirect_response=False,
        )

    def test_post_reports_field_errors_without_key_or_type_errors(self):
        response = self.post_csv(
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            'not-an-id,,!,German,"""hello"""\n'
            '999999,A very long module name,bonjour,English,"[]"\n'
        )

        self.assertEqual(response.status_code, 200)
        section_titles = {
            section["title"] for section in response.context["error_sections"]
        }
        self.assertIn("Phrase ID column", section_titles)
        self.assertIn("Module name column", section_titles)
        self.assertIn("Phrase column", section_titles)
        self.assertIn("Phrase language column", section_titles)
        self.assertIn("Translation column", section_titles)

    def test_post_reports_duplicate_new_phrases(self):
        module = Module.objects.create(name="Basics")
        Phrase.objects.create(
            phrase="bonjour",
            language="English",
            module=module,
        )
        response = self.post_csv(
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            ',Basics,BONJOUR,English,"[""hello""]"\n'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate phrases")
        self.assertContains(response, "BONJOUR")

    def test_post_reports_module_names_with_disallowed_characters(self):
        response = self.post_rows(("", "Basics_test", "bonjour", "English", ["hello"]))

        self.assertEqual(response.status_code, 200)
        section = next(
            section
            for section in response.context["error_sections"]
            if section["title"] == "Module name column"
        )
        self.assertIn("characters that are not allowed", " ".join(section["messages"]))
        self.assertIn('"Basics_test" at row 2', " ".join(section["messages"]))

    def test_post_reports_translations_with_disallowed_characters(self):
        response = self.post_rows(("", "Basics", "bonjour", "English", ["hello_world"]))

        self.assertEqual(response.status_code, 200)
        section = next(
            section
            for section in response.context["error_sections"]
            if section["title"] == "Translation column"
        )
        self.assertIn("non-alphabetic characters", " ".join(section["messages"]))
        self.assertIn('"hello_world" at row 2', " ".join(section["messages"]))

    def test_post_reports_phrases_longer_than_248_characters(self):
        phrase = "a" * 249
        response = self.post_rows(("", "Basics", phrase, "English", ["hello"]))

        self.assertEqual(response.status_code, 200)
        section = next(
            section
            for section in response.context["error_sections"]
            if section["title"] == "Phrase column"
        )
        self.assertIn("longer than 248", " ".join(section["messages"]))
        self.assertIn(f'"{phrase}" at row 2', " ".join(section["messages"]))

    def test_post_reports_translations_longer_than_248_characters(self):
        translation = "a" * 249
        response = self.post_rows(
            ("", "Basics", "bonjour", "English", [translation])
        )

        self.assertEqual(response.status_code, 200)
        section = next(
            section
            for section in response.context["error_sections"]
            if section["title"] == "Translation column"
        )
        self.assertIn("longer than 248", " ".join(section["messages"]))
        self.assertIn(f'"{translation}" at row 2', " ".join(section["messages"]))

    def test_post_reports_empty_translation_entries_as_blank(self):
        response = self.post_rows(("", "Basics", "bonjour", "English", [""]))

        self.assertEqual(response.status_code, 200)
        section = next(
            section
            for section in response.context["error_sections"]
            if section["title"] == "Translation column"
        )
        messages = " ".join(section["messages"])
        self.assertIn("rows missing translations: 2", messages)
        self.assertNotIn("non-alphabetic characters", messages)

    def test_post_reports_duplicate_translations_in_a_row(self):
        response = self.post_rows(
            ("", "Basics", "bonjour", "English", ["hello", "hello"])
        )

        self.assertEqual(response.status_code, 200)
        section = next(
            section
            for section in response.context["error_sections"]
            if section["title"] == "Translation column"
        )
        messages = " ".join(section["messages"])
        self.assertIn("duplicate equivalent translations", messages)
        self.assertIn('"hello" at row 2', messages)


class DistractorCsvTestViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        Profile.objects.create(user=user, name="Admin")
        self.client.force_login(user)

    def post_csv(self, csv_content):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        csv_path = Path(temp_dir.name) / "distractors.csv"
        csv_path.write_text(csv_content, encoding="utf-8")
        patcher = patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.client.post(reverse("staff:distractor_csv_test"))

    def test_get_renders_the_test_form(self):
        response = self.client.get(reverse("staff:distractor_csv_test"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/distractor_csv_test.html")
        self.assertIsNotNone(response.context["test_form"])

    def test_post_redirects_to_update_when_csv_is_valid(self):
        response = self.post_csv(
            "distractor_id,language,core_vocab,word\n"
            ",English,FALSE,bonjour\n"
        )

        self.assertRedirects(
            response,
            reverse("staff:distractor_import"),
            fetch_redirect_response=False,
        )

    def test_post_reports_malformed_row(self):
        response = self.post_csv(
            "distractor_id,language,core_vocab,word\n"
            ",English,FALSE\n"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There was an error reading row 2")
        self.assertEqual(response.context["error_sections"][0]["title"], "CSV file")

    def test_post_reports_non_integer_and_unknown_ids_and_field_errors(self):
        response = self.post_csv(
            "distractor_id,language,core_vocab,word\n"
            "not-an-id,English,FALSE,bonjour\n"
            "999999,French,FALSE,salut\n"
            ",German,maybe,bonjour!\n"
            ",French,FALSE,abcdefghijklmnopqrstuvwxy\n"
        )

        self.assertEqual(response.status_code, 200)
        section_titles = {
            section["title"] for section in response.context["error_sections"]
        }
        self.assertIn("Distractor ID column", section_titles)
        self.assertIn("Distractor column", section_titles)
        self.assertIn("Language column", section_titles)
        self.assertIn("Core vocabulary column", section_titles)
        self.assertContains(response, "not-an-id")

    def test_post_reports_duplicate_new_distractors(self):
        response = self.post_csv(
            "distractor_id,language,core_vocab,word\n"
            ",English,FALSE,bonjour\n"
            ",English,TRUE,bonjour\n"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate distractors")
        self.assertContains(response, "bonjour")


class PhraseCsvImportViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        Profile.objects.create(user=user, name="Admin")
        self.client.force_login(user)

    def get_csv(self, csv_content):
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "phrases.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            with patch("staff.views.PHRASE_CSV_PATH", str(csv_path)):
                return self.client.get(reverse("staff:phrase_import"))

    def test_get_summarizes_added_edited_and_deleted_phrases(self):
        module = Module.objects.create(name="Basics")
        edited = Phrase.objects.create(
            language="French",
            phrase="bonjour",
            module=module,
        )
        deleted = Phrase.objects.create(
            language="French",
            phrase="obsolete",
            module=module,
        )
        Translation.objects.create(
            language="English",
            translation="hello",
            phrase=edited,
        )

        response = self.get_csv(
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            f'{edited.id},Greetings,bonjour!,French,"[""hello"", ""salut""]"\n'
            ',Basics,nouveau,French,"[""welcome""]"\n'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/phrase_import.html")
        self.assertEqual(response.context["stored_phrase_count"], 2)
        self.assertEqual(response.context["total_added"], 1)
        self.assertEqual(response.context["added_phrases"], [("nouveau", "French")])
        self.assertEqual(response.context["phrases_edited"], 1)
        self.assertEqual(response.context["total_edits"], 3)
        self.assertEqual(response.context["total_deletions"], 1)
        self.assertEqual(response.context["phrases_to_be_deleted"], [deleted])
        self.assertContains(response, "The following 1 phrases will be deleted")
        self.assertContains(response, "Total changes that will be made: 3")

    def test_get_renders_redirect_notice_for_empty_or_invalid_csv(self):
        csv_files = (
            "",
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            ',Basics,bonjour,French,"{}"\n',
            "phrase_id,module_name,phrase,phrase_lang,translations\n"
            ',Basics,bonjour,French,"[]"\n',
        )
        for csv_content in csv_files:
            with self.subTest(csv_content=csv_content):
                response = self.get_csv(csv_content)

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(
                    response,
                    "staff/phrase_error_redirect.html",
                )
                self.assertContains(response, "One or more errors were encountered")
                self.assertContains(response, "Phrase Test page")
                self.assertContains(
                    response,
                    f'content="5;url={reverse("staff:phrase_csv_test")}"',
                )


class DistractorCsvImportViewTests(TestCase):
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
                response = self.client.get(reverse("staff:distractor_import"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/distractor_error_redirect.html")
        self.assertContains(response, "One or more errors were encountered")
        self.assertContains(
            response,
            f'content="5;url={reverse("staff:distractor_csv_test")}"',
        )

    def test_get_summarizes_added_edited_and_deleted_distractors(self):
        edited = Distractor.objects.create(
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
                f"{edited.id},French,TRUE,revised\n"
                ",English,FALSE,nouveau\n",
                encoding="utf-8",
            )
            with patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)):
                response = self.client.get(reverse("staff:distractor_import"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/distractor_import.html")
        self.assertEqual(response.context["stored_distractor_count"], 2)
        self.assertEqual(response.context["new"], 1)
        self.assertEqual(response.context["added_distractors"], [("nouveau", "English")])
        self.assertEqual(response.context["distractors_edited"], 1)
        self.assertEqual(response.context["total_edits"], 3)
        self.assertEqual(response.context["to_be_deleted"], 1)
        self.assertEqual(response.context["distractors_to_be_deleted"], [deleted])
        self.assertContains(response, "The following 1 distractors will be edited")
        self.assertContains(response, "Total changes that will be made: 3")

    def test_get_shows_redirect_notice_for_empty_or_invalid_csv(self):
        for csv_content in ("", "distractor_id,language,core_vocab,word\n,French,FALSE,bonjour!\n"):
            with self.subTest(csv_content=csv_content), TemporaryDirectory() as temp_dir:
                csv_path = Path(temp_dir) / "distractors.csv"
                csv_path.write_text(csv_content, encoding="utf-8")
                with patch("staff.views.DISTRACTOR_CSV_PATH", str(csv_path)):
                    response = self.client.get(reverse("staff:distractor_import"))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(
                    response,
                    "staff/distractor_error_redirect.html",
                )
                self.assertContains(response, "One or more errors were encountered")

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
                    self.client.post(reverse("staff:distractor_import"))

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
                response = self.client.post(reverse("staff:distractor_import"))

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
                response = self.client.post(reverse("staff:distractor_import"))

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
                response = self.client.post(reverse("staff:distractor_import"))

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
                response = self.client.post(reverse("staff:distractor_import"))

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
                response = self.client.post(reverse("staff:distractor_import"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("staff:distractor_csv_test"),
            fetch_redirect_response=False,
        )