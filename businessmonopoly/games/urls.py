from django.urls import path
from . import views

urlpatterns = [
    path('<uuid:game_id>/', views.game_detail, name='game_detail'),
    path('<uuid:game_id>/join/', views.join_game, name='join_game'),
    path('<uuid:game_id>/save/', views.save_game, name='save_game'),
    path('<uuid:game_id>/delete/', views.delete_game, name='delete_game'),
    path('list/', views.game_list, name='game_list'),
    path('create/', views.create_game, name='create_game'),
]
