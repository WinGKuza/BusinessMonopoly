import random
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.urls import reverse
from functools import wraps
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .votes import VoteService
from .forms import GameCreateForm, GameSettingsForm
from .models import Game, GamePlayer
from .realtime import send_game_update, send_personal_message, broadcast_personal_to_game
from .questions import load_questions


@require_POST
@login_required
def save_game(request, game_id):
    game = get_object_or_404(Game, id=game_id, creator=request.user)
    game.is_active = True
    game.save()

    send_game_update(game.id)
    return JsonResponse({'status': 'ok'})


def _update_pause_state(game):
    if not game.is_paused():
        if game.game_players.filter(is_active=True, is_observer=False).exists():
            game.resume()
        else:
            game.pause()


def assign_initial_role_and_resources(game_player):
    if random.random() < game_player.game.entrepreneur_chance:
        game_player.role = 3  # Предприниматель
    else:
        game_player.role = 1  # Безработный
    game_player.money = 10000
    game_player.influence = 0
    game_player.save()


def pause_protected(view_func):
    @wraps(view_func)
    def _wrapped_view(request, game_id, *args, **kwargs):
        game = get_object_or_404(Game, id=game_id)
        if game.is_paused():
            send_personal_message(
                request.user.id,
                "Игра на паузе. Действия временно недоступны.",
                "warning"
            )

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return HttpResponse(status=204)
            return redirect('game_detail', game_id=game.id)
        return view_func(request, game_id, *args, **kwargs)
    return _wrapped_view


@login_required
@require_POST
def toggle_pause(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    if request.user != game.creator:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    if game.is_paused():
        game.resume()
    else:
        game.pause()

    send_game_update(game.id)
    return JsonResponse({'status': 'ok'})


@require_POST
@login_required
@pause_protected
def upgrade_role(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    player = get_object_or_404(GamePlayer, game=game, user=request.user)

    if player.special_role != 0:
        return JsonResponse({'error': 'Вы не можете улучшать специальную роль'}, status=400)

    if player.role == 1:
        if player.money >= 500:
            player.money -= 500
        elif player.influence >= 3:
            player.influence -= 3
        else:
            send_personal_message(
                request.user.id,
                "Недостаточно средств для улучшения.",
                "error"
            )
            return HttpResponse(status=204)
        player.role = 2
    elif player.role == 2:
        if player.money >= 1000:
            player.money -= 1000
        elif player.influence >= 6:
            player.influence -= 6
        else:
            send_personal_message(
                request.user.id,
                "Недостаточно средств для улучшения.",
                "error"
            )
            return HttpResponse(status=204)
        player.role = 3
    else:
        send_personal_message(
            request.user.id,
            "Нельзя улучшить эту роль.",
            "error"
        )
        return HttpResponse(status=204)

    player.save()
    send_game_update(game.id)
    send_personal_message(
        player.user.id,
        "Роль успешно улучшена!",
        "success",
        extra_data={
            "role_id": player.role,
            "role": player.get_role_display(),
            "special_role": player.special_role,
        }
    )
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def update_game_settings(request, game_id):
    game = get_object_or_404(Game, id=game_id, creator=request.user)
    form = GameSettingsForm(request.POST, instance=game)

    if form.is_valid():
        form.save()
        send_game_update(game.id)
        send_personal_message(
            request.user.id,
            "Настройки игры обновлены.",
            "success"
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'status': 'ok'})
    else:
        send_personal_message(
            request.user.id,
            "Ошибка при сохранении настроек.",
            "error"
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Ошибка при сохранении настроек'}, status=400)

    return redirect('game_detail', game_id=game.id)


@require_POST
@login_required
@pause_protected
def transfer_money(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    sender = get_object_or_404(GamePlayer, game=game, user=request.user)
    if sender.is_observer:
        return JsonResponse({'status': 'error', 'error': 'Наблюдатель не может переводить деньги'})

    try:
        receiver_id = int(request.POST.get("receiver_id"))
        amount = int(request.POST.get("amount"))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Неверные данные"}, status=400)

    if amount <= 0:
        return JsonResponse({"error": "Сумма должна быть положительной"}, status=400)

    if sender.id == receiver_id:
        return JsonResponse({"error": "Нельзя перевести деньги самому себе"}, status=400)

    try:
        receiver = GamePlayer.objects.get(id=receiver_id, game=game)
    except GamePlayer.DoesNotExist:
        return JsonResponse({"error": "Получатель не найден"}, status=400)

    if receiver.is_observer:
        return JsonResponse({"status": "error", "error": "Нельзя переводить наблюдателю"})

    if sender.money < amount:
        return JsonResponse({"error": "Недостаточно средств"}, status=400)

    with transaction.atomic():
        sender = GamePlayer.objects.select_for_update().get(id=sender.id)
        receiver = GamePlayer.objects.select_for_update().get(id=receiver.id)

        sender.money -= amount
        receiver.money += amount
        sender.save()
        receiver.save()

    send_game_update(game.id)

    send_personal_message(
        sender.user.id,
        f"Вы перевели {amount} ₽ игроку {receiver.user.username}.",
        "success"
    )

    send_personal_message(
        receiver.user.id,
        f"Вы получили {amount} ₽ от игрока {sender.user.username}.",
        "success"
    )
    return JsonResponse({'status': 'ok'})



@login_required
def toggle_mode(request, game_id):
    game = get_object_or_404(Game, id=game_id, creator=request.user)
    player = get_object_or_404(GamePlayer, game=game, user=request.user)
    player.is_observer = not player.is_observer
    player.is_active = True
    player.save()
    send_game_update(game.id)
    #_update_pause_state(game)
    return JsonResponse({"status": "ok", "is_observer": player.is_observer})


@login_required
@require_POST
@pause_protected
def vote_for_official(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    player = get_object_or_404(GamePlayer, game=game, user=request.user)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        candidate_id = int(payload.get("candidate_id"))
    except Exception:
        return JsonResponse({"error": "Неверные данные"}, status=400)

    try:
        VoteService.cast_vote(game, request.user, candidate_id)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception:
        return JsonResponse({"error": "Не удалось сохранить голос"}, status=500)

    send_game_update(game.id)
    return JsonResponse({"status": "ok"})

@login_required
@pause_protected
def appoint_banker(request, game_id, player_id):
    game = get_object_or_404(Game, id=game_id)
    if game.state_official != request.user.playerprofile:
        messages.error(request, 'Только гос. деятель может назначать банкира.')
        return JsonResponse({'status': 'ok'})

    target_gp = get_object_or_404(GamePlayer, id=player_id, game=game)
    target_gp.role = 4
    target_gp.save()

    send_game_update(game.id)
    messages.success(request, f'{target_gp.user.username} назначен банкиром.')
    return JsonResponse({'status': 'ok'})

@login_required
def delete_game(request, game_id):
    game = get_object_or_404(Game, id=game_id)

    if request.user != game.creator:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Недостаточно прав'}, status=403)
        return redirect('game_detail', game_id=game_id)

    channel_layer = get_channel_layer()
    game_name = game.name
    redirect_url = request.build_absolute_uri(reverse('game_list'))

    broadcast_personal_to_game(
        game_id,
        f"Игра «{game_name}» была удалена",
        level="warning",
        include_observers=True,
        active_only=False,  # важно: шлём и тем, кто уже вышел
    )

    async_to_sync(channel_layer.group_send)(
        f"game_{game_id}",
        {"type": "game_deleted", "name": game_name, "redirect": redirect_url}
    )

    game.delete()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({'status': 'deleted'})
    return redirect('create_game')




@login_required
def create_game(request):
    active_game = Game.objects.filter(creator=request.user, is_active=True).first()
    if active_game:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'redirect': f'/games/{active_game.id}/join/'})

        messages.warning(request, 'У вас уже есть созданная игра. Вы перенаправлены к ней.')
        return redirect('join_game', game_id=active_game.id)

    if request.method == 'POST':
        form = GameCreateForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.creator = request.user
            game.is_active = True
            game.save()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({'redirect': f'/games/{game.id}/join/'})
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
    else:
        game_player.is_active = True
        game_player.save()

    #_update_pause_state(game)
    send_game_update(game.id)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({'status': 'joined'})
    return redirect('game_detail', game_id=game.id)





@require_POST
@login_required
def leave_game(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    try:
        player = GamePlayer.objects.get(game=game, user=request.user)
        player.is_active = False
        player.save()
    except GamePlayer.DoesNotExist:
        pass

    #_update_pause_state(game)
    send_game_update(game.id)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({'status': 'left'})
    return redirect('game_list')


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    players = GamePlayer.objects.filter(game=game, is_active=True).select_related('user')
    player = GamePlayer.objects.filter(game=game, user=request.user).first()

    settings_form = GameSettingsForm(instance=game) if request.user == game.creator else None

    return render(request, 'games/game_detail.html', {
        'game': game,
        'players': players,
        'player': player,
        'elapsed_seconds': game.elapsed_seconds(),
        'is_paused': game.is_paused(),
        'settings_form': settings_form,
    })


@login_required
def game_list(request):
    games = Game.objects.filter(is_active=True).values('id', 'name', 'creator__username', 'created_at')

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({'games': list(games)})

    return render(request, 'games/game_list.html', {'games': games})


@login_required
def home(request):
    error = None

    if request.method == 'POST':
        if 'create_game' in request.POST:
            form = GameCreateForm(request.POST)
            if form.is_valid():
                game = form.save()
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({'redirect': f'/games/{game.id}/'})
                return redirect('game_detail', game_id=game.id)

        elif 'join_game' in request.POST:
            game_id = request.POST.get('game_id')
            try:
                game = Game.objects.get(id=game_id)
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({'redirect': f'/games/{game.id}/'})
                return redirect('game_detail', game_id=game.id)
            except Game.DoesNotExist:
                error = "Игра с таким ID не найдена."

    else:
        form = GameCreateForm()

    return render(request, 'main/home.html', {'form': form, 'error': error})


@login_required
@require_POST
@pause_protected
def ask_question(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    asker_gp = get_object_or_404(GamePlayer, game=game, user=request.user)

    if asker_gp.special_role != 2:
        return JsonResponse({"error": "Только Политик может задавать вопросы."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        target_id = int(payload.get("target_player_id"))
        # новый параметр (опционально)
        qid = payload.get("question_id")
        if qid is not None:
            qid = int(qid)
    except Exception:
        return JsonResponse({"error": "Неверные данные"}, status=400)

    target_gp = get_object_or_404(
        GamePlayer, id=target_id, game=game, is_active=True, is_observer=False
    )
    if target_gp.user_id == request.user.id:
        return JsonResponse({"error": "Нельзя задавать вопрос самому себе."}, status=400)

    questions = load_questions("ru")
    if not questions:
        return JsonResponse({"error": "Нет доступных вопросов."}, status=500)

    # выбрать вопрос: заданный номер или случайный
    q = None
    if qid is not None:
        q = next((x for x in questions if int(x.get("id")) == qid), None)
        if not q:
            return JsonResponse({"error": f"Вопрос #{qid} не найден."}, status=404)
    else:
        import random
        q = random.choice(questions)
        qid = int(q.get("id"))

    # создаём запись-линк
    from .models import AskedQuestion
    asked = AskedQuestion.objects.create(
        game=game, question_id=qid, asked_by=asker_gp, target=target_gp
    )

    # отправляем персональный WS получателю
    extra = {
        "kind": "question",
        "question_id": qid,
        "text": q.get("text"),
        "choices": q.get("choices") or q.get("options") or [],
        "from_politician": asker_gp.user.username,
        "ask_token": str(asked.token),
        "game_id": str(game.id),
    }
    send_personal_message(
        target_gp.user_id,
        f"Вопрос от Политика {asker_gp.user.username}:",
        level="info",
        extra_data=extra,
    )

    return JsonResponse({"status": "ok"})



@login_required
@require_POST
@pause_protected
def answer_question(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    gp = get_object_or_404(GamePlayer, game=game, user=request.user, is_active=True)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        qid = int(payload.get("question_id"))
        idx = int(payload.get("choice_index"))
        ask_token = payload.get("ask_token")  # <== новый параметр
    except Exception:
        return JsonResponse({"error": "Неверные данные"}, status=400)

    # найдём карточку вопроса
    from .models import AskedQuestion
    asked: AskedQuestion | None = None
    if ask_token:
        asked = AskedQuestion.objects.filter(game=game, token=ask_token).first()
    if not asked:
        # fallback: последняя «открытая» карточка для этого игрока и вопроса
        asked = (AskedQuestion.objects
                 .filter(game=game, target=gp, question_id=qid, answered=False)
                 .order_by('-created_at')
                 .first())

    if not asked:
        return JsonResponse({"error": "Вопрос не найден или уже закрыт."}, status=404)
    if asked.target_id != gp.id:
        return JsonResponse({"error": "Вы не адресат этого вопроса."}, status=403)
    if asked.answered:
        return JsonResponse({"error": "Ответ уже принят."}, status=400)

    # проверка варианта
    questions = load_questions("ru")
    q = next((item for item in questions if int(item.get("id")) == qid), None)
    if not q:
        return JsonResponse({"error": "Вопрос не найден."}, status=404)

    choices = q.get("choices") or q.get("options") or []
    if not (0 <= idx < len(choices)):
        return JsonResponse({"error": "Некорректный вариант."}, status=400)

    has_correct = "correct" in q
    is_correct = None
    if has_correct:
        try:
            is_correct = (idx == int(q["correct"]))
        except Exception:
            is_correct = None

    # закрываем карточку
    asked.answered = True
    asked.answer_choice = idx
    asked.is_correct = is_correct
    asked.save(update_fields=["answered", "answer_choice", "is_correct"])

    # Игроку — локальный фидбэк (через WS персоналку)
    msg = "Ответ принят."
    level = "info"
    if is_correct is True:
        msg = "Верно! 🎉"; level = "success"
    elif is_correct is False:
        msg = "Неверно.";  level = "warning"

    send_personal_message(
        gp.user_id,
        msg,
        level=level,
        extra_data={
            "kind": "question_result",
            "question_id": qid,
            "your_choice": idx,
            "correct": q.get("correct", None),
        },
    )

    # Отправителю (Политику) — отчёт по его вопросу
    # даже если роль уже сменилась, отчёт уйдёт именно тому, кто отправил
    polis_user_id = asked.asked_by.user_id
    report_level = "success" if is_correct else "warning" if is_correct is False else "info"
    report_msg = f"{gp.user.username} ответил на ваш вопрос №{qid}: "
    if is_correct is True:
        report_msg += "верно."
    elif is_correct is False:
        report_msg += "неверно."
    else:
        report_msg += f"выбрана опция {idx}."

    send_personal_message(
        polis_user_id,
        report_msg,
        level=report_level,
        extra_data={
            "kind": "question_report",
            "player": gp.user.username,
            "question_id": qid,
            "choice": idx,
            "correct": q.get("correct", None),
            "ask_token": str(asked.token),
        },
    )

    return JsonResponse({"status": "ok", "correct": is_correct})