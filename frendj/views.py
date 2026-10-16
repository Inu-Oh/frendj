from django.shortcuts import render

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Exists, F, OuterRef, Q, Value
from django.db.models.functions import ExtractDay, Greatest
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, View, CreateView, ListView

from datetime import timedelta
from difflib import SequenceMatcher
import html
from random import choice
from unidecode import unidecode
import string

from .models import Module, Phrase, Translation, Profile, UserPhraseStrength
from .forms import ProfileForm, TestForm

# Constants for setting user phrase view counts, evaluating accuracy and errors in testing views.
INITIATE_COUNT, UNASSESSED_ACCURACY, UNASSESSED_SCORE, MAX_ERRORS = 1, False, -1, 100
PLUS_5_XP, PLUS_9_XP, QUIZ_LENGTH, RESET_TEST_COUNT, RESET_SCORE = 5, 9, 12, 1, 0


def clear_data_from_session(request, *previous_question_data) -> None:
    if request.session.get(previous_question_data[0]):
        for data_key in previous_question_data:
            try:
                del request.session[data_key]
            except KeyError:
                print(f'Exception Did not clear {data_key} from session.')


def eval_translation(user_answer: str, correct_translation: str) -> tuple[float, int]:
    """
    Evaluates the test score for a translation entered by the user
    in comparison to correct translation.
    """

    user_answer = user_answer.replace("&#x27;", "'").replace("&#45;", "-").replace("&#44;", ",")
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
        user_answer = user_answer.replace("&#x27;", "'").replace("&#45;", "-").replace("&#44;", ",")
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


def end_quiz(request, quiz_name) -> HttpResponseRedirect:
    del request.session['test_count']
    correct_count = request.session['correct_count']
    msg = f'<h5 class="pb-3">{quiz_name} quiz done!</h5><p>You got '
    msg += f'{correct_count} out of {QUIZ_LENGTH}.</p><p class="fs-4">Grade: '
    msg += f'{round( (correct_count / QUIZ_LENGTH) * 100 )}%'
    request.session['quiz_complete_msg'] = msg
    finished_exercise_url = reverse_lazy('frendj:home')
    return redirect(finished_exercise_url)


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

        # Add Quiz completion message to context if present
        if msg := request.session.get('quiz_complete_msg'):
            quiz_complete_msg = msg
            del request.session['quiz_complete_msg']
        else:
            quiz_complete_msg = ""
        
        # Delete session data from exercises if it exists
        session_data_keys = ['phrase', 'user_phrase_strength_id', 'user_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward',
            'module_id', 'testing_view']
        clear_data_from_session(request,*session_data_keys)
        # Test count for Practice, Review and Accent Quiz views is set here, incremented
        # and deleted in respective Quiz view. This circumvents Django bug that fails to delete session data.
        request.session['test_count'] = RESET_TEST_COUNT
        request.session['correct_count'] = RESET_SCORE
        
        # Get phrase counts and progress data. Set dummy 
        phrase_counts = UserPhraseStrength.objects.aggregate(
            unlearned=Count('pk', filter=Q(learned=False, user=request.user)),
            learned=Count('pk', filter=Q(learned=True, user=request.user)),
        )
        total = phrase_counts['learned'] + phrase_counts['unlearned']
        progress = round( (phrase_counts['learned'] * 100) / total ) if total > 0 else 0

        context = {
            'profile': profile,
            'unlearned_phrase_count': phrase_counts['unlearned'],
            'learned_phrase_count': phrase_counts['learned'],
            'progress': progress,
            'quiz_complete_msg': quiz_complete_msg,
            'testing_view': None,
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
        now = timezone.now() # prefer this if updated_at is timezone-aware

        # Below is SQL equivalent to the two queries - TODO learn and delete this note
        #   SELECT phrase.*, module.* FROM phrase
        #       INNER JOIN module ON phrase.module_id = module.id
        #       ORDER BY phrase;
        #   SELECT * FROM phrase_translations WHERE phrase_id IN (...)
        UserPhraseStrength.objects.filter(
            learned=True,
            user=request.user,
            updated_at__lt=now - timedelta(days=1),
        ).update(
            strength=Greatest(
                Value(0),
                F('strength') - ExtractDay(now - F('updated_at')),
            ),
            updated_at=now
        )
            
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
        user_strengths = list(
            UserPhraseStrength.objects.filter(user=request.user)
        )
        strength_by_phrase_id = {
            user_strength.phrase_id: user_strength
            for user_strength in user_strengths
        }

        learned_phrase_count = sum(
            1 for user_strength in user_strengths if user_strength.learned
        )
        phrase_count = Phrase.objects.count()
        phrases = (
            Phrase.objects
            .select_related('module')
            .prefetch_related('phrase_translations')
            .order_by('phrase')
        )
        progress = round( (learned_phrase_count * 100) / phrase_count ) if phrase_count else 0

        search = request.GET.get("search", False)
        if search:
            phrases = phrases.filter(
                Q(phrase__icontains=search)
                | Q(phrase_translations__translation__icontains=search)
            ).distinct()

        # Make a searchable dictionary of phrases with their related strengths and translations
        phrase_data = []
        strength_data = {
            'learned': learned_phrase_count,
            'total': sum(usr_s.strength for usr_s in user_strengths if usr_s.learned),
        }
        for phrase in phrases:
            user_strength = strength_by_phrase_id[phrase.id]
            phrase_data.append({
                "phrase": phrase.phrase,
                "id": phrase.id,
                "language": phrase.language,
                "module": phrase.module,
                "module_id": phrase.module_id,
                "translations": [
                    translation.translation
                    for translation in phrase.phrase_translations.all()
                ],
                "learned": user_strength.learned,
                "strength": user_strength.strength,
            })

        strength_data['average'] = round(
            strength_data['total'] / learned_phrase_count
        ) if (learned_phrase_count > 0) else None

        context = {
            'phrase_data': phrase_data,
            'profile': profile,
            'progress': progress,
            'search': search,
            'phrase_count': phrase_count,
            'strength_data': strength_data,
            'testing_view': None,
        }
        return render(request, self.template_name, context)

class ModulesView(LoginRequiredMixin, ListView):
    """Displays all available and completed modules as button links to learning exercises"""
    template_name = 'frendj/modules.html'

    def get(self, request):
        profile = Profile.objects.get(user = request.user)
        user_phrase_data = UserPhraseStrength.objects.filter(user=request.user)
        phrase_counts = user_phrase_data.aggregate(
            unlearned=Count('pk', filter=Q(learned=False)),
            learned=Count('pk', filter=Q(learned=True)),
        )
        unlearned_phrase_count = phrase_counts['unlearned']
        learned_phrase_count = phrase_counts['learned']
        total = unlearned_phrase_count + learned_phrase_count
        progress = round( (learned_phrase_count * 100) / total ) if total else 0
        unlearned_phrases = UserPhraseStrength.objects.filter(
            user=request.user,
            learned=False,
            phrase__module_id=OuterRef('pk'),
        )
        modules = Module.objects.annotate(
            phrase_count=Count('phrases_in_module'),
            has_unlearned_phrase=Exists(unlearned_phrases),
        ).order_by('name')

        if msg := request.session.get('module_complete_msg'):
            module_complete_msg = msg
            del request.session['module_complete_msg']
        else:
            module_complete_msg = ""

        # Filter for search query in the database
        search = request.GET.get("search", False)
        if search:
            modules = modules.filter(name__icontains=search)

        context = {
            'profile': profile,
            'unlearned_phrase_count': unlearned_phrase_count,
            'learned_phrase_count': learned_phrase_count,
            'progress': progress,
            'modules': modules,
            'module_complete_msg': module_complete_msg,
            'testing_view': None,
            'search': search,
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
        prev_card_sess_keys = ['phrase', 'user_phrase_strength_id', 'user_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_card_sess_keys)

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
                'phrase_count': module_phrase_count,
                'learned_count': learned_count,
                'unlearned_count': module_phrase_count - learned_count,
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'module_progress': module_progress,
                'module': module
            }
            return render(request, self.template_name, context)
        except: # If no unlearned phrase is found, redirect to home page
            user_module_phrase_strength_set = UserPhraseStrength.objects.filter(
                user=request.user,
                phrase__in=phrases
            )
            count, total_strength = 0, 0
            for phrase_strength in user_module_phrase_strength_set:
                count += 1
                total_strength += phrase_strength.strength
            avg_strength = round(total_strength / count)
            msg = f'<h5 class="pb-3">Congrats!</h5><p><b>{module.name.capitalize()}'
            msg += f'</b> module complete</p><p class="fs-4">Grade: {avg_strength}%</p>'
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

        # Clean user's answer and escape any html entities before testing. Initiate score and error counts.
        for tr in translations:
            cleaned_test_phrase = unidecode(tr.translation.lower())
            curr_score, errors = eval_translation(cleaned_answer, cleaned_test_phrase)
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
        if ('testing_view' not in request.session or 
            request.session['testing_view'] != 'frendj:practice'):
            request.session['testing_view'] = 'frendj:practice'

        # End exerice after test count reaches set quiz length
        test_count = request.session.get('test_count')
        if test_count > QUIZ_LENGTH:
            return end_quiz(request, self.__class__.__name__[:-4])

        # Clear session data for previously tested phrase if present
        prev_card_sess_keys = ['phrase', 'user_answer', 'response_accuracy', 
                                'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_card_sess_keys)

        # Select question or redirect if not abailable. Add context.
        profile = Profile.objects.get(user=request.user)
        user_phrase_strength = (
            UserPhraseStrength.objects
                .filter(user=request.user, learned=True)
                .select_related('phrase')
                .order_by('strength', 'pk')
                .first()
        )
        if user_phrase_strength is None:
            return redirect(reverse_lazy('frendj:modules'))
        
        form = TestForm()
        context = {
            'profile': profile,
            'form': form,
            'testing_view': request.session['testing_view'],
            'test_count': f"Card {test_count} of {QUIZ_LENGTH}",
            'progress': round( ( (test_count - 1) / QUIZ_LENGTH) * 100 ),
            'phrase': user_phrase_strength.phrase,
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        user_phrase_strength = (
            UserPhraseStrength.objects
                .filter(user=request.user, learned=True)
                .select_related('phrase')
                .order_by('strength', 'pk')
                .first()
        )
        translations = user_phrase_strength.phrase.phrase_translations.all()

        form = TestForm(request.POST)
        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {request.session['test_count']} of {QUIZ_LENGTH}",
                'progress': round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH) * 100 ),
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': user_phrase_strength.phrase,
            }
            return render(request, self.template_name, context)

        # Clean user's answer and escape any html entities before testing. Initiate score and error counts.
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        cleaned_answer = unidecode(user_answer.lower())
        score = UNASSESSED_SCORE
        errors = MAX_ERRORS

        # Find translation to best match user's answer. Evaluate score and set feedback.       
        for tr in translations:
            cleaned_test_phrase = unidecode(tr.translation.lower())
            curr_score, errors = eval_translation(cleaned_answer, cleaned_test_phrase)
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
            request.session['correct_count'] += 1
        else:
            response_accuracy = False

        # Adjust and save the user's phrase strength
        user_phrase_strength.views += 1
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Prepare data for feedback view
        request.session['phrase'] = user_phrase_strength.phrase.phrase
        request.session['module_id'] = user_phrase_strength.phrase.module.id
        request.session['user_answer'] = user_answer # Used as backup in case of error with HTML
        request.session['response_accuracy'] = response_accuracy
        request.session['phrase_language'] = user_phrase_strength.phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_5_XP
        # Increment test count once quiz is submitted
        request.session['test_count'] += 1

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
        if ('testing_view' not in request.session or 
            request.session['testing_view'] != 'frendj:review'):
            request.session['testing_view'] = 'frendj:review'

        # End exerice after test count reaches set quiz length
        test_count = request.session.get('test_count')
        if test_count > QUIZ_LENGTH:
            return end_quiz(request, self.__class__.__name__[:-4])
            
        # Clear session data for previously tested phrase if present
        prev_card_sess_keys = ['phrase', 'user_answer', 'response_accuracy', 
                                'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_card_sess_keys)

        # Select question or redirect if not abailable. Add context.
        profile = Profile.objects.get(user=request.user)
        user_phrase_strength = (
            UserPhraseStrength.objects
                .filter(user=request.user, learned=True)
                .select_related('phrase')
                .order_by('updated_at', 'pk')
                .first()
        )
        if user_phrase_strength is None:
            return redirect(reverse_lazy('frendj:modules'))

        form = TestForm()
        context = {
            'profile': profile,
            'form': form,
            'testing_view': request.session['testing_view'],
            'test_count': f"Card {test_count} of {QUIZ_LENGTH}",
            'progress': round( ( (test_count - 1) / QUIZ_LENGTH) * 100 ),
            'user_phrase_strength': user_phrase_strength,
            'phrase': user_phrase_strength.phrase,
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        user_phrase_strength = (
            UserPhraseStrength.objects
                .filter(user=request.user, learned=True)
                .select_related('phrase')
                .order_by('updated_at', 'pk')
                .first()
        )
        translations = user_phrase_strength.phrase.phrase_translations.all()

        form = TestForm(request.POST)
        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {request.session['test_count']} of {QUIZ_LENGTH}",
                'progress': round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH) * 100 ),
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'phrase': user_phrase_strength.phrase,
            }
            return render(request, self.template_name, context)

        # Clean user's answer and escape any html entities before testing. Initiate score and error counts.
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        cleaned_answer = unidecode(user_answer.lower())
        score = UNASSESSED_SCORE
        errors = MAX_ERRORS

        # Find translation to match user's answer. Evaluate score and set feedback.
        for tr in translations:
            cleaned_test_phrase = unidecode(tr.translation.lower())
            curr_score, errors = eval_translation(cleaned_answer, cleaned_test_phrase)
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
            request.session['correct_count'] += 1
        else:
            response_accuracy = False

        # Adjust and save the user's phrase strength
        user_phrase_strength.views += 1
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Prepare data for feedback view
        request.session['phrase'] = user_phrase_strength.phrase.phrase
        request.session['module_id'] = user_phrase_strength.phrase.module.id
        request.session['user_answer'] = user_answer # Used as backup in csae of error with HTML
        request.session['response_accuracy'] = response_accuracy
        request.session['phrase_language'] = user_phrase_strength.phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_5_XP
        # Increment test count once quiz is submitted
        request.session['test_count'] += 1

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
        if ('testing_view' not in request.session or
            request.session['testing_view'] != 'frendj:accent'):
            request.session['testing_view'] = 'frendj:accent'

        # End exerice after test count reaches set quiz length
        test_count = request.session.get('test_count')
        if test_count > QUIZ_LENGTH:
            return end_quiz(request, self.__class__.__name__[:-4])

        # Clear session data for previously tested phrase if present
        prev_card_sess_keys = ['phrase', 'user_phrase_strength_id', 'user_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_card_sess_keys)

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
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {test_count} of {QUIZ_LENGTH}",
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'progress': round( ( (test_count - 1) / QUIZ_LENGTH) * 100 ),
                'phrase': phrase,
            }

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
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {request.session['test_count']} of {QUIZ_LENGTH}",
                'user_phrase_strength': user_phrase_strength, # Phrase strength object
                'progress': round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH) * 100 ),
                'phrase': phrase,
            }
            return render(request, self.template_name, context)

        # Clean user's answer, escape any html entities and remove punctuation. Initiate score evaluation.
        user_answer = html.escape(form.cleaned_data['answer'].strip())
        test_user_ans = user_answer.translate(str.maketrans("", "", string.punctuation))
        highest_score = UNASSESSED_SCORE
        
        # Find translation that exactly matches answer. Evaluate score, add points and set feedback.
        for translation in translations:
            test_translation = translation.translation.translate(str.maketrans("", "", string.punctuation))
            score, errors = eval_translation(test_user_ans.lower(), test_translation.lower())
            if test_user_ans == test_translation:
                user_phrase_strength.correct += 1
                profile.xp += PLUS_9_XP
                profile.save()
                response_accuracy = True
                matched_translation = translation.translation
                feedback_html = feedback(user_answer, matched_translation, errors, score)
                request.session['correct_count'] += 1
                break
            elif score > highest_score:
                response_accuracy = False    
        try: 
            feedback_html
        except NameError:
            feedback_html = feedback(user_answer, translations[0].translation, errors, score)
      
        # Adjust and save the user's phrase views and score
        user_phrase_strength.views += 1
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
        request.session['phrase_language'] = phrase.language
        request.session['feedback_html'] = feedback_html
        request.session['xp_reward'] = PLUS_9_XP
        # Increment test count once quiz is submitted
        request.session['test_count'] += 1

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
            progress = round( (user_learned_count / module_phrase_count) * 100 )
        else:
            progress = round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH ) * 100 )

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

        learned_count = round(
                module.phrases_in_module.count() * ( progress / 100 )
            )
        unlearned_count = module.phrases_in_module.count() - learned_count

        context = {
            'profile': profile,
            'user_answer': user_answer, # Used as backup in case of error with HTML
            'response_accuracy': response_accuracy,
            'phrase': phrase,
            'translations': translations,
            'test_count': f"Card {request.session['test_count'] - 1} of {QUIZ_LENGTH}",
            'testing_view': testing_view,
            'result': result,
            'module': module,
            'learned_count': learned_count,
            'unlearned_count': unlearned_count,
            'feedback_html': feedback_html,
            'progress': progress,
            'xp_reward': xp_reward
        }
        return render(request, self.template_name, context)