from django.db import IntegrityError
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Module, Phrase, Profile, Translation, UserPhraseStrength


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


class ModuleTestCase(TestCase):

    def setUp(self):
        
        # Create modules
        Module.objects.create(name="Good Module")
        Module.objects.create(name="No")
        Module.objects.create(name="I am too long to be a module name")
    
    def test_module_count(self):
        modules = Module.objects.all()
        self.assertEqual(modules.count(), 3)

    def test_valid_module(self):
        good_module = Module.objects.get(name="Good Module")
        self.assertTrue(good_module.is_valid_module())
    
    def test_invalid_module_too_short(self):
        short_name_module = Module.objects.get(name="No")
        self.assertFalse(short_name_module.is_valid_module())
    
    def test_invalid_module_too_long(self):
        long_name_module = Module.objects.get(name="I am too long to be a module name")
        self.assertFalse(long_name_module.is_valid_module())

    def test_unique_module_name(self):

        # Attempt to create a duplicate module name and raise exception
        with self.assertRaises(IntegrityError):
            Module.objects.create(name="Good Module")


class PhraseTestCase(TestCase):

    def setUp(self):
        
        # Create modules
        good_module = Module.objects.create(name="Good Module")
        bad_module = Module.objects.create(name="No")

        # Create phrases
        Phrase.objects.create(language="French", phrase="Salut", module=good_module)
        Phrase.objects.create(language="English", phrase="Hi", module=good_module)
        Phrase.objects.create(language="Finnish", phrase="Moi", module=good_module)
        Phrase.objects.create(language="French", phrase="Coucou", module=bad_module)
        Phrase.objects.create(language="English", phrase="", module=good_module)
        Phrase.objects.create(
            language="French",
            phrase="Je suis une histoire trop longue pour cette appli. Je ne conforme pas aux regles qui sont inscrit dans les modeles de cet appli de Django. Il faut écrire combien lettre de plus. Je ne sais plus quoi d'écrire. Aide moi ma muse de finire cette phrase trop longue et banale.",
            module=good_module
        )

    def test_english_phrase_count(self):
        english_phrases = Phrase.objects.filter(language="English")
        self.assertEqual(english_phrases.count(), 2)
    
    def test_french_phrase_count(self):
        french_phrase = Phrase.objects.filter(language="French")
        self.assertEqual(french_phrase.count(), 3)
    
    def test_module_phrase_count(self):
        module = Module.objects.get(name="Good Module")
        self.assertEqual(module.phrases_in_module.count(), 5)

    def test_valid_phrase(self):
        phrase = Phrase.objects.get(phrase="Salut")
        self.assertTrue(phrase.is_valid_phrase())
    
    def test_invalid_phrase_too_short(self):
        short_phrase = Phrase.objects.get(phrase="")
        self.assertFalse(short_phrase.is_valid_phrase())
    
    def test_invalid_phrase_too_long(self):
        long_phrase = Phrase.objects.get(phrase="Je suis une histoire trop longue pour cette appli. Je ne conforme pas aux regles qui sont inscrit dans les modeles de cet appli de Django. Il faut écrire combien lettre de plus. Je ne sais plus quoi d'écrire. Aide moi ma muse de finire cette phrase trop longue et banale.")
        self.assertFalse(long_phrase.is_valid_phrase())

    def test_invalid_phrase_langauge(self):
        finnish_phrase = Phrase.objects.get(phrase="Moi")
        self.assertFalse(finnish_phrase.is_valid_phrase())
    
    def test_invalid_phrase_bad_module(self):
        bad_module_phrase = Phrase.objects.get(phrase="Coucou")
        self.assertFalse(bad_module_phrase.is_valid_phrase())
    
    def test_unique_phrase_per_langauge_constraint(self):
        good_module = Module.objects.get(name="Good Module")

        # Attempt to make a duplicate phrase and raise exception
        with self.assertRaises(IntegrityError) as context:
            Phrase.objects.create(language="French", phrase="Salut", module=good_module)


class TranslationTestCase(TestCase):
    
    def setUp(self):

        # Create modules
        good_module = Module.objects.create(name="Good Module")
        bad_module = Module.objects.create(name="No")

        # Create phrases
        salut = Phrase.objects.create(language="French", phrase="Salut", module=good_module)
        hi = Phrase.objects.create(language="English", phrase="Hi", module=good_module)
        moi = Phrase.objects.create(language="Finnish", phrase="Moi", module=good_module)
        coucou = Phrase.objects.create(language="French", phrase="Coucou", module=bad_module) 
        no_phrase = Phrase.objects.create(language="English", phrase="", module=good_module)

        # Create translations
        Translation.objects.create(language="English", translation="Hi", phrase=salut)
        Translation.objects.create(language="French", translation="Salut", phrase=hi)
        Translation.objects.create(language="French", translation="Coucou", phrase=hi)
        Translation.objects.create(language="French", translation="Coucou", phrase=moi)
        Translation.objects.create(language="English", translation="Kookoo", phrase=coucou)
        Translation.objects.create(language="French", translation="Rien", phrase=no_phrase)
        Translation.objects.create(language="Swedish", translation="Hey", phrase=salut)
        Translation.objects.create(language="English", translation="", phrase=hi)
        Translation.objects.create(language="French", translation="Bonjour", phrase=salut)

    def test_english_translation_count(self):
        english_translations = Translation.objects.filter(language="English")
        self.assertEqual(english_translations.count(), 3)
    
    def test_hi_translation_count(self):
        hi = Phrase.objects.get(phrase="Hi")
        self.assertEqual(hi.phrase_translations.count(), 3)
    
    def test_module_translation_count(self):
        module = Module.objects.get(name="Good Module")
        phrases = module.phrases_in_module.all()
        translations = Translation.objects.filter(phrase__in=phrases)
        self.assertEqual(translations.count(), 8)
    
    def test_valid_translation(self):
        salut = Translation.objects.get(translation="Salut")
        self.assertTrue(salut.is_valid_translation())
    
    def test_invalid_translation_wrong_translation_language(self):
        swedish_word = Translation.objects.get(translation="Hey")
        self.assertFalse(swedish_word.is_valid_translation())
    
    def test_invalid_translation_wrong_phrase_language(self):
        finnish_word = Phrase.objects.get(phrase="Moi")
        coucou_as_translation_of_moi = Translation.objects.get(
            translation="Coucou", phrase=finnish_word)
        self.assertFalse(coucou_as_translation_of_moi.is_valid_translation())
    
    def test_invalid_translation_same_language_as_phrase(self):
        bonjour_as_translation_of_salut = Translation.objects.get(translation="Bonjour")
        self.assertFalse(bonjour_as_translation_of_salut.is_valid_translation())
    
    def test_invalid_translation_too_short(self):
        no_translation = Translation.objects.get(translation="")
        self.assertFalse(no_translation.is_valid_translation())
    
    def test_invalid_translation_no_phrase(self):
        translation_without_phrase = Translation.objects.get(translation="Rien")
        self.assertFalse(translation_without_phrase.is_valid_translation())
    
    def test_invalid_translation_module_name_too_short(self):
        short_name_module_tranaslation = Translation.objects.get(translation="Kookoo")
        self.assertFalse(short_name_module_tranaslation.is_valid_translation())


class UserPhraseStrengthTestCase(TestCase):
    
    def setUp(self):
        
        # Create users
        foo = User.objects.create_user(username="foo", password="dj39&*d2", email="foo@cb-bc.gc.ca")
        bar = User.objects.create_user(username="bar", password="-13f23%^jd", email="bar@cb-bc.gc.ca")

        # Create modules
        good_module = Module.objects.create(name="Good Module")

        # Create phrases
        salut = Phrase.objects.create(language="French", phrase="Salut", module=good_module)
        hi = Phrase.objects.create(language="English", phrase="Hi", module=good_module)
        bonjour = Phrase.objects.create(language="French", phrase="Bonjour", module=good_module)
        moi = Phrase.objects.create(language="Finnish", phrase="Moi", module=good_module)
        coucou = Phrase.objects.create(language="French", phrase="Coucou", module=good_module) 
        blank_phrase = Phrase.objects.create(language="English", phrase="", module=good_module)

        # Create user phrase strength objects
        UserPhraseStrength.objects.create(user=foo, phrase=salut)
        UserPhraseStrength.objects.create(user=bar, phrase=salut, learned=True, views=1, correct=1, strength=100)
        UserPhraseStrength.objects.create(user=foo, phrase=hi, learned=True, views=23, correct=0, strength=0)
        UserPhraseStrength.objects.create(user=bar, phrase=hi, learned=True, views=-1, correct=0, strength=0)
        UserPhraseStrength.objects.create(user=foo, phrase=bonjour, learned=True, views=1, correct=-1, strength=0)
        UserPhraseStrength.objects.create(user=bar, phrase=coucou, learned=True, views=1, correct=1, strength=-1)
        UserPhraseStrength.objects.create(user=foo, phrase=blank_phrase)
        UserPhraseStrength.objects.create(user=bar, phrase=moi)

    def test_user_phrase_strength_count_per_user(self):
        foo = User.objects.get(username="foo")
        user_phrase_strength_objects = foo.user_phrase_strength.all()
        self.assertEqual(user_phrase_strength_objects.count(), 4)

    def test_user_phrase_strength_count_per_phrase(self):
        salut = Phrase.objects.get(phrase="Salut")
        user_phrase_strength_objects = UserPhraseStrength.objects.filter(phrase=salut)
        self.assertEqual(user_phrase_strength_objects.count(), 2)
    
    def test_user_phrase_strength_defaults(self):
        foo = User.objects.get(username="foo")
        salut = Phrase.objects.get(phrase="Salut")
        user_phrase_strength = UserPhraseStrength.objects.get(user=foo, phrase=salut)
        self.assertEqual(user_phrase_strength.learned, False)
        self.assertEqual(user_phrase_strength.views, 0)
        self.assertEqual(user_phrase_strength.correct, 0)
        self.assertEqual(user_phrase_strength.strength, 0)

    def test_valid_user_phrase_strength_default_values(self):
        foo = User.objects.get(username="foo")
        salut = Phrase.objects.get(phrase="Salut")
        user_phrase_strength = UserPhraseStrength.objects.get(user=foo, phrase=salut)
        self.assertTrue(user_phrase_strength.is_valid_user_phrase_strength())

    def test_valid_user_phrase_strength_w_perfect_score(self):
        bar = User.objects.get(username="bar")
        salut = Phrase.objects.get(phrase="Salut")
        user_phrase_strength = UserPhraseStrength.objects.get(user=bar, phrase=salut)
        self.assertTrue(user_phrase_strength.is_valid_user_phrase_strength())
    
    def test_valid_user_phrase_strength_w_low_score(self):
        foo = User.objects.get(username="foo")
        hi = Phrase.objects.get(phrase="Hi")
        user_phrase_strength = UserPhraseStrength.objects.get(user=foo, phrase=hi)
        self.assertTrue(user_phrase_strength.is_valid_user_phrase_strength())
    
    def test_invalid_user_phrase_strength_w_negative_views(self):
        bar = User.objects.get(username="bar")
        hi = Phrase.objects.get(phrase="Hi")
        user_phrase_strength = UserPhraseStrength.objects.get(user=bar, phrase=hi)
        self.assertFalse(user_phrase_strength.is_valid_user_phrase_strength())

    def test_invalid_user_phrase_strength_w_negative_correct_answers(self):
        foo = User.objects.get(username="foo")
        bonjour = Phrase.objects.get(phrase="Bonjour")
        user_phrase_strength = UserPhraseStrength.objects.get(user=foo, phrase=bonjour)
        self.assertFalse(user_phrase_strength.is_valid_user_phrase_strength())
    
    def test_invalid_user_phrase_strength_w_negative_strength_score(self):
        bar = User.objects.get(username="bar")
        coucou = Phrase.objects.get(phrase="Coucou")
        user_phrase_strength = UserPhraseStrength.objects.get(user=bar, phrase=coucou)
        self.assertFalse(user_phrase_strength.is_valid_user_phrase_strength())
    
    def test_invalid_user_phrase_strength_w_blank_phrase(self):
        foo = User.objects.get(username="foo")
        blank_phrase = Phrase.objects.get(phrase="")
        user_phrase_strength = UserPhraseStrength.objects.get(user=foo, phrase=blank_phrase)
        self.assertFalse(user_phrase_strength.is_valid_user_phrase_strength())

    def test_invalid_user_phrase_strenght_w_wrong_phrase_langauge(self):
        bar = User.objects.get(username="bar")
        finnish_phrase = Phrase.objects.get(language="Finnish")
        user_phrase_strength = UserPhraseStrength.objects.get(user=bar, phrase=finnish_phrase)
        self.assertFalse(user_phrase_strength.is_valid_user_phrase_strength())