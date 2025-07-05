from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_game, name='create_game'),
    path('list/', views.game_list, name='game_list'),

    path('<uuid:game_id>/', views.game_detail, name='game_detail'),
    path('<uuid:game_id>/join/', views.join_game, name='join_game'),
    path('<uuid:game_id>/save/', views.save_game, name='save_game'),
    path('<uuid:game_id>/delete/', views.delete_game, name='delete_game'),
    path('<uuid:game_id>/toggle_host/', views.toggle_host_mode, name='toggle_host'),
    path('<uuid:game_id>/reelect/', views.reelect_state_official, name='reelect_state'),
    path('<uuid:game_id>/appoint_banker/<int:player_id>/', views.appoint_banker, name='appoint_banker'),
    path('<uuid:game_id>/join/', views.join_game, name='join_game'),
    path('<uuid:game_id>/leave/', views.leave_game, name='leave_game'),
    path('<uuid:game_id>/transfer/', views.transfer_money, name='transfer_money'),
]

