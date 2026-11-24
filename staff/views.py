import os
from csv import reader, DictWriter, Error as CSV_Error
from json import loads
from pathlib import Path
from re import compile, match
from tempfile import NamedTemporaryFile

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import UpdateView, CreateView, ListView, View

from frendj.models import Module, Phrase, Translation, Distractor, UserPhraseStrength
from accounts.models import Profile

from .forms import ModuleForm, CreatePhraseForm, CreateTranslationForm, UpdatePhraseForm, UpdateTranslationForm, CsvForm

PHRASE_CSV_PATH = 'import_data.csv'
DISTRACTOR_CSV_PATH = 'import_distractors.csv'
ALLOWED_DISTRACTOR = compile(r"(?=.*[^\W\d_])(?:[^\W\d_]|['-])+")


class StaffMenuView(LoginRequiredMixin, ListView):
    """Admin staff menu to navigate adding and editing content."""

    template_name = 'staff/manage_content.html'
    
    def get(self, request):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        profile = Profile.objects.get(user=request.user)
        modules = Module.objects.all().order_by('name')
        phrases = Phrase.objects.all().order_by('phrase')
        translations = Translation.objects.all().order_by('translation')

        context = {
            'profile': profile,
            'modules': modules,
            'phrases': phrases,
            'translations': translations,
        }
        
        return render(request, self.template_name, context)


# Three views for adding new content
class CreateModuleView(PermissionRequiredMixin, CreateView):
    """Admin page. Adds new modules to the database."""

    permission_required = 'frendj.add_module'
    template_name = 'staff/add_module.html'
    
    def get(self, request):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        form = ModuleForm()
        context = {'form': form}
        return render(request, self.template_name, context)

    def post(self, request):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        form = ModuleForm(request.POST)

        if not form.is_valid():
            context = {'form': form}
            return render(request, self.template_name, context)
        
        # Save new module and redirect to add phrases to this module
        module = form.save()
        return redirect(reverse_lazy('staff:add_phrase', kwargs={'pk': module.id}))


class CreatePhraseView(PermissionRequiredMixin, CreateView):
    """Admin page. Adds new phrases to the database."""

    permission_required = 'frendj.add_phrase'
    template_name = 'staff/add_phrase.html'
    
    def get(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')

        module = Module.objects.get(id=pk)
        phrases = Phrase.objects.filter(module=module)
        form = CreatePhraseForm()
        context = {'form': form, 'module': module, 'phrases': phrases}
        return render(request, self.template_name, context)

    def post(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        form = CreatePhraseForm(request.POST)
        module = Module.objects.get(id=pk)

        if not form.is_valid():
            context = {'form': form, 'module': module}
            return render(request, self.template_name, context)
        
        # Save new phrase after setting its module
        phrase = form.save(commit=False)
        phrase.module = module
        phrase.save()

        # Create a phrase strength object for the new phrase for every user 
        User = get_user_model()
        users = User.objects.all()
        for user in users:
            UserPhraseStrength.objects.create(
                phrase = phrase,
                user = user,
                learned = False,
                strength = 0,
                views = 0,
                correct = 0
            )
            
        return redirect(reverse_lazy('staff:add_phrase', kwargs={'pk': pk}))


class CreateTranslationView(PermissionRequiredMixin, CreateView):
    """Admin page. Adds new phrase translations to the database."""

    permission_required = 'frendj.add_translation'
    template_name = 'staff/add_translation.html'
    
    def get(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        phrase = Phrase.objects.get(id=pk)
        phrase_lang = phrase.language
        translation_lang = "French" if phrase_lang == "English" else "English"
        module = phrase.module
        phrase_set = Phrase.objects.filter(module=module)
        translations = Translation.objects.filter(phrase=phrase)
        
        form = CreateTranslationForm()
        context = {
            'form': form,
            'module': module,
            'current_phrase': phrase,
            'phrase_set': phrase_set,
            'translations': translations,
            'translation_language': translation_lang,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        form = CreateTranslationForm(request.POST)
        phrase = Phrase.objects.get(id=pk)
        phrase_lang = phrase.language
        translation_lang = "French" if phrase_lang == "English" else "English"

        if not form.is_valid():
            module = phrase.module
            phrase_set = Phrase.objects.filter(module=module)
            translations = Translation.objects.filter(phrase=phrase)
            
            context = {
                'form': form,
                'module': module,
                'current_phrase': phrase,
                'phrase_set': phrase_set,
                'translations': translations,
                'translation_language': translation_lang,
            }
            return render(request, self.template_name, context)

        translation = form.save(commit=False)
        translation.phrase = phrase
        translation.language = translation_lang
        translation.save()

        return redirect(reverse_lazy('staff:add_translation', kwargs={'pk': pk}))


# Three views for editing content
class UpdateModuleView(PermissionRequiredMixin, UpdateView):
    """Admin page. Edits modules in the database."""

    permission_required = 'frendj.change_module'
    template_name = 'staff/edit_module.html'
    
    def get(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        module = Module.objects.get(id=pk)
        form = ModuleForm(instance=module)
        context = {'module': module, 'form': form}
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        module = get_object_or_404(Module, id=pk)
        form = ModuleForm(request.POST, instance=module)

        if not form.is_valid():
            context = {'module': module, 'form': form}
            return render(request, self.template_name, context)

        form.save()
        return redirect(reverse_lazy('staff:manage_content'))


class UpdatePhraseView(PermissionRequiredMixin, UpdateView):
    """Admin page. Edits phrases in the database."""

    permission_required = 'frendj.change_phrase'
    template_name = 'staff/edit_phrase.html'
    
    def get(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        phrase = Phrase.objects.get(id=pk)
        form = UpdatePhraseForm(instance=phrase)
        module = Module.objects.get(name=phrase.module)
        context = {'form': form, 'module': module, 'phrase': phrase}
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        phrase = get_object_or_404(Phrase, id=pk)
        form = UpdatePhraseForm(request.POST, instance=phrase)

        if not form.is_valid():
            module = Module.objects.get(name=phrase.module)
            context = {'form': form, 'module': module, 'phrase': phrase}
            return render(request, self.template_name, context)

        form.save()
        return redirect(reverse_lazy('staff:manage_content'))


class UpdateTranslationView(PermissionRequiredMixin, UpdateView):
    """Admin page. Edits phrase translations in the database."""

    permission_required = 'frendj.change_translation'
    template_name = 'staff/edit_translation.html'
    
    def get(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
    
        translation = Translation.objects.get(id=pk)
        translation_lang = translation.language
        form = UpdateTranslationForm(instance=translation)
        phrase = Phrase.objects.get(id=translation.phrase.id)
        module = Module.objects.get(name=phrase.module)
        context = {
            'form': form,
            'module': module,
            'phrase': phrase,
            'translation': translation,
            'translation_language': translation_lang,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        if not request.user.is_staff:
            return redirect('frendj:home')
        
        translation = get_object_or_404(Translation, id=pk)
        translation_lang = translation.language
        form = UpdateTranslationForm(request.POST, instance=translation)
        if not form.is_valid():
            phrase = Phrase.objects.get(id=translation.phrase.id)
            module = Module.objects.get(name=phrase.module)
            context = {
                'form': form,
                'module': module,
                'phrase': phrase,
                'translation': translation,
                'translation_language': translation_lang,
            }
            return render(request, self.template_name, context)

        translation = form.save(commit=False)
        translation.language = translation_lang
        form.save()
        return redirect(reverse_lazy('staff:manage_content'))


# Two views for mass database updates from CSV to SQL
class CsvToDbTestView(PermissionRequiredMixin, View):
    """
    Admin page. Tests whether import_data.csv is correctly populated to mass edit data.
    Otherwise it provides feedback on errors that need correction.
    """

    permission_required = [
        'frendj.add_module',
        'frendj.add_phrase',
        'frendj.add_translation',
        'frendj.change_module',
        'frendj.change_phrase',
        'frendj.change_translation',
    ]
    template_name = 'staff/csv_db_test.html'

    def get(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')
        
        profile = Profile.objects.get(user=request.user)
        test_form = CsvForm()

        context = {
            'profile': profile,
            'test_form': test_form,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')
        
        profile = Profile.objects.get(user=request.user)
        test_form = CsvForm(request.POST)

        if not test_form.is_valid():
            context = {
                'profile': profile,
                'test_form': test_form,
            }
            return render(request, self.template_name, context)

        # Try to create from CSV file a list of dictionaries to verify data
        data_list = []
        csv_errors = []
        try:
            with open(PHRASE_CSV_PATH, newline="", encoding="utf-8-sig") as csvfile:
                data_reader = reader(csvfile)
                next(data_reader, None)
                for row_num, row in enumerate(data_reader, start=2):
                    try:
                        data_list.append({
                            'phrase_id': row[0] if row[0].strip() else None,
                            'module_name': row[1],
                            'phrase': row[2],
                            'phrase_lang': row[3],
                            'translations': loads(row[4])
                        })
        # If an error occurs fromat an appropriate error message
                    except (ValueError, IndexError) as e:
                        csv_errors.append(
                            f"There was an error reading row {row_num} of the CSV. "
                            f"{e}. Correct the CSV before proceeding."
                        )
        except FileNotFoundError:
            csv_errors.append(f"The file {DISTRACTOR_CSV_PATH} was not found.")
        except (OSError, CSV_Error) as e:
            csv_errors.append(
                f"There was an error reading {PHRASE_CSV_PATH}: {e}. Correct the CSV before proceeding."
            )

        # With critical error reading CSV redirect to show error message
        if csv_errors:
            context = {
                'profile': profile,
                'test_form': test_form,
                'error_sections': [
                    {'title': "CSV file", 'messages': csv_errors}
                ]
            }
            return render(request, self.template_name, context)

        # Check that phrase ID is entered correctly for updates - Set up base data to verify
        phrases = Phrase.objects.all()
        phrase_keys = {
            (p.phrase.strip().lower(), p.language.strip().lower())  for p in phrases
        }
        # Track lists of errors by type
        non_int_rows = []
        wrong_id_rows = []
        id_errors = []
        missing_module_rows = []
        error_sections = []

        # Loop through CSV data to check each error type starting vith ID column
        row = 1
        for item in data_list:
            row += 1
            raw_id = item['phrase_id']
            try:
                phrase_id = int(raw_id)
            except ValueError:
                non_int_rows.append(f"{row} : {raw_id}")
            else:
                if not phrases.filter(id=int(phrase_id)).exists():
                    wrong_id_rows.append(f"ID {phrase_id} at row {row}")
            # Verify that module name is present for each phrase and not longer than 24 chars
            module_name = item['module_name']
            if not module_name:
                missing_module_rows.append(row)
            # ELIF - create allowed module name stting and chck
            # IF - check length of module name

            # Check that phrases are present and only contain alphabetic characters

        # Format message if IDs are not entered correctly
        if non_int_rows:
            id_errors.append(
                "These rows contain phrase IDs that are not intagers: "
                + ", ".join(non_int_rows)
            )

        if wrong_id_rows:
            id_errors.append(
                "Phrase IDs at the following rows don't exist in the database. Delete"
                " if it's a new phrase or correct if its already in the database: "
                + ", ".join(wrong_id_rows)
            )

        if id_errors:
            id_errors.append("Correct all phrase IDs before running the test again.")
            error_sections.append({
                'title': "Phrase ID column",
                'messages': id_errors,
            })

        # Verify that module name is entered for each phrase and not longer than 24 chars
        row = 1
        for item in data_list:
            row += 1
            if not item["module_name"]:
                message += f"blank at row {row}, "
            elif len(item["module_name"]) > 24:
                message += f"name too long at row {row}, "
        if message:
            message += "Module names not provided or too long for phrases at rows: " + message
            message += "\b\b. Provide module names for each phrase."
            context = {
                'profile': profile,
                'test_form': test_form,
                'message': message,
            }
            return render(request, self.template_name, context)
        
        # Check that phrases ware entered and only contain alphabetic characters
        row, missing_phrases, non_alphas = 1, "", ""
        for item in data_list:
            row += 1
            if not item["phrase"]:
                if not missing_phrases:
                    missing_phrases += "Phrase cells are blank at the following rows: "
                missing_phrases += f"{row}, "
            elif match(r'[a-zA-Z ]$', item["phrase"]):
                if not non_alphas:
                    non_alphas += "The following phrases include non-alpha characters: "
                non_alphas += f'"{item["phrase"]}" at row {row}, '
        if missing_phrases or non_alphas:
            message += "Errors with data entry for phrase column. "
            if missing_phrases:
                message += missing_phrases + "\b\b. "
            if non_alphas:
                message += non_alphas + "\b\b. "
            message += "Resolve missing phrases and replace non alphabetic characters."
            context = {
                'profile': profile,
                'test_form': test_form,
                'message': message,
            }
            return render(request, self.template_name, context)

        # Check that new phrase is unique in its language list
        phrase_list = [p.phrase.lower()+p.language.lower() for p in phrases]
        duplicates, row = [], 1 # first row is heading
        for item in data_list:
            row += 1
            if not item['phrase_id']:
                if item['phrase'].lower()+item['phrase_lang'].lower() in phrase_list:
                    duplicates.append({'phrase': item['phrase'], 'row': row})
                    print("Duplicate phrase:", item['phrase'], 
                        "Language:", item['phrase_lang'])
                phrase_list.append(item['phrase'])
        if len(duplicates):
            message += "The CSV file includes phrases that are duplicates: "
            for duplicate in duplicates:
                message += f'"{duplicate['phrase']}" at row {duplicate['row']}, '
            message += "\b\b. Make sure there are no duplicates before testing again."
            context = {
                'profile': profile,
                'test_form': test_form,
                'message': message,
            }
            return render(request, self.template_name, context)

        # Verify either English or French
        row, lang_errors = 1, []
        for item in data_list:
            row += 1
            if item['phrase_lang'] not in ["French", "English"]:
                lang_errors.append(row)
        if lang_errors:
            message = """Invalid language was entered in some rows. 
                Use either French or English, capatialized, to indicate the phrase language.
                Correct this in the CSV before proceeding. Affected rows include: """
            for err in lang_errors:
                message += str(err) + ", "
            message += "\b\b."
            context = {
                'profile': profile,
                'test_form': test_form,
                'message': message,
            }
            return render(request, self.template_name, context)

        # Verify that all row have well formatted translations that include only alphabetic characters
        row, non_lists, non_alphas, missing_translations = 1, "", "", ""
        for item in data_list:
            row += 1
            if translations := item["translations"]:
                if type(translations) is not list:
                    if not non_lists:
                        non_lists += "Translations in the following rows are not formatted correctly. "
                        non_lists += "Enter all translations in double quotation marks in square brackets. "
                        non_lists += "Example: [\"Translation one\", \"Two and\", \"Three\"]. Correct rows: "
                    non_lists += f"{row}, "
                for translation in translations:
                    if match(r'[a-zA-Z ]$', translation):
                        if not non_alphas:
                            non_alphas += "Translations in the following rows include non-alphabetic characters: "
                        non_alphas += f"{row}, "
            else: # if list is empty
                if not missing_translations:
                    missing_translations += "Translations are missing for phrases in rows: "
                missing_translations += f"{row}, "
        if missing_translations or non_alphas or non_lists:
            message += "Errors with data entry for translation column. "
            if missing_translations:
                message += missing_translations
            if non_alphas:
                message += non_alphas
            if non_lists:
                message += non_lists
            message += "Correct all errors before proceeding with the test."
            context = {
                'profile': profile,
                'test_form': test_form,
                'message': message,
            }
            return render(request, self.template_name, context)

        # If check finds no errors redirect to update DB page
        return redirect(reverse_lazy('staff:csv_db_update') )


class CsvToDbUpdateView(PermissionRequiredMixin, ListView):
    """
    Admin page. GET shows summary of changes that will be made to the database based on
    import_data.csv. If the CSV is free of errors, POST updates the SQL database.
    """

    permission_required = [
        'frendj.add_module',
        'frendj.add_phrase',
        'frendj.add_translation',
        'frendj.change_module',
        'frendj.change_phrase',
        'frendj.change_translation',
    ]
    template_name = 'staff/csv_db_update.html'

    def get(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')
        profile = Profile.objects.get(user=request.user)
        phrases = Phrase.objects.all()
        translations = Translation.objects.all()
        submit_form = CsvForm() 

        # Try to create from CSV file a list of dictionaries to verify SQL data
        data_list = []
        try:
            with open(PHRASE_CSV_PATH) as csvfile:
                data_reader = reader(csvfile)
                next(data_reader)
                row_count = 1
                for row in data_reader:
                    row_count += 1
                    dict_obj = {
                        'phrase_id': row[0],
                        'module_name': row[1],
                        'phrase': row[2],
                        'phrase_lang': row[3],
                        'translations': loads(row[4])
                    }
                    data_list.append(dict_obj)
        # If an error occurs give feedback
        except Exception as e:
            message = f"There was an error reading the file. "
            message += "Review the CSV and return to test form before running update. "
            context = {
                'profile': profile,
                'message': message,
                'details': e
            }
            return render(request, self.template_name, context)

        # TODO - remove print statements in checks after testing
        # Run all checks to test data and redirect to test page if there are any errors
        error, error_msg = False, "No errors"
        phrases = Phrase.objects.all()
        phrase_list = [p.phrase.lower()+p.language.lower() for p in phrases]
        for item in data_list:
            # Check that phrase id is entered correctly for updates
            if phrase_id := item["phrase_id"]:
                try:
                    phrase_id = int(phrase_id)
                except ValueError:
                    error = True
                    print("Phrase id is not an int. Error: ", error)
                    break
                try:
                    if not phrases.get(id=phrase_id):
                        error = True
                        print("Phrase ID is wrong. Error: ", error)
                        break
                except:
                    error = True
                    print("Phrase ID is wrong. Error: ", error)
                    break
            # Verify that module name is entered for each phrase and not longer than 24 chars
            if ( not item["module_name"] or (len(item["module_name"]) > 24) ):
                error = True
                print("Module name error. Error: ", error)
                break
            # Check that phrases ware entered and only contain alphabetic characters
            if not item["phrase"] or match(r'[a-zA-Z ]$', item["phrase"]):
                error = True
                print("Phrase blank or misformatted. Error: ", error)
                break
            # Check that new phrase is unique in its language list
            if not item['phrase_id']:
                print(item['phrase'].lower()+item['phrase_lang'].lower())
                if item['phrase'].lower()+item['phrase_lang'].lower() in phrase_list:
                    error = True
                    print("Duplicate phrase. Error: ", error, item['phrase'], 
                        "Language: ", item['phrase_lang'])
                    break
            # Verify either English or French for language options
            if item["phrase_lang"] not in ["French", "English"]:
                error = True
                print("Language is not French or English. Error: ", error)
                break
            # Verify that all row have well formatted translations that include only alphabetic characters
            if item_translations := item["translations"]:
                if type(item_translations) is not list:
                    error = True
                    print("Translations are not in a list format. Error: ", error)
                    break
                for translation in item_translations:
                    if not translation or match(r'[a-zA-Z ]$', translation):
                        error = True
                        print("A translation is blank or not alphabetic. Error: ", error)
                        break
            else: # if translation list is empty
                error = True
                print("Translation list is empty. Error: ", error)
                break
        if error:
            return redirect('staff:csv_db_test')

        # Compare CSV data with database content and get stats
        current_phrase_count = phrases.count()
        total, changed, new, csv_phrase_ids = 0, [], [], []

        # Count all the items in the data list
        for item in data_list:
            total += 1

            # Count new items as those without a phrase ID
            if not item['phrase_id']:
                new.append((item["phrase"], item['phrase_lang']))
            else:
                csv_phrase_ids.append(int(item['phrase_id']))
                phrase = phrases.get(id=item['phrase_id'])
                if phrase.language != item['phrase_lang']:
                    changed.append(f"{phrase} (change language): {phrase.language} -> {item['phrase_lang']}")
                elif phrase.phrase != item["phrase"]:
                    changed.append(f"{phrase} (change phrase) -> {item['phrase']}")
                elif phrase.module.name != item['module_name']:
                    changed.append(f"{phrase} (change module): {phrase.module.name} -> {item['module_name']}")
                else:
                    old_translations, new_translations = set(), set(item['translations'])
                    phrase_translations = translations.filter(phrase=phrase)
                    for translation in phrase_translations:
                        old_translations.add(translation.translation)
                    if old_translations != new_translations:
                        changed.append(f"{phrase.phrase} (change translations): {', '.join(old_translations)} -> {', '.join(new_translations)}")

        # TODO - change this to count number of phrases to be deleted from the database
        # - unchanged is because deletion was not yet set up - TODO - delete in post
        # Count the number of unchanged phrases in the database based on the changes 
        unchanged = total - len(new) - len(changed)
        for phrase in phrases:
            if phrase.id not in csv_phrase_ids:
                unchanged += 1

        context = {
            'profile': profile,
            'submit_form': submit_form,
            'current_phrase_count': current_phrase_count,
            'new': len(new),
            'added_phrases': new,
            'changed': len(changed),
            'changed_phrases': changed,
            'unchanged': unchanged,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')
        profile = Profile.objects.get(user=request.user)
        modules = Module.objects.all()
        phrases = Phrase.objects.all()
        translations = Translation.objects.all()
        submit_form = CsvForm(request.POST)
        if not submit_form.is_valid():
            message = "The update failed due to an invalid form. Contact IT for support."
            context = {
                'profile': profile,
                'message': message,
            }
            return render(request, self.template_name, context)
        
        # Read the CSV file and create list of dicts to track prhase data
        data_list, val_error = [], ""
        try:
            with open(PHRASE_CSV_PATH) as csvfile:
                data_reader = reader(csvfile)
                next(data_reader)
                row_count = 1
                for row in data_reader:
                    id_cell_value = int(row[0]) if row[0] else ""
                    dict_obj = {
                        'row': row_count,
                        'phrase_id': id_cell_value,
                        'module_name': row[1],
                        'phrase': row[2],
                        'phrase_lang': row[3],
                        'translations': loads(row[4])
                    }
                    if not dict_obj['module_name'] or not dict_obj['phrase'] or not dict_obj['phrase_lang'] or not dict_obj['translations']:
                        val_error += f"There is blank data at row {dict_obj['row']}. "
                        raise ValueError
                    data_list.append(dict_obj)
                    row_count += 1
        # If an error occurs give feedback
        except Exception as e:
            message = "There was an error reading the file. "
            message += val_error
            message += "Review the CSV and return to test form before running update. "
            context = {
                'profile': profile,
                'message': message,
                'details': e
            }
            return render(request, self.template_name, context)


        """The next six loops run same varfications as CsvToDbTestView, but abbreviated."""
        # Check that phrase id is entered correctly
        row = 1
        for item in data_list:
            row += 1
            if phrase_id := item["phrase_id"]:
                if not isinstance(phrase_id, int) or not phrases.get(id=phrase_id):
                    message = "Errors with data entry in the phrase ID column. "
                    message += "Review the data before continuing." 
                    context = { 'profile': profile, 'message': message }
                    return render(request, self.template_name, context)

        # Verify that module name is entered for each phrase
        row = 1
        for item in data_list:
            row += 1
            if not item["module_name"]:
                message = "Module names are missing. Provide module names for each phrase before continuing."
                context = { 'profile': profile, 'message': message }
                return render(request, self.template_name, context)
        
        # Check that phrases ware entered and only contain alphabetic characters
        row = 1
        for item in data_list:
            row += 1
            if not item["phrase"] or match(r'[a-zA-Z ]$', item["phrase"]):
                message = "Some phrases are too long or include non-alphabetic characters. "
                message += "Add missing phrases and replace non alphabetic characters before continuing."
                context = { 'profile': profile, 'message': message }
                return render(request, self.template_name, context)

        # Check that new phrases are unique
        phrase_list, row = [phrase.phrase for phrase in phrases], 1
        for item in data_list:
            row += 1
            if not item["phrase_id"]:
                if phrase := item["phrase"] in phrase_list:
                    message = "The CSV file includes duplicate phrases. Remove them before continuing."
                    context = { 'profile': profile, 'message': message }
                    return render(request, self.template_name, context)                    
                else:
                    phrase_list.append(phrase)

        # Verify either English or French for language options
        row = 1
        for item in data_list:
            row += 1
            if item["phrase_lang"] not in ["French", "English"]:
                message = "Some rows list an invalid phrase language. Review all rows and ensure that "
                message += "phrases have either French or English language before continuing."
                context = { 'profile': profile, 'message': message }
                return render(request, self.template_name, context)

        # Verify that all phrases have translations and those include only alphabetic characters
        row, non_lists, non_alphas, missing_translations = 1, False, False, False
        for item in data_list:
            row += 1
            if item["translations"]:
                if type(item["translations"]) is not list:
                    non_lists = True
                    break
                for translation in item["translations"]:
                    if match(r'[a-zA-Z ]$', translation):
                        non_alphas = True
                        break
            else: # if list is empty
                missing_translations = True
                break
        if missing_translations or non_alphas or non_lists:
            message = "Errors with data entry for translation column. Add translations for phrases with the "
            message += "format [\"Translation one\", \"Two and\", \"Three\"]. Correct all rows before continuing."
            context = {
                'profile': profile,
                'message': message,
            }
            return render(request, self.template_name, context)


        """The next loop populates and updates the database."""
        # Set data to track changes. Log changes to terminal.
        module_names, added_modules = [module.name for module in modules], 0
        added_phrases, edited_phrases, added_strength_objs  = 0, 0, 0
        deleted_translations, added_translations, edited_translations = 0, 0, 0

        # Compare new data to database and change data for all updates in CSV
        row = 1
        for dict_obj in data_list:
            row += 1
            # If the phrase's module doesn't exists create it
            if dict_obj["module_name"] not in module_names:
                print(f"Creating new module '{dict_obj['module_name']}'")
                module = Module.objects.create(
                    name = dict_obj["module_name"] 
                )
                module_names.append(dict_obj["module_name"])
                added_modules += 1
            else:
                module = modules.get(name=dict_obj["module_name"])
            
            # Update the phrase if it exists and changes were made
            if phrase_id := dict_obj["phrase_id"]:
                language_changed, phrase_changed, module_changed = False, False, False
                phrase = phrases.get(id=phrase_id)
                if phrase.language != dict_obj["phrase_lang"]:
                    print(f"Changing phrase language from {phrase.language} to {dict_obj['phrase_lang']}", end=". ")
                    phrase.language = dict_obj["phrase_lang"]
                    language_changed = True
                if phrase.phrase != dict_obj["phrase"]:
                    print(f"Changing phrase from '{phrase.phrase}' to '{dict_obj['phrase']}'", end=". ")
                    phrase.phrase = dict_obj["phrase"]
                    phrase_changed = True
                if phrase.module.name != dict_obj["module_name"]:
                    print(f"Changing module from '{phrase.module}' to '{dict_obj['module_name']}'", end=". ")
                    phrase.module = module
                    module_changed = True
                if language_changed or phrase_changed or module_changed:
                    print("Change made to phrase with ID", phrase_id)
                    phrase.save()
                    edited_phrases += 1
                # Loop through translations to update them if there are changes
                old_translation_set, new_translation_set = set(), set(dict_obj["translations"])
                old_phrase_translations = translations.filter(phrase=phrase)
                for translation in old_phrase_translations:
                    old_translation_set.add(translation.translation)
                if old_translation_set != new_translation_set:
                    translation_language = "English" if str(dict_obj["phrase_lang"]) == "French" else "French"
                    print(f"Changing translations for the phrase '{phrase.phrase}' with id {phrase_id}.")
                    # Delete old translations if they are not in updated set
                    for old_translation in old_phrase_translations:
                        if old_translation.translation not in new_translation_set:
                            old_translation.delete()
                            deleted_translations += 1
                    # Add translations that are not in the database
                    for new_translation in dict_obj["translations"]:
                        if new_translation not in old_translation_set:
                            Translation.objects.create(
                                language = translation_language,
                                translation = new_translation,
                                phrase = phrase
                            )
                            edited_translations += 1
            # Or create new phrase if it does not yet exist
            else:
                phrase = Phrase.objects.create(
                    language = dict_obj["phrase_lang"],
                    phrase = dict_obj["phrase"],
                    module = module
                )
                added_phrases += 1
                print(f"Creating new phrase, translation(s) and user strength objects for {dict_obj['phrase']} in {dict_obj['phrase_lang']} with ID {phrase.id}. ")
                # Create translations for the new phrase
                translation_language = "English" if str(dict_obj["phrase_lang"]) == "French" else "French"
                for translation in dict_obj["translations"]:
                    Translation.objects.create(
                        language = translation_language,
                        translation = translation,
                        phrase = phrase
                    )
                    added_translations += 1
                # Create phrase strength objects for each user for the new phrase
                User = get_user_model()
                users = User.objects.all()
                for user in users:
                    UserPhraseStrength.objects.create(
                        phrase = phrase,
                        user = user,
                        learned = False,
                        strength = 0,
                        views = 0,
                        correct = 0
                    )
                    added_strength_objs += 1
        
        # Log all change counts in terminal
        print(f"Modules added: {added_modules}\nPhrases added: {added_phrases}")
        print(f"Phrases edited: {edited_phrases}\nStrength objects added: {added_strength_objs}")
        print(f"Translations deleted: {deleted_translations}")
        print(f"Translation sets edited: {edited_translations}")
        print(f"Translations added for newly added phrases: {added_translations}")

               
        """The final loop writes a new copy of the database to CSV"""
        export_data = []
        updated_phrases = Phrase.objects.all()
        updated_tranlations = Translation.objects.all()
        for phrase in updated_phrases:
            row = {}
            row["phrase_id"] = phrase.id
            row["module_name"] = phrase.module
            row["phrase"] = phrase.phrase
            row["phrase_lang"] = phrase.language
            phrase_translations = updated_tranlations.filter(phrase=phrase)
            translation_dict = '['
            for translation in phrase_translations:
                # translation_set.append(translation.translation) # NOTE This did not work
                translation_dict += f'"{translation.translation}", '
            translation_dict = translation_dict[0:-2] + ']'
            row["translations"] = translation_dict
            export_data.append(row)

        current_time = timezone.now()
        now = current_time.strftime("%Y-%m-%d_%H-%M-%S")
        with open(f"database_export_{now}.csv", "w") as export:
            writer = DictWriter(
                export, 
                fieldnames=[
                    "phrase_id",
                    "module_name",
                    "phrase",
                    "phrase_lang",
                    "translations"
                ]
            )
            writer.writeheader()
            for phrase in export_data:
                writer.writerow(
                    {
                        "phrase_id": phrase["phrase_id"],
                        "module_name": phrase["module_name"],
                        "phrase": phrase["phrase"],
                        "phrase_lang": phrase["phrase_lang"],
                        "translations": phrase["translations"]
                    }
                )
        
        return redirect(reverse_lazy('frendj:glossary'))


class DistractorTestView(PermissionRequiredMixin, ListView):
    """
    Admin page. Tests whether import_distractos.csv is correctly populated to mass
    edit DB data. Otherwise it provides feedback on errors that need correction.
    """

    permission_required = [
        'frendj.add_distractor',
        'frendj.change_distractor',
    ]
    template_name = 'staff/distractor_test.html'

    def get(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')

        profile = Profile.objects.get(user=request.user)
        test_form = CsvForm()

        context = {
            'profile': profile,
            'test_form': test_form,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')

        profile = Profile.objects.get(user=request.user)
        test_form = CsvForm(request.POST)

        if not test_form.is_valid():
            context = {
                'profile': profile,
                'test_form': test_form,
            }
            return render(request, self.template_name, context)

        # Try to create from CSV file a list of dictionaries to verify data
        data_list = []
        csv_errors = []
        try:
            with open(DISTRACTOR_CSV_PATH, newline="", encoding="utf-8-sig") as csvfile:
                data_reader = reader(csvfile)
                next(data_reader, None)
                for row_num, row in enumerate(data_reader, start=2):
                    try:
                        data_list.append({
                            'id': row[0] if row[0].strip() else None,
                            'distractor': row[3],
                            'language': row[1],
                            'core_vocab': row[2],
                        })
        # If an error occurs format an appropriate error message
                    except (ValueError, IndexError) as e:
                        csv_errors.append(
                            f"There was an error reading row {row_num} of the CSV. "
                            f"{e}. Correct the CSV before proceeding."
                        )
        except FileNotFoundError:
            csv_errors.append(f"The file {DISTRACTOR_CSV_PATH} was not found.")
        except (OSError, CSV_Error) as e:
            csv_errors.append(
                f"There was an error reading {DISTRACTOR_CSV_PATH}: {e}. Correct the CSV before proceeding."
            )

        # With critical error reading CSV redirect to show error message
        if csv_errors:
            context = {
                'profile': profile,
                'test_form': test_form,
                'error_sections': [
                    {'title': 'CSV file', 'messages': csv_errors},
                ],
            }
            return render(request, self.template_name, context)

        # Check that distractor ID is entered correctly for updates - Set up base data to verify
        distractors = Distractor.objects.all()
        distractor_keys = {
            (d.word.strip().lower(), d.language.strip().lower()) for d in distractors
        }
        # Track lists of errors by type
        non_int_rows = []
        wrong_id_rows = []
        id_errors = []
        missing_distractor_rows = []
        non_alpha_rows = []
        too_long_rows = []
        distractor_errors = []
        duplicates = []
        lang_errors = []
        core_vocab_errors = []
        error_sections = []

        # Loop through CSV data to check each error type starting with ID column checks
        row = 1
        for item in data_list: 
            row += 1
            raw_id = item['id']
            if raw_id is not None:
                try:
                    distractor_id = int(raw_id)
                except ValueError:
                    non_int_rows.append(f"{row} : {raw_id}")
                else:
                    if not distractors.filter(id=int(distractor_id)).exists():
                        wrong_id_rows.append(f"ID {distractor_id} at row {row}, ")
            # Check that distractors are present and only contain 24 or less alphabetic characters
            distractor = item['distractor']
            if not distractor:
                missing_distractor_rows.append(row)
            elif not ALLOWED_DISTRACTOR.fullmatch(distractor):
                non_alpha_rows.append(f'"{distractor}" at row {row}')
            if len(distractor) > 24:
                too_long_rows.append(f'"{distractor}" at row {row}')
            # Chack that new distractor is unique in its language list
            if not item['id']:
                key = (item['distractor'].strip().lower(), item['language'].strip().lower())
                if key in distractor_keys:
                    duplicates.append({'distractor': item['distractor'], 'row': row})
                distractor_keys.add(key)
            # Verify that language is either English or French
            if item['language'] not in {"English", "French"}:
                lang_errors.append(str(row))
            # Check that value for core vocabulary identification is either True or False
            if item['core_vocab'].strip().upper() not in {"TRUE", "FALSE"}:
                core_vocab_errors.append(str(row))

        # Format message if IDs are not entered correctly
        if non_int_rows:
            id_errors.append(
                "These rows contain distractor IDs that are not integers: "
                + ", ".join(non_int_rows)
            )
        if wrong_id_rows:
            id_errors.append(
                "Distractor IDs at the following rows don't exist in the database. Delete"
                " if it's a new distractor or correct if its already in the database: "
                + ", ".join(wrong_id_rows)
            )
        if id_errors:
            id_errors.append("Correct all distractor IDs before running the test again.")
            error_sections.append({
                'title': "Distractor ID column",
                'messages': id_errors,
            })

        # Format message if distractors are not enetered correctly
        if missing_distractor_rows:
            distractor_errors.append(
                "The following rows are missing distractors: "
                + ", ".join(str(missing_distractor_rows))
            )
        if non_alpha_rows:
            distractor_errors.append(
                "The following rows include non-alpha characters: "
                + ", ".join(non_alpha_rows)
            )
        if too_long_rows:
            distractor_errors.append(
                "The distractrors in the following rows are longer than the 24 character limit: "
                + ", ".join(too_long_rows)
            )
        if distractor_errors:
            distractor_errors.append(
                "Resolve missing distractors, replace non-alpha chars and remove words longer than 24 chars."
            )
            error_sections.append({
                'title': 'Distractor column',
                'messages': distractor_errors,
            })

        # Format message if distractors are not unique
        if duplicates:
            duplicate_messages = [
                "The CSV file includes distractors that are duplicates: "
                + ", ".join(f'"{d["distractor"]}" at row {d["row"]}' for d in duplicates),
                "Make sure there are no duplicates before testing again.",
            ]
            error_sections.append({
                'title': 'Duplicate distractors',
                'messages': duplicate_messages,
            })

        # Format message if language of distractor is other than French or English
        if lang_errors:
            error_sections.append({
                'title': 'Language column',
                'messages': [
                    (
                        "Invalid language was entered in some rows. "
                        "Use either French or English, capatialized, to indicate the distractor language. "
                        "Correct this in the CSV before proceeding. Affected rows include: "
                        + ", ".join(lang_errors) + "."
                    ),
                ],
            })

        # Format message if boolean value is not entered correctly to track core vocabulary distractors
        if core_vocab_errors:
            error_sections.append({
                'title': 'Core vocabulary column',
                'messages': [
                    (
                        "Invalid values were intered in column that identfies core vacabulary. "
                        "Review the following rows to make sure they use TRUE or FALSE to identify "
                        "the distractor as core vocabulary word: "
                        + ", ".join(core_vocab_errors) + "."
                    ),
                ],
            })

        # If there are any error message redirect back to same page to give feedback
        if error_sections:
            context = {
                'profile': profile,
                'test_form': test_form,
                'error_sections': error_sections,
            }
            return render(request, self.template_name, context)

        # If check finds no errors redirect to distractor update page
        return redirect(reverse_lazy('staff:distractor_update'))


class DistractorUpdateView(PermissionRequiredMixin, ListView):
    """
    Admin page. GET shows summary of changes that will be made to the database based on
    import_distractor.csv. If the CSV is free of errors, POST updates the Postgres DB.
    """

    permission_required = [
        'frendj.add_distractor',
        'frendj.change_distractor',
    ]
    template_name = 'staff/distractor_update.html'

    # Try to create from CSV file a list of dictionaries to verify SQL data
    def try_to_read_csv(self, file_path):
        data_list = []
        error = False
        try:
            with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
                data_reader = reader(csvfile)
                next(data_reader, None)
                for _, row in enumerate(data_reader, start=2):
                    try:
                        data_list.append({
                            'id': int(row[0].strip()) if row[0].strip() else None,
                            'word': row[3].strip().casefold(),
                            'language': row[1].strip().title(),
                            'core_vocab': (
                                True if row[2].strip().upper() == "TRUE"
                                else False if row[2].strip().upper() == "FALSE"
                                else None
                            ),
                        })
        # If an error occurs format an appropriate error message
                    except (ValueError, IndexError) as e:
                        error = True
                        break
        except FileNotFoundError:
            error = True
        except (OSError, CSV_Error):
            error = True

        return data_list, error

    def check_CSV_for_errors(self, data_list, distractors, error):
        # Loop through CSV data to check each error type starting with ID column checks
        distractor_by_id = {d.id: d for d in distractors}
        final_keys = set()
        seen_ids = set()
        row = 1
        for item in data_list: 
            row += 1
            raw_id = item['id']
            if raw_id is not None:
                if raw_id in seen_ids:
                    error = True
                    break
                seen_ids.add(raw_id)
                if raw_id not in distractor_by_id:
                    error = True
                    break
            # Check that distractors are present and only contain alphabetic characters
            distractor = item['word']
            if not distractor:
                error = True
                break
            elif not ALLOWED_DISTRACTOR.fullmatch(distractor):
                error = True
                break
            if len(distractor) > 24:
                error = True
                break
            # Check the final word/language pair for duplicate CSV rows and updates.
            key = (item['word'].strip().lower(), item['language'].strip().lower())
            if key in final_keys:
                error = True
                break
            final_keys.add(key)
            # Verify that language is either English or French
            if item['language'].strip().title() not in {"English", "French"}:
                error = True
                break
            # Check that value for core vocabulary identification is either True or False
            if item['core_vocab'] not in {True, False}:
                error = True
                break

        return error

    def get(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')

        profile = Profile.objects.get(user=request.user)
        distractors = Distractor.objects.all()
        update_form = CsvForm()

        # Check that distractor ID is entered correctly for updates - Set up base data to verify
        data_list, error = self.try_to_read_csv(DISTRACTOR_CSV_PATH)
        if not error:
            distractors = Distractor.objects.all()
            error = self.check_CSV_for_errors(data_list, distractors, error)

        # If any error was found, redirect back to DistractorTestView
        if error or not data_list:
            return render(request, 'staff/distractor_error_redirect.html')

        # Compare CSV data with database content and get stats
        stored_distractor_count = distractors.count()
        total = 0
        changed = []
        distractors_edited = 0
        new = []
        csv_ids = []

        # Count all the distractors in the data list
        for item in data_list:
            total += 1

            # Count new distractors as those without an ID 
            if not item['id']:
                new.append((item['word'], item['language']))
            # Track all changes made to distractors in the CSV
            else:
                csv_ids.append(int(item['id']))
                distractor_to_be_edited = False
                distractor = distractors.get(id=item['id'])
                if distractor.language != item['language']:
                    changed.append(f"{distractor} (change language): {distractor.language} -> {item['language']}")
                    distractor_to_be_edited = True
                if distractor.word != item['word']:
                    changed.append(f"{distractor} (change distractor): {distractor.word} -> {item['word']}")
                    distractor_to_be_edited = True
                if distractor.core_vocab != item['core_vocab']:
                    changed.append(f"{distractor} (toggle core vocab); {distractor.core_vocab} -> {item['core_vocab']}")
                    distractor_to_be_edited = True
                if distractor_to_be_edited:
                    distractors_edited += 1

        # Count and track the disractors that will be deleted from the database
        distractors_to_be_deleted = []
        for distractor in distractors:
            if distractor.id not in csv_ids:
                distractors_to_be_deleted.append(distractor)
        to_be_deleted_count = len(distractors_to_be_deleted)

        context = {
            'profile': profile,
            'update_form': update_form,
            'stored_distractor_count': stored_distractor_count,
            'new': len(new),
            'added_distractors': new,
            'total_edits': len(changed),
            'distractors_edited': distractors_edited,
            'edited_distractors': changed,
            'to_be_deleted': to_be_deleted_count,
            'distractors_to_be_deleted': distractors_to_be_deleted,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if not request.user.is_superuser:
            return redirect('frendj:home')

        profile = Profile.objects.get(user=request.user)
        distractors = Distractor.objects.all()
        update_form = CsvForm(request.POST)
        if not update_form.is_valid():
            message = "Your request couldn't complete. Please try again. If error persists, contact the support team."
            context = {
                'profile': profile,
                'message': message,
            }
            return render(request, self.template_name, context)

        # Populate / update the database. First set up variables to track changes.
        added_descriptors = 0
        edited_languages = 0
        edited_core_vocabs = 0
        edited_words = 0
        missing_ids = []

        # Final check for CSV errors before updating the database
        data_list, error = self.try_to_read_csv(DISTRACTOR_CSV_PATH)
        try:
            with transaction.atomic():
                distractors = Distractor.objects.select_for_update()
                if not error:
                    error = self.check_CSV_for_errors(data_list, distractors, error)

                if error or not data_list:
                    return render(request, 'staff/distractor_error_redirect.html')

                # Delete distractors with IDs missing from database before adding and editing
                stored_distractor_ids = list(distractors.values_list("pk", flat=True))
                csv_distractor_ids = {
                    int(item['id']) for item in data_list if item.get('id') is not None
                }
                missing_ids = [
                    id_ for id_ in stored_distractor_ids
                    if id_ not in csv_distractor_ids
                ]
                Distractor.objects.filter(id__in=missing_ids).delete()

                # Compare new CSV data to database stored data and update the database
                row = 1
                for dict_obj in data_list:
                    row += 1
                    # Update the distractor if it is already in database (has an ID) and changes were made
                    if id_ := dict_obj['id']:
                        distractor = distractors.get(id=id_)
                        changed = False
                        if distractor.language != dict_obj['language']:
                            distractor.language = dict_obj['language']
                            edited_languages += 1
                            changed = True
                        if distractor.core_vocab != dict_obj['core_vocab']:
                            distractor.core_vocab = dict_obj['core_vocab']
                            edited_core_vocabs += 1
                            changed = True
                        if distractor.word != dict_obj['word']:
                            distractor.word = dict_obj['word']
                            edited_words += 1
                            changed = True
                        if changed:
                            distractor.save()

                    else:
                        Distractor.objects.create(
                            language=dict_obj['language'],
                            core_vocab=dict_obj['core_vocab'],
                            word=dict_obj['word']
                        )
                        added_descriptors += 1

        except IntegrityError as e:
            messages.error(
                request,
                f"The distractor update was not applied because database data conflicts: {e}",
            )
            return redirect(reverse_lazy('staff:distractor_test'))

        # Write a new copy of distractors to CSV after the database transaction.
        temporary_export = None
        try:
            export_data = []
            updated_distractors = Distractor.objects.all()
            for distractor in updated_distractors:
                export_data.append({
                    'id': distractor.id,
                    'language': distractor.language,
                    'core_vocab': str(distractor.core_vocab).upper(),
                    'word': distractor.word,
                })

            export_dir = Path(settings.BASE_DIR)
            export_dir.mkdir(parents=True, exist_ok=True)
            now = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
            export_path = export_dir / f"distractor_export_{now}.csv"

            with NamedTemporaryFile(
                mode='w',
                newline='',
                encoding='utf-8-sig',
                dir=export_dir,
                prefix='.distractor_export_',
                suffix='.tmp',
                delete=False,
            ) as export:
                temporary_export = Path(export.name)
                writer = DictWriter(
                    export,
                    fieldnames=["distractor_id", "language", "core_vocab", "word"]
                )
                writer.writeheader()
                for distractor in export_data:
                    writer.writerow({
                        'distractor_id': distractor['id'],
                        'language': distractor['language'],
                        'core_vocab': distractor['core_vocab'],
                        'word': distractor['word']
                    })
                export.flush()
                os.fsync(export.fileno())

            os.replace(temporary_export, export_path)
        except (OSError, CSV_Error) as e:
            if temporary_export is not None:
                try:
                    temporary_export.unlink(missing_ok=True)
                except OSError:
                    pass
            messages.error(
                request,
                f"The database update committed, but the distractor CSV export failed: {e}",
            )
            return redirect(reverse_lazy('frendj:glossary'))

        # Send this message only after both the database update and export complete.
        messages.success(
            request,
            (
                f"Distractors added: {added_descriptors}\nDescriptor languages edited: {edited_languages}\n"
                f"Distractor core vocab identification edited: {edited_core_vocabs}\n"
                f"Descriptor words edited: {edited_words}\nDistractors deleted: {len(missing_ids)}"
            )
        )

        return redirect(reverse_lazy('frendj:glossary'))