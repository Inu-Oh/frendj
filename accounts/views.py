from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import UserCreateForm
from frendj.models import Phrase, UserPhraseStrength


class RegisterView(CreateView):
    template_name = 'registration/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            success_url = reverse_lazy('frendj:home')
            return redirect(success_url)
        form = UserCreateForm()
        context = {'form': form}
        return render(request, self.template_name, context)
    
    def post(self, request):
        form = UserCreateForm(request.POST)
        if not form.is_valid():
            context = {'form': form}
            return render(request, self.template_name, context)
        
        with transaction.atomic():
            user = form.save()

            # For all phrases, set user strength to 0 and learned to false
            for phrase in Phrase.objects.all():
                UserPhraseStrength.objects.create(
                    phrase=phrase,
                    user=user,
                    learned=False,
                    strength=0,
                    views=0,
                    correct=0,
                )
        return redirect(reverse_lazy('frendj:home'))