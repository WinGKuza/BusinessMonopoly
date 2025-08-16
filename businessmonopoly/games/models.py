import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

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
        logger.info("[ELECTION] START game=%s at=%s", self.id, self.voting_started_at)

    def end_election(self):
        if not self.is_voting:
            return
        self.is_voting = False
        self.last_election_time = timezone.now()
        self.voting_paused_at = None
        self.voting_total_paused_seconds = 0
        self.save(update_fields=["is_voting", "last_election_time", "voting_paused_at", "voting_total_paused_seconds"])
        logger.info("[ELECTION] END   game=%s at=%s", self.id, self.last_election_time)

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
    special_role = models.IntegerField(choices=ROLE_CHOICES, default=0)
    game = models.ForeignKey(Game, related_name='game_players', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='game_players', on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    money = models.IntegerField(default=10000)
    influence = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_observer = models.BooleanField(default=False)

    class Meta:
        unique_together = ('game', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.game.name}"

    def get_role_display(self):
        return dict(self.ROLE_CHOICES).get(self.role, 'Неизвестно') if not self.special_role else dict(self.SPECIAL_ROLE_CHOICES).get(self.special_role, 'Неизвестно')
