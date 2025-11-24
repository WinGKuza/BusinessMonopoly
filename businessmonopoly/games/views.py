import random
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.urls import reverse
from functools import wraps
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .votes import VoteService
from .forms import GameCreateForm, GameSettingsForm
from .models import Game, GamePlayer, PendingAnswer, AskedQuestion
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
    game_player.money = 300
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

    if player.role == 1: #TODO Сделать выбор или то или то
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


@login_required
@require_POST
@pause_protected
def transfer_money(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    sender = get_object_or_404(GamePlayer, game=game, user=request.user, is_active=True)

    if sender.is_observer:
        return JsonResponse({"error": "Наблюдатель не может переводить деньги"}, status=400)

    receiver_raw = request.POST.get("receiver")
    amount_raw = request.POST.get("amount")
    source = request.POST.get("source")  # "personal"/"bank" для банкира, может быть None

    try:
        amount = int(amount_raw)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Некорректная сумма"}, status=400)

    if amount <= 0:
        return JsonResponse({"error": "Сумма должна быть положительной"}, status=400)

    if not receiver_raw:
        return JsonResponse({"error": "Не указан получатель"}, status=400)

    # --- разбираем получателя ---
    receiver_kind = None  # "player" | "bank" | "gov"
    target_player = None

    if receiver_raw == "bank":
        receiver_kind = "bank"
    elif receiver_raw == "gov":
        receiver_kind = "gov"
    elif receiver_raw.startswith("p"):
        receiver_kind = "player"
        try:
            target_id = int(receiver_raw[1:])
        except ValueError:
            return JsonResponse({"error": "Некорректный получатель"}, status=400)
        target_player = get_object_or_404(
            GamePlayer,
            id=target_id,
            game=game,
            is_active=True,
            is_observer=False,
        )
    else:
        return JsonResponse({"error": "Некорректный получатель"}, status=400)

    # Нельзя переводить себе самому (для player)
    if receiver_kind == "player" and target_player.id == sender.id:
        return JsonResponse({"error": "Нельзя перевести деньги самому себе"}, status=400)

    # дальше — внутренняя логика переводов
    from .money import transfer_money as core_transfer

    ok, msg = core_transfer(
        game=game,
        sender=sender,
        receiver=target_player,
        amount=amount,
        receiver_kind=receiver_kind,
        source=source,
    )

    if not ok:
        return JsonResponse({"error": msg}, status=400)

    # Обновим состояние игры для всех
    send_game_update(game.id)

    return JsonResponse({"status": "ok", "message": msg})



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
@require_POST
def choose_banker(request, game_id: int):
    game = get_object_or_404(Game, pk=game_id)

    # только текущий Политик
    if not game.is_politician(request.user):
        return HttpResponseForbidden("Только Политик может назначать Банкира")

    try:
        payload = json.loads(request.body or "{}")
        banker_gp_id = int(payload.get("banker_id"))
    except Exception:
        return JsonResponse({"error": "Некорректный payload"}, status=400)

    banker_gp = get_object_or_404(
        GamePlayer,
        pk=banker_gp_id, game=game,
        is_active=True, is_observer=False,
    )

    # нельзя назначить игрока со спец-ролью (уже Политик/Банкир)
    if banker_gp.special_role in (1, 2):
        return JsonResponse({"error": "Игрок уже имеет спец-роль"}, status=400)

    game.set_banker(banker_gp)
    return JsonResponse({"status": "ok", "banker_id": banker_gp.id})

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
        idx = payload.get("choice_index")  # может быть None
        ask_token = payload.get("ask_token")  # <== есть в твоём коде
        free_text = (payload.get("answer_text") or "").strip()  # НОВОЕ: для ручных/свободных
    except Exception:
        return JsonResponse({"error": "Неверные данные"}, status=400)

    # найдём карточку вопроса
    asked: AskedQuestion | None = None
    if ask_token:
        asked = AskedQuestion.objects.filter(game=game, token=ask_token).first()
    if not asked:
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

    # загружаем вопрос
    questions = load_questions("ru")
    q = next((item for item in questions if int(item.get("id")) == qid), None)
    if not q:
        return JsonResponse({"error": "Вопрос не найден."}, status=404)

    choices = q.get("choices") or q.get("options") or []
    reward = (q.get("reward") or {})
    reward_money = int(reward.get("money") or 0)
    reward_infl  = int(reward.get("influence") or 0)

    # --- ветка 1: ручной вопрос (correct is None) ---
    if q.get("correct", None) is None:
        # берём текст ответа: либо выбранный вариант (если варианты вдруг есть),
        # либо свободный текст
        if choices and idx is not None:
            try:
                idx = int(idx)
                if not (0 <= idx < len(choices)):
                    return JsonResponse({"error": "Некорректный вариант."}, status=400)
                answer_text = str(choices[idx])
            except Exception:
                return JsonResponse({"error": "Некорректный вариант."}, status=400)
        else:
            # свободный ответ обязателен
            if not free_text:
                return JsonResponse({"error": "Ответ пустой."}, status=400)
            answer_text = free_text

        # создаём ожидающий ручного решения ответ
        PendingAnswer.objects.create(
            game=game,
            player=gp,
            question_id=qid,
            answer_text=answer_text,
            status="pending",
        )

        # НЕ закрываем asked сразу — пусть висит до решения
        # (если хочешь — можешь пометить asked.answer_choice = None, но не answered=True)

        # игроку — квитанция
        send_personal_message(
            gp.user_id,
            "Ответ отправлен. Ожидайте решения Политика.",
            level="info",
            extra_data={
                "kind": "question_result",
                "question_id": qid,
                "your_choice": None,
                "correct": None,
            },
        )

        # политикам — напоминание о ревью
        for pol in GamePlayer.objects.filter(game=game, special_role=2, is_active=True):
            send_personal_message(
                pol.user_id,
                f"Новый ответ по вопросу №{qid} от {gp.user.username}.",
                level="info",
                extra_data={
                    "kind": "question_review",
                    "question_id": qid,
                    "player_username": gp.user.username,
                    "answer_text": answer_text,
                    "ask_token": str(asked.token),
                }
            )

        return JsonResponse({"status": "ok", "pending": True})

    # --- ветка 2: авто-вопрос (есть correct) ---
    if not choices:
        return JsonResponse({"error": "У вопроса нет вариантов."}, status=400)
    try:
        idx = int(idx)
        if not (0 <= idx < len(choices)):
            return JsonResponse({"error": "Некорректный вариант."}, status=400)
    except Exception:
        return JsonResponse({"error": "Некорректный вариант."}, status=400)

    # correct может быть индексом или значением; поддержим оба
    correct_raw = q.get("correct")
    if isinstance(correct_raw, int):
        is_correct = (idx == correct_raw)
        correct_for_report = correct_raw
    else:
        # строка/значение — сравниваем по тексту
        is_correct = (str(choices[idx]) == str(correct_raw))
        # для отчёта отдадим само значение
        correct_for_report = correct_raw

    # закрываем карточку (для авто-вопроса)
    asked.answered = True
    asked.answer_choice = idx
    asked.is_correct = is_correct
    asked.save(update_fields=["answered", "answer_choice", "is_correct"])

    # игроку — локальный фидбэк
    if is_correct:
        grant_reward(gp, money=reward_money, influence=reward_infl, reason=f"Правильный ответ #{qid}")
        send_game_update(game.id)
        send_personal_message(
            gp.user_id,
            "Верно! 🎉",
            level="success",
            extra_data={"kind": "question_result", "question_id": qid, "your_choice": idx, "correct": correct_for_report},
        )
    else:
        send_personal_message(
            gp.user_id,
            "Неверно.",
            level="warning",
            extra_data={"kind": "question_result", "question_id": qid, "your_choice": idx, "correct": correct_for_report},
        )

    # Отчёт Политику, который задавал этот конкретный вопрос
    polis_user_id = asked.asked_by.user_id
    send_personal_message(
        polis_user_id,
        f"{gp.user.username} ответил на ваш вопрос №{qid}: {'верно' if is_correct else 'неверно'}.",
        level="success" if is_correct else "warning",
        extra_data={
            "kind": "question_report",
            "player": gp.user.username,
            "question_id": qid,
            "choice": idx,
            "correct": correct_for_report,
            "ask_token": str(asked.token),
        },
    )

    return JsonResponse({"status": "ok", "correct": bool(is_correct)})


def grant_reward(target_gp: GamePlayer, money: int = 0, influence: int = 0, reason: str = ""):
    if not money and not influence:
        return
    with transaction.atomic():
        gp = GamePlayer.objects.select_for_update().get(pk=target_gp.pk)
        gp.money += int(money)
        gp.influence += int(influence)
        gp.save(update_fields=["money", "influence"])
    send_game_update(gp.game_id)
    msg = f"Награда: +{money} 💰, +{influence} ⭐"
    if reason:
        msg = f"{reason}. {msg}"
    send_personal_message(gp.user_id, msg, "success")


@login_required
@require_POST
@pause_protected
def grade_pending_answer(request, game_id):
    from django.utils import timezone
    from .models import Game, GamePlayer, AskedQuestion, PendingAnswer

    game = get_object_or_404(Game, id=game_id)
    reviewer_gp = get_object_or_404(GamePlayer, game=game, user=request.user)

    # Разрешим только Политику
    if reviewer_gp.special_role != 2:
        return JsonResponse({"error": "Только Политик может принимать решения."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Неверный JSON"}, status=400)

    approved   = payload.get("approved")
    ask_token  = payload.get("ask_token")
    qid_raw    = payload.get("question_id")
    pid_raw    = payload.get("player_id")  # опционально

    # нормализуем approved -> bool
    if isinstance(approved, str):
        approved = approved.lower() in ("1", "true", "yes", "y")
    approved = bool(approved)

    # question_id (опц.)
    qid = None
    if qid_raw is not None:
        try:
            qid = int(qid_raw)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Некорректный question_id"}, status=400)

    # 1) Основной путь — ищем по ask_token
    asked = None
    if ask_token:
        asked = AskedQuestion.objects.filter(game=game, token=ask_token).first()
        if not asked:
            return JsonResponse({"error": "Карточка вопроса не найдена по токену."}, status=404)
        # извлекаем адресата
        target_gp = asked.target
        if qid is None:
            qid = asked.question_id
    else:
        # 2) Фолбэк — по player_id + question_id (если прислали)
        if pid_raw is None or qid is None:
            return JsonResponse({"error": "Нужен ask_token или (player_id и question_id)."}, status=400)
        try:
            player_id = int(pid_raw)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Некорректный player_id"}, status=400)

        target_gp = get_object_or_404(GamePlayer, id=player_id, game=game, is_active=True)
        asked = (AskedQuestion.objects
                 .filter(game=game, target=target_gp, question_id=qid)
                 .order_by('-created_at').first())
        if not asked:
            return JsonResponse({"error": "Карточка вопроса не найдена."}, status=404)

    # Находим «ожидающий» ответ, если это ручной вопрос (correct == null)
    pending = (PendingAnswer.objects
               .filter(game=game, player=target_gp, question_id=qid, status="pending")
               .order_by('-created_at')
               .first())
    if not pending:
        # Может быть уже обработан, или вопрос авто-проверяемый
        return JsonResponse({"error": "Нет ожидающего решения ответа."}, status=404)

    # Применяем решение
    pending.status = "approved" if approved else "rejected"
    pending.decided_at = timezone.now()
    pending.decided_by = request.user
    pending.save(update_fields=["status", "decided_at", "decided_by"])

    # Выдаём награду только при approved
    if approved:
        # Возьмём награду из questions.json (если есть), иначе дефолт
        from .questions import load_questions
        qs = load_questions("ru")
        spec = next((x for x in qs if int(x.get("id", -1)) == qid), None) or {}
        reward = spec.get("reward") or {}
        money = int(reward.get("money") or 0)
        infl  = int(reward.get("influence") or 0)

        if money or infl:
            # фиксируем баланс под транзакцию на всякий случай
            with transaction.atomic():
                tgt_locked = GamePlayer.objects.select_for_update().get(pk=target_gp.pk)
                tgt_locked.money += money
                tgt_locked.influence += infl
                tgt_locked.save(update_fields=["money", "influence"])
            # пушим игроку уведомление
            parts = []
            if money: parts.append(f"+{money} ₽")
            if infl:  parts.append(f"+{infl} ⭐")
            send_personal_message(
                target_gp.user_id,
                f"Ваш ответ принят. Награда: {' и '.join(parts)}",
                level="success",
            )
        else:
            # награда не задана — просто уведомим
            send_personal_message(
                target_gp.user_id,
                "Ваш ответ принят.",
                level="success",
            )
    else:
        send_personal_message(
            target_gp.user_id,
            "Ваш ответ отклонён.",
            level="warning",
        )

    # Автору вопроса (Политику) — подтверждение
    send_personal_message(
        asked.asked_by.user_id,
        f"Решение по ответу игрока {target_gp.user.username} на вопрос №{qid}: "
        + ("одобрено" if approved else "отклонено"),
        level=("success" if approved else "warning"),
        extra_data={
            "kind": "question_review_result",
            "question_id": qid,
            "player": target_gp.user.username,
            "approved": approved,
            "ask_token": str(asked.token),
        },
    )

    # Обновим общий стейт на клиенте (балансы и т.п.)
    send_game_update(game.id)

    return JsonResponse({"status": "ok", "approved": approved})



@login_required
@require_POST
def start_election_early(request, game_id: int):
    game = get_object_or_404(Game, pk=game_id)

    # ТОЛЬКО создатель игры или суперюзер
    if not (request.user.is_superuser or game.creator_id == request.user.id):
        return HttpResponseForbidden("Недостаточно прав")

    # Если уже идёт голосование — просто отвечаем «уже идёт»
    if getattr(game, "is_voting", False):
        return JsonResponse({"status": "already_running"}, status=200)

    # Старт выборов немедленно
    game.start_election()

    # (опционально) уведомления по WS
    try:
        from .realtime import broadcast_personal_to_game, send_game_update
        broadcast_personal_to_game(
            game.id,
            "Создатель игры запустил досрочные выборы.",
            level="info",
            include_observers=True,
            extra_data={"reason": "manual_start", "at": timezone.now().isoformat()},
        )
        send_game_update(game.id)
    except Exception:
        pass

    return JsonResponse({"status": "ok"})


