import uuid
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator

import logging
logger = logging.getLogger(__name__)

class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    start_time = models.DateTimeField(default=timezone.now)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_games', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)
    is_voting = models.BooleanField(default=False)

    # Настройки игры
    entrepreneur_chance = models.FloatField(default=0.3)
    election_interval = models.DurationField(default=timedelta(minutes=90))
    election_duration = models.DurationField(default=timedelta(seconds=30))
    last_election_time = models.DateTimeField(default=timezone.now)
    voting_started_at = models.DateTimeField(null=True, blank=True)
    voting_paused_at = models.DateTimeField(null=True, blank=True)
    voting_total_paused_seconds = models.IntegerField(default=0)
    state_balance = models.IntegerField(default=1000)
    bank_balance = models.IntegerField(default=10000)

    # Пауза
    paused_at = models.DateTimeField(null=True, blank=True)
    total_paused_seconds = models.IntegerField(default=0)

    def is_paused(self):
        return self.paused_at is not None

    def pause(self):
        if not self.is_paused():
            self.paused_at = timezone.now()
            # если в момент паузы идёт голосование — “заморозим” его
            if self.is_voting and not self.voting_paused_at:
                self.voting_paused_at = self.paused_at
            self.save(update_fields=['paused_at', 'voting_paused_at'])

    def resume(self):
        if self.is_paused():
            now = timezone.now()
            if self.is_voting and self.voting_paused_at:
                self.voting_total_paused_seconds += int((now - self.voting_paused_at).total_seconds())
                self.voting_paused_at = None
            delta = timezone.now() - self.paused_at
            self.total_paused_seconds += int(delta.total_seconds())
            self.paused_at = None
            self.save(update_fields=['paused_at', 'total_paused_seconds', 'voting_paused_at', 'voting_total_paused_seconds'])

    def start_election(self):
        if self.is_voting:
            return
        self.is_voting = True
        self.voting_started_at = timezone.now()
        self.voting_paused_at = None
        self.voting_total_paused_seconds = 0
        self.save(update_fields=["is_voting", "voting_started_at", "voting_paused_at", "voting_total_paused_seconds"])
        from .votes import VoteService
        VoteService.start_election_for_game(self, started_at=self.voting_started_at)
        logger.info("[ELECTION] START game=%s at=%s", self.id, self.voting_started_at)

    def end_election(self, force_result: str | None = None):
        if not self.is_voting:
            return

        from .votes import VoteService
        from .models import VoteSession, VoteBallot, GamePlayer
        from .realtime import broadcast_personal_to_game, send_game_update

        # Если прилетел форс-таймаут — не даём сервису «рисовать победителя»
        if force_result == "timeout":
            session = (VoteSession.objects
                       .filter(game=self, kind=VoteSession.KIND_ELECTION, is_active=True)
                       .first())
            if session:
                session.meta = {**(session.meta or {}), "last_result": "timeout"}
                session.close()

            # закрываем флаги игры
            self.is_voting = False
            self.last_election_time = timezone.now()
            self.voting_paused_at = None
            self.voting_total_paused_seconds = 0
            self.save(
                update_fields=["is_voting", "last_election_time", "voting_paused_at", "voting_total_paused_seconds"])

            broadcast_personal_to_game(
                self.id,
                "Время голосования истекло. Перезапускаем выборы…",
                level="warning",
                include_observers=True,
                extra_data={"reason": "timeout"},
            )
            self.start_election()
            send_game_update(self.id)
            return

        # Обычный путь — даём сервису подвести итоги
        winner_gp = None
        try:
            winner_gp = VoteService.finish_force(self)
        except Exception:
            logger.exception("[ELECTION] finish_force failed game=%s", self.id)

        last_session = (VoteSession.objects
                        .filter(game=self)
                        .order_by("-started_at")
                        .first())
        last_meta = (last_session.meta or {}) if last_session else {}
        last_result = last_meta.get("last_result")  # winner/tie/timeout/no_votes/None

        # Закрываем флаги игры
        self.is_voting = False
        self.last_election_time = timezone.now()
        self.voting_paused_at = None
        self.voting_total_paused_seconds = 0
        self.save(update_fields=["is_voting", "last_election_time", "voting_paused_at", "voting_total_paused_seconds"])

        # === КРИТИЧЕСКОЕ: проверка «все ли проголосовали» ДО назначения победителя ===
        expected = GamePlayer.objects.filter(game=self, is_active=True, is_observer=False).count()
        ballots = 0
        if last_session:
            ballots = (VoteBallot.objects
                       .filter(session=last_session)
                       .values("voter_id").distinct().count())

        if ballots < expected:
            broadcast_personal_to_game(
                self.id,
                "Недостаточно голосов. Перезапускаем выборы…",
                level="warning",
                include_observers=True,
                extra_data={"reason": "not_enough_votes", "expected": expected, "got": ballots},
            )
            self.start_election()
            send_game_update(self.id)
            return
        # === /КРИТИЧЕСКОЕ ===

        # 1) Таймаут (если вдруг сервис его оставил) -> перезапуск
        if last_result == "timeout":
            broadcast_personal_to_game(
                self.id,
                "Время голосования истекло. Перезапускаем выборы…",
                level="warning",
                include_observers=True,
                extra_data={"reason": "timeout"},
            )
            self.start_election()
            send_game_update(self.id)
            return

        # 2) Есть победитель -> назначаем и выходим
        if winner_gp is not None:
            GamePlayer.objects.filter(game=self, special_role=2) \
                .exclude(pk=winner_gp.pk).update(special_role=0)
            if winner_gp.special_role != 2:
                winner_gp.special_role = 2
                winner_gp.save(update_fields=["special_role"])

            broadcast_personal_to_game(
                self.id,
                f"«{winner_gp.user.username}» — новый Политик! 🎉",
                level="success",
                extra_data={"winner_player_id": winner_gp.id, "role": "Политик"},
                include_observers=True,
            )
            self.start_banker_selection(winner_gp)
            send_game_update(self.id)
            return

        # 3) Ничья -> перезапуск
        if last_result == "tie":
            broadcast_personal_to_game(
                self.id,
                "Ничья. Перезапускаем выборы…",
                level="warning",
                include_observers=True,
                extra_data={"reason": "tie"},
            )
            self.start_election()
            send_game_update(self.id)
            return

        # 4) Все проголосовали, но уникального лидера нет -> крутим дальше
        broadcast_personal_to_game(
            self.id,
            "Победитель не определён. Перезапускаем выборы…",
            level="warning",
            include_observers=True,
            extra_data={"reason": "no_winner_all_voted"},
        )
        self.start_election()
        send_game_update(self.id)

    @transaction.atomic
    def set_banker(self, banker_gp):
        """Назначить Банкира (special_role=1). С прежнего банкира снять спец-роль."""
        from .models import GamePlayer
        # снять у прежнего банкира
        GamePlayer.objects.filter(game=self, special_role=1).update(special_role=0)
        # назначить нового
        banker_gp.special_role = 1  # 1 = Банкир
        banker_gp.save(update_fields=["special_role"])

        # оповещения/обновление UI
        try:
            from .realtime import broadcast_personal_to_game, send_game_update
            broadcast_personal_to_game(
                self.id,
                f"Назначен Банкир: {banker_gp.user.username}",
                level="info",
                include_observers=True,
                extra_data={"event": "banker_assigned", "banker_id": banker_gp.id},
            )
            send_game_update(self.id)
        except Exception:
            pass

    def is_politician(self, user) -> bool:
        """Пользователь — текущий Политик этой игры? (special_role=2)"""
        from .models import GamePlayer
        if not user or not user.is_authenticated:
            return False
        return GamePlayer.objects.filter(game=self, user=user, special_role=2).exists()

    def start_banker_selection(self, politician_gp):
        """
        Попросить фронт ВЫБРАТЬ Банкира — только у текущего политика.
        Всем остальным отправим событие, чтобы скрыть любой старый UI выбора.
        """
        from .models import GamePlayer
        from .realtime import broadcast_personal_to_game, send_game_update
        from .realtime import send_personal_message  # если у вас в том же модуле

        candidates = list(
            GamePlayer.objects
            .filter(game=self, is_active=True, is_observer=False, special_role__in=[0, 1])
            .values("id", username=models.F("user__username"))
        )

        for pol in GamePlayer.objects.filter(game=self, special_role=2, is_active=True):
            send_personal_message(
                pol.user_id,
                "Политик должен выбрать Банкира.",
                level="info",
                extra_data={
                    "kind": "banker_selection_started",
                    "candidates": candidates,
                },
            )




    def election_elapsed_seconds(self) -> int:
        #Сколько секунд прошло с начала голосования, без учёта паузы игры.
        if not self.is_voting or not self.voting_started_at:
            return 0
        now = timezone.now()
        elapsed = int((now - self.voting_started_at).total_seconds())

        paused = self.voting_total_paused_seconds
        if self.paused_at and self.voting_paused_at:
            paused += int((now - self.voting_paused_at).total_seconds())

        return max(elapsed - paused, 0)

    def election_remaining_seconds(self) -> int:
        return max(int(self.election_duration.total_seconds()) - self.election_elapsed_seconds(), 0)

    def elapsed_seconds(self):
        base = self.paused_at if self.is_paused() else timezone.now()
        elapsed = int((base - self.start_time).total_seconds()) - self.total_paused_seconds
        return max(elapsed, 0)

    def __str__(self):
        return self.name


class GamePlayer(models.Model):
    ROLE_CHOICES = [
        (1, 'Безработный'),
        (2, 'Работник'),
        (3, 'Предприниматель'),
    ]
    SPECIAL_ROLE_CHOICES = [
        (0, ''),
        (1, 'Банкир'),
        (2, 'Политик'),
    ]
    role = models.IntegerField(choices=ROLE_CHOICES, default=1)
    special_role = models.IntegerField(choices=SPECIAL_ROLE_CHOICES, default=0)
    game = models.ForeignKey(Game, related_name='game_players', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='game_players', on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    money = models.IntegerField(default=300)
    influence = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_observer = models.BooleanField(default=False)

    class Meta:
        unique_together = ('game', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.game.name}"

    def get_role_display(self):
        return dict(self.ROLE_CHOICES).get(self.role, 'Неизвестно') if not self.special_role else dict(self.SPECIAL_ROLE_CHOICES).get(self.special_role, 'Неизвестно')


class VoteSession(models.Model):
    KIND_ELECTION = "election"
    KIND_EVENT = "event"
    KIND_CHOICES = [(KIND_ELECTION, "Election"), (KIND_EVENT, "Event")]

    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='vote_sessions')
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    question = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(db_index=True, default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['game', 'is_active']),
            models.Index(fields=['game', 'kind', 'started_at']),
        ]

    def tally(self):
        return (VoteBallot.objects.filter(session=self)
                .values('option_id')
                .annotate(count=models.Count('id'))
                .order_by('-count', 'option_id'))

    def voters_count(self):
        return (VoteBallot.objects.filter(session=self)
                .values('voter_id').distinct().count())

    def has_everyone_voted(self, expected_count: int) -> bool:
        return self.voters_count() >= expected_count

    def close(self):
        if not self.is_active:
            return
        self.is_active = False
        self.ends_at = timezone.now()
        self.save(update_fields=['is_active', 'ends_at'])


class VoteOption(models.Model):
    session = models.ForeignKey(VoteSession, on_delete=models.CASCADE, related_name='options')
    label = models.CharField(max_length=255, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')
    weight = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('session', 'content_type', 'object_id')
        indexes = [models.Index(fields=['session'])]


class VoteBallot(models.Model):
    session = models.ForeignKey(VoteSession, on_delete=models.CASCADE, related_name='ballots')
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ballots')
    option = models.ForeignKey(VoteOption, on_delete=models.CASCADE, related_name='ballots')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'voter')
        indexes = [
            models.Index(fields=['session', 'voter']),
            models.Index(fields=['session', 'option']),
        ]

    def clean(self):
        if self.option.session_id != self.session_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("Option must belong to the same session.")


class AskedQuestion(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='asked_questions')
    question_id = models.IntegerField()
    asked_by = models.ForeignKey('GamePlayer', on_delete=models.CASCADE, related_name='questions_asked')
    target = models.ForeignKey('GamePlayer', on_delete=models.CASCADE, related_name='questions_received')
    created_at = models.DateTimeField(auto_now_add=True)
    answered = models.BooleanField(default=False)
    answer_choice = models.IntegerField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['game', 'answered']),
            models.Index(fields=['target', 'answered']),
            models.Index(fields=['asked_by', 'created_at']),
        ]

    def __str__(self):
        return f"Q#{self.question_id} {self.asked_by_id}->{self.target_id} ({'done' if self.answered else 'open'})"


class PendingAnswer(models.Model):
    STATUS_CHOICES = [
        ("pending", "Ожидает решения"),
        ("approved", "Одобрен"),
        ("rejected", "Отклонён"),
    ]
    game = models.ForeignKey("games.Game", on_delete=models.CASCADE, related_name="pending_answers")
    player = models.ForeignKey("games.GamePlayer", on_delete=models.CASCADE, related_name="pending_answers")
    question_id = models.IntegerField()
    answer_text = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [
            models.Index(fields=["game", "status"]),
        ]

    def __str__(self):
        return f"Q{self.question_id} by {self.player.user.username} [{self.status}]"