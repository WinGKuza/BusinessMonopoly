import random
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from .forms import GameCreateForm, GameSettingsForm
from .models import Game, GamePlayer, PlayerProfile

def _update_pause_state(game):
    if game.game_players.exists():
        game.resume()
    else:
        game.pause()


def assign_initial_role_and_resources(game_player):
    if game_player.role == 0:
        if random.random() < game_player.game.entrepreneur_chance:
            game_player.role = 3  # Предприниматель
        else:
            game_player.role = 1  # Безработный
        game_player.money = 10000
        game_player.influence = 0
        game_player.save()


@login_required
@require_POST
def update_game_settings(request, game_id):
    game = get_object_or_404(Game, id=game_id, creator=request.user)
    form = GameSettingsForm(request.POST, instance=game)
    if form.is_valid():
        form.save()
        messages.success(request, "Настройки игры обновлены.")
    else:
        messages.error(request, "Ошибка при сохранении настроек.")
    return redirect('game_detail', game_id=game.id)


@require_POST
@login_required
def transfer_money(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    sender = get_object_or_404(GamePlayer, game=game, user=request.user)

    receiver_id = request.POST.get('receiver')
    amount = int(request.POST.get('amount', 0))

    if amount <= 0:
        messages.error(request, 'Сумма должна быть положительной.')
        return redirect('game_detail', game_id=game_id)

    try:
        receiver = GamePlayer.objects.get(id=receiver_id, game=game)
    except GamePlayer.DoesNotExist:
        messages.error(request, 'Получатель не найден в этой игре.')
        return redirect('game_detail', game_id=game_id)

    if sender.money < amount:
        messages.error(request, 'Недостаточно денег.')
        return redirect('game_detail', game_id=game_id)

    with transaction.atomic():
        GamePlayer.objects.filter(id=sender.id).update(money=F('money') - amount)
        GamePlayer.objects.filter(id=receiver.id).update(money=F('money') + amount)

    messages.success(request, f'Переведено {amount} ₽ игроку {receiver.user.username}.')
    return redirect('game_detail', game_id=game_id)



@login_required
def toggle_host_mode(request, game_id):
    game = get_object_or_404(Game, id=game_id, creator=request.user)
    profile = request.user.playerprofile
    profile.is_host = not profile.is_host
    profile.save()
    return redirect('game_detail', game_id=game.id)

@login_required
def reelect_state_official(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    if not game.election_due():
        messages.warning(request, 'Переизбрание возможно раз в 1.5 часа.')
        return redirect('game_detail', game_id=game.id)

    players = GamePlayer.objects.filter(game=game)
    if not players:
        messages.error(request, 'Нет игроков для голосования.')
        return redirect('game_detail', game_id=game.id)

    new_official = max(players, key=lambda p: p.influence)

    if game.state_official and game.state_official != new_official.user.playerprofile:
        old_profile = game.state_official
        old_gp = GamePlayer.objects.filter(game=game, user=old_profile.user).first()
        if old_gp and old_gp.role == 5:
            old_gp.role = 1
            old_gp.save()

    new_official.role = 5
    new_official.save()

    game.state_official = new_official.user.playerprofile
    game.last_election_time = timezone.now()
    game.save()

    messages.success(request, f'Новый государственный деятель: {new_official.user.username}')
    return redirect('game_detail', game_id=game.id)

@login_required
def appoint_banker(request, game_id, player_id):
    game = get_object_or_404(Game, id=game_id)
    if game.state_official != request.user.playerprofile:
        messages.error(request, 'Только государственный деятель может назначать банкира.')
        return redirect('game_detail', game_id=game.id)

    target_gp = get_object_or_404(GamePlayer, id=player_id, game=game)
    target_gp.role = 4
    target_gp.save()

    messages.success(request, f'{target_gp.user.username} назначен банкиром.')
    return redirect('game_detail', game_id=game.id)

@login_required
@require_POST
def save_game(request, game_id):
    game = get_object_or_404(Game, id=game_id, creator=request.user)
    game.is_active = True
    game.save()
    return JsonResponse({'status': 'saved'})

@login_required
@require_POST
def delete_game(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    if request.user == game.creator:
        game.delete()
        return redirect('create_game')
    return redirect('game_detail', game_id=game_id)

@login_required
def create_game(request):
    active_game = Game.objects.filter(creator=request.user, is_active=True).first()
    if active_game:
        return redirect('game_detail', game_id=active_game.id)

    if request.method == 'POST':
        form = GameCreateForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.creator = request.user
            game.is_active = True
            game.save()
            return redirect('join_game', game_id=game.id)
    else:
        form = GameCreateForm()
    return render(request, 'games/create_game.html', {'form': form})

@login_required
def join_game(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    game_player, created = GamePlayer.objects.get_or_create(game=game, user=request.user)
    if created:
        assign_initial_role_and_resources(game_player)
    _update_pause_state(game)
    return redirect('game_detail', game_id=game.id)

@login_required
@require_POST
def leave_game(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    GamePlayer.objects.filter(game=game, user=request.user).delete()
    _update_pause_state(game)
    return redirect('game_list')

@login_required
def game_list(request):
    games = Game.objects.filter(is_active=True)
    return render(request, 'games/game_list.html', {'games': games})


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    players = GamePlayer.objects.filter(game=game).select_related('user')
    player = GamePlayer.objects.filter(game=game, user=request.user).first()

    settings_form = GameSettingsForm(instance=game) if request.user == game.creator else None

    context = {
        'game': game,
        'players': players,
        'player': player,
        'elapsed_seconds': game.elapsed_seconds(),
        'election_due': game.election_due(),
        'is_paused': game.is_paused(),
        'settings_form': settings_form,
    }
    return render(request, 'games/game_detail.html', context)



@login_required
def home(request):
    error = None
    if request.method == 'POST':
        if 'create_game' in request.POST:
            form = GameCreateForm(request.POST)
            if form.is_valid():
                game = form.save()
                return redirect('game_detail', game_id=game.id)
        elif 'join_game' in request.POST:
            game_id = request.POST.get('game_id')
            try:
                game = Game.objects.get(id=game_id)
                return redirect('game_detail', game_id=game.id)
            except Game.DoesNotExist:
                error = "Игра с таким ID не найдена."
    else:
        form = GameCreateForm()

    return render(request, 'main/home.html', {'form': form, 'error': error})
