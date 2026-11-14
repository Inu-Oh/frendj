from django.contrib import admin
from accounts.models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'xp')
    fields = ('user',)
    search_fields = ('name',)