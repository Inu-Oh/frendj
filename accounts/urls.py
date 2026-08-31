from django.contrib.auth.views import LoginView
from django.urls import path
from .views import RegisterView

app_name = 'accounts'
urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', 
        LoginView.as_view(redirect_authenticated_user=True), name='login'),
]