from django.urls import path
from . import views

app_name = 'staff'
urlpatterns = [
    # Main page for content admins to navigate adding and editing content
    path('', views.StaffMenuView.as_view(), name='manage_content'),

    # Add new modules, phrases and translations
    path('add_module', views.CreateModuleView.as_view(), name='add_module'),
    path('module/<int:pk>/add_phrase',
         views.CreatePhraseView.as_view(), name='add_phrase'),
    path('module/<int:pk1>/phrase/<int:pk2>/add_translation',
         views.CreateTranslationView.as_view(), name='add_translation'),

    # Edit modules, phrases and translations
    path('edit_module/<int:pk>', views.UpdateModuleView.as_view(), name='edit_module'),
    path('edit_phrase/<int:pk>', views.UpdatePhraseView.as_view(), name='edit_phrase'),
    path('edit_translation/<int:pk>',
         views.UpdateTranslationView.as_view(),name='edit_translation'),

    # Mass add / update modules, phrases and translations from CSV to DB
    path('csv_db_test', views.CsvToDbTestView.as_view(), name='csv_db_test'),
    path('csv_db_update', views.CsvToDbUpdateView.as_view(), name='csv_db_update'),

]