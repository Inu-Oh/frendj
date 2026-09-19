from django.shortcuts import render

# Create your views here.
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, View, CreateView, ListView

from datetime import datetime
from difflib import SequenceMatcher
import html
from random import choice
from unidecode import unidecode
import string

from .models import Module, Phrase, Translation, Profile, UserPhraseStrength
from .forms import ProfileForm, TestForm

# Constants for setting user phrase view counts, evaluating accuracy and errors in testing views.
INITIATE_COUNT, UNASSESSED_ACCURACY, UNASSESSED_SCORE, MAX_ERRORS = 1, False, -1, 100
PLUS_5_XP, PLUS_9_XP = 5, 9


def clear_data_from_session(request, *previous_question_data):
    if request.session.get(previous_question_data[0]):
        for data_key in previous_question_data:
            try:
                del request.session[data_key]
            except KeyError:
                print(f'Exception Did not clear {data_key} from session.')
                pass


def eval_tranlation(user_answer: str, correct_translation: str) -> tuple[float, int]:
    """
    Evaluates the test score for a translation entered by the user
    in comparison to correct translation.
    """
    
    if user_answer == correct_translation:
        translation_score, error_count = 100, 0
    else:
        matcher = SequenceMatcher(None, a=user_answer, b=correct_translation)
        translation_score = matcher.ratio() * 100

        error_count = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ('replace', 'delete'):
                error_count += (i2 - i1) # Length of segment in user answer
            if tag == 'insert':
                error_count += (j2 - j1) # Length of segment in correct translation
    # TODO - Remove print and dev notes after correcting errors
    print(translation_score, error_count, user_answer, correct_translation)
    return translation_score, error_count

def feedback(
        user_answer: str, 
        correct_translation: str, 
        error_count: int, 
        translation_score: float
    ) -> str:
    """
    Generates HTML style tags to provide better feedback on translation accuracy.
    Used for learn, practice and review exercise view classes.
    """

    # Return no feedback for correct answers
    if translation_score >= 100 and error_count <= 0:
        return f'<span class="text-success">{user_answer}</span>' 
    # Full feedback string is red if too many errors
    elif translation_score < 75 or error_count >= 4: 
        return f'<span class="text-danger">{user_answer}</span>' 
    else: # Provide more detailed feedback if errors are minimal
        matcher = SequenceMatcher(None, a=user_answer, b=correct_translation)
        words = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                words.append(f'<span class="text-danger">{user_answer[i1:i2]}</span>')
            elif tag == 'insert':
                words.append(f'<span class="text-danger">{correct_translation[j1:j2]}</span>')
            elif tag == 'equal':
                words.append(user_answer[i1:i2])
        return f'<span class="text-success">{"".join(words)}</span>' 


class Home(LoginRequiredMixin, TemplateView):
    """Displays the app home page menu with exercises for users and nav bar"""

    template_name = 'frendj/home.html'

    def get(self, request):
        # Redirect to create profile page if the user doesn't have one
        try:
            profile = Profile.objects.get(user = request.user)
        except:
            create_profile_url = reverse_lazy('frendj:create_profile')
            return redirect(create_profile_url)
        
        # Delete session data from exercises if it exists
        session_data_keys = ['phrase', 'user_phrase_strength_id', 'user_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward',
            'test_count', 'module_id']
        clear_data_from_session(request,*session_data_keys)
        
        # Get user phrase strength data for progress
        user_phrase_strength_set = UserPhraseStrength.objects.filter(user=request.user)
        if user_phrase_strength_set.count() > 0:
            unlearned_phrase_count = user_phrase_strength_set.filter(learned=False).count()
            learned_phrase_count = user_phrase_strength_set.filter(learned=True).count()
            progress = int((learned_phrase_count * 100) / (learned_phrase_count + unlearned_phrase_count))
        else:
            progress = 0
        # Set dummy values in case vocabulary database has not been populated
        try:
            unlearned_phrase_count
            learned_phrase_count
        except:
            unlearned_phrase_count = 1
            learned_phrase_count = 0

        context = {
            'profile': profile,
            'unlearned_phrase_count': unlearned_phrase_count,
            'learned_phrase_count': learned_phrase_count,
            'progress': progress,
        }
        return render(request, self.template_name, context)


class ResetView(LoginRequiredMixin, UpdateView):
    """Resets the user's strength for all phrases after each login and redirects home."""
    # Recalculates user phrase after each login based on time elapsed. Login redirects
    # here. The form autosubmits, post updates all user scores then redirects home.
    template_name = 'frendj/reset.html'

    # Login redirects to get and hidden form in template redirects to post.
    def get(self, request):
        return render(request, self.template_name)

    # Post view updates user phrase strenght objecs.
    def post(self, request):
        learned_phrases = UserPhraseStrength.objects.filter(learned=True, user=request.user)

        # Recalculate phrase strength based on last time seen by user
        for phrase in learned_phrases:
            now = datetime.now()
            day_of_last_reset = datetime(
                day=phrase.updated_at.day,
                month=phrase.updated_at.month,
                year=phrase.updated_at.year,
                hour=phrase.updated_at.hour,
                minute=phrase.updated_at.minute
            )
            delta = now - day_of_last_reset
            days_since_reset = delta.days
            
            # Function data for review in server log
            # test_log = f"\nDays since reset for phrase \"{str(phrase.phrase)}\""
            # test_log += f": {days_since_reset}\n  Now                : {now}"
            # test_log += f"\n  Time of last reset : {day_of_last_reset}\n"
            # test_log += f"    strength before recalc : {str(phrase.strength)}"
            # print(test_log)

            # Weaken strength if phrase wasn't tested for longer than a day
            if days_since_reset > 0 and phrase.strength > 25:
                phrase.strength -= days_since_reset
                phrase.save()
            
            # Function data for review in server log - part 2
            # print(f"    strength after recalc  : {str(phrase.strength)}")
            
        success_url = 'frendj:home'
        return redirect(success_url)


class ProfileCreateView(LoginRequiredMixin, CreateView):
    """
    Adds a profile name to greet the user
    Creates objects to track the user's skill with all phrases in the database
    """
    model = Profile
    template_name = 'frendj/create_profile.html'

    def get(self, request):
        form = ProfileForm()
        context = {'form': form}
        return render(request, self.template_name, context)
    
    def post(self, request):
        form = ProfileForm(request.POST)
        if not form.is_valid():
            context = {'form': form}
            return render(request, self.template_name, context)
        
        # Add user to profile form
        profile = form.save(commit=False)
        profile.user = self.request.user
        profile.save()

        # For all phrases, set user strength to 0 and learned to false
        phrases = Phrase.objects.all()
        for phrase in phrases:
            UserPhraseStrength.objects.create(
                phrase = phrase,
                user = self.request.user,
                learned = False,
                strength = 0,
                views = 0,
                correct = 0
            )

        success_url = reverse_lazy('frendj:home')
        return redirect(success_url)


class GlossaryView(LoginRequiredMixin, ListView):
    """
    Searches and list all phrases in the database along with their translations.
    Displays summary of user progress
    """
    template_name = 'frendj/glossary.html'

    def get(self, request):
        profile = Profile.objects.get(user=request.user)
        phrases = Phrase.objects.all().order_by('phrase')
        phrase_count = phrases.count()
        modules = Module.objects.all()
        translations = Translation.objects.all()
        phrase_strength_set = UserPhraseStrength.objects.filter(user=request.user)
        if phrase_strength_set.count() > 0:
            unlearned_phrase_count = phrase_strength_set.filter(learned=False).count()
            learned_phrase_count = phrase_strength_set.filter(learned=True).count()
        else:
            unlearned_phrase_count, learned_phrase_count = 1, 0
        progress = int((learned_phrase_count * 100) / (learned_phrase_count + unlearned_phrase_count))

        # Create list of dicts for faster data access and search response on web page load
        phrase_data = []
        strength_data = { 'learned': 0, 'total': 0 }
        for phrase in phrases:
            item = {}
            item["phrase"] = phrase.phrase
            item["id"] = phrase.id
            item["language"] = phrase.language
            item["module"] = phrase.module
            module = modules.get(name=phrase.module)
            item["module_id"] = module.id
            item_translations = translations.filter(phrase=phrase)
            item["translations"] = []
            for item_translation in item_translations:
                item["translations"].append(item_translation.translation)
            user_strength = phrase_strength_set.get(phrase=phrase)
            item["learned"] = user_strength.learned
            item["strength"] = user_strength.strength
            phrase_data.append(item)

            # Calculate overall average user strength
            if user_strength.learned:
                strength_data['learned'] += 1
                strength_data['total'] += user_strength.strength
        if learned_phrase_count > 0:
            strength_data['average'] = round(strength_data['total'] / strength_data['learned'])
        else:
            strength_data['average'] = None

        # Search result implemention for search bar
        search = request.GET.get("search", False)
        if search:
            phrase_data = [d for d in phrase_data if search.lower() in d["phrase"].lower() or search in " ".join(d["translations"]).lower()]

        context = {
            'phrase_data': phrase_data,
            'profile': profile,
            'progress': progress,
            'search': search,
            'phrase_count': phrase_count,
            'strength_data': strength_data,
        }
        return render(request, self.template_name, context)


class ModulesView(LoginRequiredMixin, ListView):
    """Displays all available and completed modules as button links to learning exercises"""
    template_name = 'frendj/modules.html'

    def get(self, request):
        profile = Profile.objects.get(user = request.user)
        phrases = Phrase.objects.all()
        user_phrase_data = UserPhraseStrength.objects.filter(user=request.user)
        if user_phrase_data.count() > 0:
            unlearned_phrase_set = user_phrase_data.filter(learned=False)
            unlearned_phrase_count = unlearned_phrase_set.count()
            learned_phrase_set= user_phrase_data.filter(learned=True)
            learned_phrase_count = learned_phrase_set.count()
        else:
            unlearned_phrase_count, learned_phrase_count = 1, 0
        progress = int((learned_phrase_count * 100) / (learned_phrase_count + unlearned_phrase_count))
        modules = Module.objects.all()

        if msg := request.session.get('module_complete_msg'):
            module_complete_msg = msg
            del request.session['module_complete_msg']
        else:
            module_complete_msg = ""

        # Create lists of modules the user has and has not completed
        open_modules = []
        closed_modules = []
        for module in modules:
            # Get all phrases in module to compare with learned and unlearned phrases
            phrase_set = phrases.filter(module=module)
            # If module includes unlearned phrases add to open modules list...
            for phrase in phrase_set:
                for unlearned_phrase in unlearned_phrase_set:
                    if unlearned_phrase.phrase == phrase:
                        if not module in open_modules:
                            open_modules.append(module)
        # ...else add to closed modules list
        for module in modules:
            if not module in open_modules:
                closed_modules.append(module)

        context = {
            'profile': profile,
            'unlearned_phrase_count': unlearned_phrase_count,
            'learned_phrase_count': learned_phrase_count,
            'progress': progress,
            'modules': modules,
            'open_modules': open_modules,
            'closed_modules': closed_modules,
            'module_complete_msg': module_complete_msg,
        }
        return render(request, self.template_name, context)


class LearnView(LoginRequiredMixin, View):
    """
    Test form. Prompts user to translate phrases from a learning module. Chooses
    random phrase one at a time. (Does not test accent and punctuation.)
    """
    template_name = 'frendj/learn.html'

    def get(self, request, pk):
        # Clear session data for previously tested phrase if present
        prev_question_keys = ['phrase', 'user_phrase_strength_id', 'user_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_question_keys)

        # Get data for current phrase to test and context
        profile = Profile.objects.get(user=request.user)
        form = TestForm()
        module = Module.objects.get(id=pk)
        phrases = module.phrases_in_module.all()
        try: # Select random unlearned phrase for testing and save it to session for access in POST
            user_unlearned_phrase_objects = UserPhraseStrength.objects.filter(
                learned=False,
                user=request.user,
                phrase__in=phrases
            )
            user_phrase_strength = choice(user_unlearned_phrase_objects)
            phrase = phrases.get(id=user_phrase_strength.phrase_id)
            request.session['user_phrase_strength_id'] = user_phrase_strength.id

            # Module progress
            module_phrase_count = phrases.count()
            learned_count = UserPhraseStrength.objects.filter(
                learned=True,
                user=request.user,
                phrase__in=phrases
            ).count()
            module_progress = round( (learned_count / module_phrase_count) * 100 )

            context = {
                'profile': profile,
                'form': form,
                'phrase': phrase,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'module_progress': module_progress,
                'module_name': module.name
            }
            return render(request, self.template_name, context)
        except: # If no unlearned phrase is found, redirect to home page
            msg = f'Congrats! You finished the "{module.name}" module.'
            request.session['module_complete_msg'] = msg
            finished_learning_url = reverse_lazy('frendj:modules')
            return redirect(finished_learning_url)
    
    def post(self, request, pk):
        profile = Profile.objects.get(user=request.user)
        form = TestForm(request.POST)
        
        # Get an unlearned phrase for testing and its translations
        user_phrase_strength = UserPhraseStrength.objects.get(
                    id=request.session.get('user_phrase_strength_id')
                )
        phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)
        translations = phrase.phrase_translations.all()
 
        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'phrase': phrase,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
            }
            return render(request, self.template_name, context)

        # Clean user's answer and escape any html entities before testing
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        cleaned_answer = unidecode(user_answer.lower())

        # Track phrase as learned by the user. Initiate view, score and error counts
        user_phrase_strength.learned = True
        user_phrase_strength.views = INITIATE_COUNT
        score = UNASSESSED_SCORE
        errors = MAX_ERRORS

        # Find translation to match user's answer. Evaluate score and set feedback.       # Find a translation that best matches the user's answer. Evaluate score & errors
        for tr in translations:
            cleaned_test_phrase = unidecode(tr.translation.lower())
            curr_score, errors = eval_tranlation(cleaned_answer, cleaned_test_phrase)
            if curr_score > score:
                score = curr_score
                matched_translation = tr.translation
                feedback_html = feedback(user_answer, matched_translation, errors, score)
        try: 
            feedback_html
        except NameError:
            feedback_html = feedback(user_answer, translations[0].translation, errors, score)

        # If evaluation passes 90%, add points to user profile and raise user phrase strength
        if score >= 90:
            user_phrase_strength.correct += 1
            user_phrase_strength.strength = round(score)
            profile.xp += PLUS_5_XP
            profile.save()
            response_accuracy = True
        else:
            response_accuracy = False
        user_phrase_strength.save()

        # Prepare data for feedback view
        request.session['phrase'] = user_phrase_strength.phrase.phrase
        request.session['user_answer'] = user_answer # Backup in csae of error with HTML
        request.session['response_accuracy'] = response_accuracy
        request.session['testing_view'] = 'frendj:learn'
        request.session['module_id'] = pk
        request.session['phrase_language'] = phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_5_XP

        # Redirect to feedback if post succeeds
        success_url = reverse_lazy('frendj:feedback')
        return redirect(success_url)


class PracticeView(LoginRequiredMixin, View):
    """
    Test form. Prompts user to translate phrases one at a time. Selects user's
    weakest phrase each time. (Does not test accent and punctuation.)
    """
    template_name = 'frendj/practice.html'

    def get(self, request):
        # Set or reset the exercise session test count. End exerice after count 15.
        try:
            test_count = request.session.get('test_count')
            if test_count >= 12:
                request.session['test_count'] = 0
                finished_exercise_url = reverse_lazy('frendj:home')
                return redirect(finished_exercise_url)
        except:
            request.session['test_count'] = 0

        # Clear session data for previously tested phrase if present
        prev_question_keys = ['phrase', 'user_answer', 'response_accuracy', 
                                'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_question_keys)

        # Select question or redirect if not abailable. Add context.
        profile = Profile.objects.get(user=request.user)
        form = TestForm()
        try:
            phrase_strength_set = UserPhraseStrength.objects.filter(learned=True, user=request.user)
            user_phrase_strength = phrase_strength_set.earliest('strength')
            phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)

            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': phrase,
            }
            # Increment test count for each phrase test before passing to session
            request.session['test_count'] += 1

            return render(request, self.template_name, context)
        except:
            start_learning_url = reverse_lazy('frendj:modules')
            return redirect(start_learning_url)
    
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        form = TestForm(request.POST)
        phrase_strength_set = UserPhraseStrength.objects.filter(learned=True, user=request.user)
        user_phrase_strength = phrase_strength_set.earliest('strength')
        phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)
        module = Module.objects.get(name=phrase.module)
        translations = phrase.phrase_translations.all()

        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': phrase,
            }
            return render(request, self.template_name, context)

        # Clean user's answer and escape any html entities before testing
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        cleaned_answer = unidecode(user_answer.lower())

        # Track phrase as learned by the user. Initiate view, score and error counts
        user_phrase_strength.learned = True
        user_phrase_strength.views = INITIATE_COUNT
        score = UNASSESSED_SCORE
        errors = MAX_ERRORS

        # Find translation to match user's answer. Evaluate score and set feedback.       # Find a translation that best matches the user's answer and evaluate score and errors
        for tr in translations:
            cleaned_test_phrase = unidecode(tr.translation.lower())
            curr_score, errors = eval_tranlation(cleaned_answer, cleaned_test_phrase)
            if curr_score > score:
                score = curr_score
                matched_translation = tr.translation
                feedback_html = feedback(user_answer, matched_translation, errors, score)
        try: 
            feedback_html
        except NameError:
            feedback_html = feedback(user_answer, translations[0].translation, errors, score)

        # If evaluation passes mark, add points to user profile
        if score >= 90:
            user_phrase_strength.correct += 1
            response_accuracy = True
            profile.xp += PLUS_5_XP
            profile.save()
        else:
            response_accuracy = False

        # Adjust and save the user's phrase strength
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Prepare data for feedback view
        request.session['phrase'] = user_phrase_strength.phrase.phrase
        request.session['module_id'] = module.id
        request.session['user_answer'] = user_answer # Used as backup in case of error with HTML
        request.session['response_accuracy'] = response_accuracy
        request.session['testing_view'] = 'frendj:practice'
        request.session['phrase_language'] = phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_5_XP

        # Redirect to feedback if post succeeds
        success_url = reverse_lazy('frendj:feedback')
        return redirect(success_url)


class ReviewView(LoginRequiredMixin, View):
    """
    Test form. Prompts user to translate phrases one at a time. Selects phrase not 
    seen by user in longest time. (Does not test accent and punctuation.)
    """
    template_name = 'frendj/review.html'

    def get(self, request):
        # Set or reset the exercise session test count. End exerice after count 15.
        try:
            test_count = request.session.get('test_count')
            if test_count >= 15:
                request.session['test_count'] = 0
                finished_exercise_url = reverse_lazy('frendj:home')
                return redirect(finished_exercise_url)
        except:
            request.session['test_count'] = 0
            
        # Clear session data for previously tested phrase if present
        prev_question_keys = ['phrase', 'user_answer', 'response_accuracy', 
                                'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_question_keys)

        # Select question or redirect if not abailable. Add context.
        profile = Profile.objects.get(user=request.user)
        form = TestForm()
        try:
            phrase_strength_set = UserPhraseStrength.objects.filter(learned=True, user=request.user)
            user_phrase_strength = phrase_strength_set.earliest('updated_at')
            phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)

            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength,
                'phrase': phrase,
            }
            # Increment test count for each phrase test before passing to session
            request.session['test_count'] += 1

            return render(request, self.template_name, context)
        except:
            start_learning_url = reverse_lazy('frendj:modules')
            return redirect(start_learning_url)
    
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        form = TestForm(request.POST)
        phrase_strength_set = UserPhraseStrength.objects.filter(learned=True, user=request.user)
        user_phrase_strength = phrase_strength_set.earliest('updated_at')
        phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)
        module = Module.objects.get(name=phrase.module)
        translations = phrase.phrase_translations.all()

        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': phrase,
            }
            return render(request, self.template_name, context)

        # Clean user's answer and escape any html entities before testing
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        cleaned_answer = unidecode(user_answer.lower())

        # Track phrase as learned by the user. Initiate view, score and error counts
        user_phrase_strength.learned = True
        user_phrase_strength.views = INITIATE_COUNT
        score = UNASSESSED_SCORE
        errors = MAX_ERRORS

        # Find translation to match user's answer. Evaluate score and set feedback.
        for tr in translations:
            cleaned_test_phrase = unidecode(tr.translation.lower())
            curr_score, errors = eval_tranlation(cleaned_answer, cleaned_test_phrase)
            if curr_score > score:
                score = curr_score
                matched_translation = tr.translation
                feedback_html = feedback(user_answer, matched_translation, errors, score)
        try: 
            feedback_html
        except NameError:
            feedback_html = feedback(user_answer, translations[0].translation, errors, score)

        # If evaluation passes mark, add points to user profile and raise user phrase strength
        if score >= 90:
            user_phrase_strength.correct += 1
            profile.xp += PLUS_5_XP
            profile.save()
            response_accuracy = True
        else:
            response_accuracy = False

        # Adjust and save the user's phrase strength
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Prepare data for feedback view
        request.session['phrase'] = user_phrase_strength.phrase.phrase
        request.session['module_id'] = module.id
        request.session['user_answer'] = user_answer # Used as backup in csae of error with HTML
        request.session['response_accuracy'] = response_accuracy
        request.session['testing_view'] = 'frendj:review'
        request.session['phrase_language'] = phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_5_XP

        # Redirect to feedback if post succeeds
        success_url = reverse_lazy('frendj:feedback')
        return redirect(success_url)


class AccentView(LoginRequiredMixin, View):
    """
    Rigorous test form. Prompts user to translate phrases one at a time. Selects
    phrase randomly. Tests accent and punctuation.
    """
    template_name = 'frendj/accent.html'

    def get(self, request):
        # Set or reset the exercise session test count. End exerice after count 15.
        try:
            test_count = request.session.get('test_count')
            if test_count >= 12:
                request.session['test_count'] = 0
                finished_exercise_url = reverse_lazy('frendj:home')
                return redirect(finished_exercise_url)
        except:
            request.session['test_count'] = 0

        # Clear session data for previously tested phrase if present
        prev_question_keys = ['phrase', 'user_phrase_strength_id', 'user_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_question_keys)

        profile = Profile.objects.get(user=request.user)
        form = TestForm()

        # Select question or redirect if not abailable. Add context.
        try: 
            phrase_strength_set = UserPhraseStrength.objects.filter(learned=True, user=request.user)
            user_phrase_strength = choice(phrase_strength_set)
            phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)

            # Save phrase data to session to be access in POST
            request.session['user_phrase_strength_id'] = user_phrase_strength.id

            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': phrase,
            }
            # Increment test count for each phrase test before passing to session
            request.session['test_count'] += 1

            return render(request, self.template_name, context)
        except:
            start_learning_url = reverse_lazy('frendj:modules')
            return redirect(start_learning_url)
    
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        form = TestForm(request.POST)
        user_phrase_strength = UserPhraseStrength.objects.get(
                    id=request.session.get('user_phrase_strength_id')
                )
        phrase = Phrase.objects.get(id=user_phrase_strength.phrase_id)
        module = Module.objects.get(name=phrase.module)
        translations = phrase.phrase_translations.all()

        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': phrase,
            }
            return render(request, self.template_name, context)

        # Clean user's answer, escape any html entities, and remove punctuation, before testing
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        test_user_ans = user_answer.translate(str.maketrans("", "", string.punctuation))

        # Increment user view of current phrase. Set variable to support feedback.
        user_phrase_strength.views += 1
        highest_score = UNASSESSED_SCORE
        
        # Find translation that exactly matches answer. Evaluate score, add points and set feedback.
        for translation in translations:
            test_translation = translation.translation.translate(str.maketrans("", "", string.punctuation))
            score, errors = eval_tranlation(test_user_ans.lower(), test_translation.lower())
            if test_user_ans == test_translation:
                user_phrase_strength.correct += 1
                profile.xp += PLUS_9_XP
                profile.save()
                response_accuracy = True
                matched_translation = translation.translation
                feedback_html = feedback(user_answer, matched_translation, errors, score)
                break
            # TODO - review the elif block / Is it still needed.
            elif score > highest_score:
                response_accuracy = False    
        try: 
            feedback_html
        except NameError:
            feedback_html = feedback(user_answer, translations[0].translation, errors, score)
      
        # Adjust and save the user's phrase score
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Prepare data for feedback view
        request.session['phrase'] = user_phrase_strength.phrase.phrase
        request.session['user_answer'] = user_answer  # Used as backup in csae of error with HTML
        request.session['response_accuracy'] = response_accuracy
        request.session['module_id'] = module.id
        request.session['testing_view'] = 'frendj:accent'
        request.session['phrase_language'] = phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_9_XP

        # Redirect to feedback if post succeeds
        success_url = reverse_lazy('frendj:feedback')
        return redirect(success_url)


class FeedbackView(LoginRequiredMixin, View):
    """Displays feedback on user translation accuracy and points earned."""

    template_name = 'frendj/feedback.html'

    def get(self, request):
        profile = Profile.objects.get(user=request.user)
        phrase_str = request.session.get('phrase')
        module = Module.objects.get(id=request.session.get('module_id'))
        phrase = Phrase.objects.get(
            phrase=phrase_str,
            language=request.session.get('phrase_language'),
            module=module
        )
        
        user_answer = request.session.get('user_answer')
        response_accuracy = request.session.get('response_accuracy')
        translations = Translation.objects.filter(phrase=phrase)
        testing_view = request.session.get('testing_view')
        feedback_html = request.session.get('feedback_html')
        xp_reward = request.session.get('xp_reward')

        # Module progress - for LearnView only
        if testing_view == "frendj:learn":
            module_phrases = Phrase.objects.filter(module=module)
            module_phrase_count = module_phrases.count()
            user_learned_count = UserPhraseStrength.objects.filter(
                learned=True,
                user=request.user,
                phrase__in=module_phrases
            ).count()
            module_progress = round( (user_learned_count / module_phrase_count) * 100 )
        else:
            module_progress = None

        # Feedback phrases
        if response_accuracy:
            correct = [
                "Amazing", "Awesome", "Great", "Yes!", "You got it", "Wow",
                "You're good at this", "You're great!", "You're awesome"
                ]
            result = choice(correct)
        else:
            wrong = [
                "Better luck next time", "Keep practicing", "Keep at it",
                "You'll get it next time", "It'll stick eventually"
                ]
            result = choice(wrong)
        try:
            module_id = request.session.get('module_id')
        except:
            module_id = None

        context = {
            'profile': profile,
            'user_answer': user_answer, # Used as backup in case of error with HTML
            'response_accuracy': response_accuracy,
            'phrase': phrase,
            'translations': translations,
            'testing_view': testing_view,
            'result': result,
            'module_id': module_id,
            'feedback_html': feedback_html,
            'module_progress': module_progress,
            'module_name': module.name,
            'xp_reward': xp_reward
        }
        # Retrieve and pass on test count for the current exercise session
        return render(request, self.template_name, context)