from django.contrib import admin
from frendj.models import Module, Phrase, Profile, Translation, UserPhraseStrength


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    search_fields = ('module',)


@admin.register(Phrase)
class PhraseAdmin(admin.ModelAdmin):
    list_display = ('phrase', 'language', 'module')
    ordering = ('phrase', 'language', 'module')
    search_fields = ('phrase',)
    list_filter = ('language', 'module')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'xp')
    fields = ('user',)
    search_fields = ('name',)


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    list_display = ('translation', 'phrase', 'language')
    list_filter = ('language',)
    search_fields = ('translation',)


@admin.register(UserPhraseStrength) # Dev only. Disable before production
class UserPhraseStrengthAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'learned', 'phrase', 'strength')
    list_filter = ('user', 'learned', 'phrase')