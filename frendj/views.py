from django.shortcuts import render

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Exists, ExpressionWrapper, F, IntegerField, OuterRef, Q, Sum, Value
from django.db.models.functions import ExtractDay, Greatest, NullIf
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, View, CreateView, ListView

from datetime import timedelta
from difflib import SequenceMatcher
import html
from random import choice
from unidecode import unidecode
import string
import re

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


def eval_answer(raw_answer: str, correct_translation: str) -> tuple[float, int]:
    """
    Evaluates the test score for a translation entered by the user
    in comparison to a correct translation.
    """
    def normalize(text: str) -> str:
        text = unidecode(html.unescape(text)).casefold()
        return "".join(char for char in text if char.isalnum())

    answer = normalize(raw_answer)
    reference = normalize(correct_translation)
    matcher = SequenceMatcher(None, a=answer, b=reference)
    score = matcher.ratio() * 100

    error_count = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            error_count += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            error_count += i2 - i1
        elif tag == "insert":
            error_count += j2 - j1

    print(score, error_count)
    return score, error_count


def feedback(
        raw_answer: str, 
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
        return format_html('<span class="text-success">{}</span>', raw_answer) 
    # Full feedback string is red if too many errors
    elif translation_score < 50 or error_count >= 6: 
        return format_html('<span class="text-danger">{}</span>', raw_answer) 
    else: # Highlight misspelled words
        display_answer = html.unescape(raw_answer)
        answer_matches = list(re.finditer(r"\w+", display_answer))
        answer = [match.group().casefold() for match in answer_matches]
        reference = re.findall(r"\w+", html.unescape(correct_translation).casefold())

        distances = [
            [0] * (len(reference) + 1)
            for _ in range(len(answer) + 1)
        ]
        for i in range(len(answer) + 1):
            distances[i][0] = i
        for j in range(len(reference) + 1):
            distances[0][j] = j
        for i, word in enumerate(answer, start=1):
            for j, expected in enumerate(reference, start=1):
                distances[i][j] = min(
                    distances[i - 1][j] + 1,
                    distances[i][j - 1] + 1,
                    distances[i - 1][j - 1] + (word != expected),
                )

        misspelled = set()
        i, j = len(answer), len(reference)
        while i or j:
            if (
                i and j and answer[i - 1] == reference[j - 1]
                and distances[i][j] == distances[i - 1][j - 1]
            ):
                i -= 1
                j -= 1
            elif (
                i and j
                and distances[i][j] == distances[i - 1][j - 1] + 1
            ):
                misspelled.add(i - 1)
                i -= 1
                j -= 1
            elif i and distances[i][j] == distances[i - 1][j] + 1:
                misspelled.add(i - 1)
                i -= 1
            else:
                j -= 1

        parts = []
        position = 0
        for index, match in enumerate(answer_matches):
            parts.append(display_answer[position:match.start()])
            word = display_answer[match.start():match.end()]
            if index in misspelled:
                parts.append(
                    format_html('<span class="text-danger">{}</span>', word)
                )
            else:
                parts.append(word)
            position = match.end()
        parts.append(display_answer[position:])
        html_str = format_html_join("", "{}", ((part,) for part in parts))
        return format_html('<span class="text-success">{}</span>', html_str)


def end_quiz(request, quiz_name) -> HttpResponseRedirect:
    del request.session['test_count']
    correct_count = request.session['correct_count']
    msg = f'<h5 class="pb-3">{quiz_name} quiz done!</h5><p>You got '
    msg += f'{correct_count} out of {QUIZ_LENGTH}.</p><p class="fs-4">Grade: '
    msg += f'{round( (correct_count / QUIZ_LENGTH) * 100 )}%'
    request.session['quiz_complete_msg'] = msg
    return redirect(reverse_lazy('frendj:home'))


def match_answer(form, translations):
    # Set up all data needed to evaluate the user answer
    raw_answer = form.cleaned_data['answer'].strip()
    best_translation = None
    best_score = UNASSESSED_SCORE
    least_errors = MAX_ERRORS

    # Evaluate the user's answer against all translations and generate feedback
    for translation in translations:
        current_score, current_errors = eval_answer(
            raw_answer, translation.translation
        )
        if current_score > best_score:
            best_score = current_score
            least_errors = current_errors
            best_translation = translation.translation
        
    if best_translation is None:
        best_translation = translations[0]
    
    feedback_html = feedback(raw_answer, best_translation, least_errors, best_score)

    return best_score, feedback_html


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
        session_data_keys = ['phrase', 'module_id', 'xp_reward', 'response_accuracy', 
            'user_phrase_strength_id', 'phrase_language', 'feedback_html', 'testing_view']
        clear_data_from_session(request,*session_data_keys)
        # Test count for Practice, Review and Accent Quiz views is set here, incremented
        # and deleted in respective Quiz view. This circumvents Django bug that fails to delete session data.
        request.session.update({
            'test_count': RESET_TEST_COUNT,
            'correct_count': RESET_SCORE
        })
        
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
        return redirect('frendj:home')


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
        return redirect(reverse_lazy('frendj:home'))


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
        total = phrase_counts['unlearned'] + phrase_counts['learned']
        progress = round( (phrase_counts['learned'] * 100) / total ) if total else 0
        unlearned_phrases = UserPhraseStrength.objects.filter(
            user=request.user,
            learned=False,
            phrase__module_id=OuterRef('pk'),
        )
        modules = Module.objects.annotate(
            phrase_count=Count('phrases_in_module', distinct=True),
            learned_phrase_count=Count(
                'phrases_in_module__userphrasestrength',
                filter=Q(
                    phrases_in_module__userphrasestrength__user=request.user,
                    phrases_in_module__userphrasestrength__learned=True,
                ),
                distinct=True,
            ),
            progress=ExpressionWrapper(
                F('learned_phrase_count') * 100 / NullIf(F('phrase_count'), Value(0)),
                output_field=IntegerField(),
            ),
            total_strength=Sum('phrases_in_module__userphrasestrength__strength'),
            strength=ExpressionWrapper(
                F('total_strength') / NullIf(F('learned_phrase_count'), Value(0)),
                output_field=IntegerField(),
            ),
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
            'learned_phrase_count': phrase_counts['learned'],
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
        prev_card_sess_keys = ['phrase', 'user_phrase_strength_id', 'raw_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_card_sess_keys)

        # Get data for current phrase to test and context
        profile = Profile.objects.get(user=request.user)
        form = TestForm()
        module = Module.objects.get(id=pk)
        user_phrase_data = UserPhraseStrength.objects.filter(
            user=request.user, phrase__module_id=pk
        )
        counts = user_phrase_data.aggregate(
            unlearned=Count('pk', filter=Q(learned=False)),
            learned=Count('pk', filter=Q(learned=True)),
            total=Count('pk'),
            total_module_strength=Sum('strength'),
        )

        # Select random unlearned phrase for testing. Save to session for access in POST
        if counts['unlearned'] > 0:
            user_phrase_strength = user_phrase_data.filter(learned=False).order_by('?').first() 
            request.session['user_phrase_strength_id'] = user_phrase_strength.id
            module_progress = round(
                (counts['learned'] / counts['total']) * 100 
            ) if counts['total'] > 0 else 0

            context = {
                'profile': profile,
                'form': form,
                'module': module,
                'phrase': user_phrase_strength.phrase,
                'phrase_count':counts['total'],
                'learned_count': counts['learned'],
                'unlearned_count': counts['unlearned'],
                'user_phrase_strength': user_phrase_strength,
                'module_progress': module_progress,
            }
            return render(request, self.template_name, context)
        else: # If no unlearned phrase is found, redirect to home page with completion message
            if counts['total'] > 0 and counts['total_module_strength'] is not None:
                avg_strength = round(counts['total_module_strength'] / counts['total'])
            else:
                avg_strength = 0
            msg = f'<h5 class="pb-3">Congrats!</h5><p><b>{module.name.capitalize()}'
            msg += f'</b> module complete</p><p class="fs-4">Grade: {avg_strength}%</p>'
            request.session['module_complete_msg'] = msg
            return redirect(reverse_lazy('frendj:modules'))
    
    def post(self, request, pk):
        profile = Profile.objects.get(user=request.user)
        form = TestForm(request.POST)
        
        # Get an unlearned phrase for testing and its translations
        user_phrase_strength = UserPhraseStrength.objects.get(
                    id=request.session.get('user_phrase_strength_id')
                )
        phrase = user_phrase_strength.phrase
        translations = phrase.phrase_translations.all()
 
        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength,
                'phrase': phrase,
            }
            return render(request, self.template_name, context)

        best_score, feedback_html = match_answer(form, translations)

        # If evaluation passes 90%, add points to user profile and raise user phrase strength
        user_phrase_strength.learned = True
        user_phrase_strength.views = INITIATE_COUNT
        if best_score >= 90:
            user_phrase_strength.correct += 1
            user_phrase_strength.strength = round(best_score)
            profile.xp += PLUS_5_XP
            profile.save()
            response_accuracy = True
        else:
            response_accuracy = False
        user_phrase_strength.save()

        # Store data in session for feedback view
        request.session.update({
            'phrase_id': user_phrase_strength.phrase.id,
            'response_accuracy': response_accuracy,
            'testing_view': 'frendj:learn',
            'feedback_html': feedback_html,
            'xp_reward': PLUS_5_XP,
        })

        # Redirect to feedback if post succeeds
        return redirect(reverse_lazy('frendj:feedback'))


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
        prev_card_sess_keys = ['phrase', 'raw_answer', 'response_accuracy', 
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
            'phrase': user_phrase_strength.phrase,
            'testing_view': request.session['testing_view'],
            'test_count': f"Card {test_count} of {QUIZ_LENGTH}",
            'progress': round( ( (test_count - 1) / QUIZ_LENGTH) * 100 ),
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
                'user_phrase_strength': user_phrase_strength,
                'phrase': user_phrase_strength.phrase,
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {request.session['test_count']} of {QUIZ_LENGTH}",
                'progress': round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH) * 100 ),
            }
            return render(request, self.template_name, context)

        best_score, feedback_html = match_answer(form, translations)

        # Increment views. Add points if score passes and update user profile and phrase strength
        user_phrase_strength.views += 1
        if best_score >= 90:
            user_phrase_strength.correct += 1
            response_accuracy = True
            profile.xp += PLUS_5_XP
            profile.save()
            request.session['correct_count'] += 1
        else:
            response_accuracy = False
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Store data in session for feedback view and increment test count
        test_count = request.session['test_count'] + 1
        request.session.update({
            'phrase_id': user_phrase_strength.phrase.id,
            'response_accuracy': response_accuracy,
            'feedback_html': feedback_html,
            'xp_reward': PLUS_5_XP,
            'test_count': test_count,
        })

        # Redirect to feedback if post succeeds
        return redirect(reverse_lazy('frendj:feedback'))


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
        prev_card_sess_keys = ['phrase', 'raw_answer', 'response_accuracy', 
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
            'user_phrase_strength': user_phrase_strength,
            'phrase': user_phrase_strength.phrase,
            'testing_view': request.session['testing_view'],
            'test_count': f"Card {test_count} of {QUIZ_LENGTH}",
            'progress': round( ( (test_count - 1) / QUIZ_LENGTH) * 100 ),
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
                'user_phrase_strength': user_phrase_strength,
                'phrase': user_phrase_strength.phrase,
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {request.session['test_count']} of {QUIZ_LENGTH}",
                'progress': round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH) * 100 ),
            }
            return render(request, self.template_name, context)

        best_score, feedback_html = match_answer(form, translations)

        # Increment views. Add points if score passes and update user profile and phrase strength
        user_phrase_strength.views += 1
        if best_score >= 90:
            user_phrase_strength.correct += 1
            response_accuracy = True
            profile.xp += PLUS_5_XP
            profile.save()
            request.session['correct_count'] += 1
        else:
            response_accuracy = False
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Store data in session for feedback view and increment test count
        test_count = request.session['test_count'] + 1
        request.session.update({
            'phrase_id': user_phrase_strength.phrase.id,
            'response_accuracy': response_accuracy,
            'feedback_html': feedback_html,
            'xp_reward': PLUS_5_XP,
            'test_count': test_count,
        })

        # Redirect to feedback if post succeeds
        return redirect(reverse_lazy('frendj:feedback'))


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
        prev_card_sess_keys = ['phrase', 'user_phrase_strength_id', 'raw_answer',
            'response_accuracy', 'phrase_language', 'feedback_html', 'xp_reward']
        clear_data_from_session(request,*prev_card_sess_keys)

        profile = Profile.objects.get(user=request.user)
        form = TestForm()

        # Select question or redirect if not abailable. Add context.
        user_phrase_strength = (
            UserPhraseStrength.objects
                .filter(user=request.user, learned=True)
                .order_by('?')
                .first()
        )

        if user_phrase_strength is None:
            return redirect(reverse_lazy('frendj:modules'))
        
        # Save phrase data to session to be access in POST
        request.session['user_phrase_strength_id'] = user_phrase_strength.id

        context = {
            'profile': profile,
            'form': form,
            'user_phrase_strength': user_phrase_strength,
            'phrase': user_phrase_strength.phrase,
            'testing_view': request.session['testing_view'],
            'test_count': f"Card {test_count} of {QUIZ_LENGTH}",
            'progress': round( ( (test_count - 1) / QUIZ_LENGTH) * 100 ),
        }

        return render(request, self.template_name, context)
    
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        form = TestForm(request.POST)
        user_phrase_strength = (
            UserPhraseStrength.objects
                .get(id=request.session.get('user_phrase_strength_id'))
        )
        translations = user_phrase_strength.phrase.phrase_translations.all()

        if not form.is_valid():
            context = {
                'profile': profile,
                'form': form,
                'user_phrase_strength': user_phrase_strength,
                'phrase': user_phrase_strength.phrase,
                'testing_view': request.session['testing_view'],
                'test_count': f"Card {request.session['test_count']} of {QUIZ_LENGTH}",
                'progress': round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH) * 100 ),
            }
            return render(request, self.template_name, context)

        # Set up all data needed to evaluate the user answer
        raw_answer = form.cleaned_data['answer'].strip()
        normalized_answer = raw_answer.translate(str.maketrans("", "", string.punctuation))
        matched_translation = None
        best_score = UNASSESSED_SCORE
        least_errors = MAX_ERRORS

        # Check answer for perfect match against all translations, update profile points and ge5 feedback
        for translation in translations:
            test_translation = translation.translation.translate(str.maketrans("", "", string.punctuation))
            score, errors = eval_answer(normalized_answer.lower(), test_translation.lower())
            if normalized_answer == test_translation:
                user_phrase_strength.correct += 1
                profile.xp += PLUS_9_XP
                profile.save()
                response_accuracy = True
                matched_translation = translation.translation
                request.session['correct_count'] += 1
            else:
                response_accuracy = False
            if score > best_score:
                best_score = score
                least_errors = errors

        if matched_translation is None:
            matched_translation = translations[0].translation
        
        feedback_html = feedback(raw_answer, matched_translation, least_errors, best_score)
      
        # Adjust and save the user's phrase views and score
        user_phrase_strength.views += 1
        user_phrase_strength.strength = (
            (user_phrase_strength.views - 
                (user_phrase_strength.views - user_phrase_strength.correct)
            ) * 100) / user_phrase_strength.views
        user_phrase_strength.save()

        # Store data in session for feedback view and increment test count
        test_count = request.session['test_count'] + 1
        request.session.update({
            'phrase_id': user_phrase_strength.phrase.id,
            'response_accuracy': response_accuracy,
            'feedback_html': feedback_html,
            'xp_reward': PLUS_9_XP,
            'test_count': test_count,
        })

        # Redirect to feedback if post succeeds
        return redirect(reverse_lazy('frendj:feedback'))


class FeedbackView(LoginRequiredMixin, View):
    """Displays feedback on user translation accuracy and points earned."""

    template_name = 'frendj/feedback.html'

    def get(self, request):
        testing_view = request.session.get('testing_view')
        profile = Profile.objects.get(user=request.user)
        phrase = Phrase.objects.get(id=request.session['phrase_id'])
        raw_answer = request.session.get('raw_answer')
        response_accuracy = request.session.get('response_accuracy')
        feedback_html = request.session.get('feedback_html')
        xp_reward = request.session.get('xp_reward')

        # Module progress for LearnView only; quiz progress for all the others
        if testing_view == "frendj:learn":
            stats = (
                Phrase.objects
                    .filter(module_id=phrase.module_id)
                    .aggregate(
                        module_phrase_count=Count('pk', distinct=True),
                        learned_count=Count(
                            'userphrasestrength__pk',
                            filter=Q(
                                userphrasestrength__user=request.user,
                                userphrasestrength__learned=True,
                            ),
                            distinct=True
                        ),
                )
            )
            total = stats['module_phrase_count']
            learned_count = stats['learned_count']
            unlearned_count = total - learned_count
            progress = round( (learned_count / total) * 100 ) if total > 0 else 0
        else:
            learned_count, unlearned_count = None, None
            progress = round( ( (request.session['test_count'] - 1) / QUIZ_LENGTH ) * 100 )

        # Choose one result phrase for feedback
        if response_accuracy:
            correct = ["Amazing", "Awesome", "Great", "Yes!", "You got it", "Wow",
                "You're good at this", "You're great!", "You're awesome"]
            result = choice(correct)
        else:
            wrong = ["Better luck next time", "Keep practicing", "Keep at it",
                "You'll get it next time", "It'll stick eventually"]
            result = choice(wrong)

        context = {
            'testing_view': testing_view,
            'profile': profile,
            'phrase': phrase,
            'module': phrase.module,
            'raw_answer': raw_answer, # Used as backup in case of error with HTML
            'response_accuracy': response_accuracy,
            'feedback_html': feedback_html,
            'xp_reward': xp_reward,
            'translations': phrase.phrase_translations.all(),
            'test_count': f"Card {request.session['test_count'] - 1} of {QUIZ_LENGTH}",
            'learned_count': learned_count,
            'unlearned_count': unlearned_count,
            'progress': progress,
            'result': result,
        }
        return render(request, self.template_name, context)