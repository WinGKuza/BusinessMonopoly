from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='home'),
    path('about', views.about, name='about'),
    path('registration', views.registration, name='registration'),
    path('create/', views.create_game, name='create_game'),
]
