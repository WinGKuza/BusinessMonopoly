from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_game, name='create_game'),
    path('list/', views.game_list, name='game_list'),

    path('<uuid:game_id>/', views.game_detail, name='game_detail'),
    path('<uuid:game_id>/join/', views.join_game, name='join_game'),
    path('<uuid:game_id>/save/', views.save_game, name='save_game'),
    path('<uuid:game_id>/delete/', views.delete_game, name='delete_game'),
    path('<uuid:game_id>/toggle_mode/', views.toggle_mode, name='toggle_mode'),
    path("<uuid:game_id>/vote/", views.vote_for_official, name="vote_for_official"),
    path('<uuid:game_id>/update_settings/', views.update_game_settings, name='update_game_settings'),
    path('<uuid:game_id>/appoint_banker/<int:player_id>/', views.appoint_banker, name='appoint_banker'),
    path('<uuid:game_id>/join/', views.join_game, name='join_game'),
    path('<uuid:game_id>/leave/', views.leave_game, name='leave_game'),
    path('<uuid:game_id>/transfer/', views.transfer_money, name='transfer_money'),
    path('<uuid:game_id>/toggle_pause/', views.toggle_pause, name='toggle_pause'),
    path('<uuid:game_id>/upgrade_role/', views.upgrade_role, name='upgrade_role'),
]

