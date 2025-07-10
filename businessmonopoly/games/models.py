import uuid
import datetime
from django.db import models
from django.conf import settings
from django.utils import timezone


class PlayerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_host = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username}"


class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    start_time = models.DateTimeField(default=timezone.now)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_games', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)

    state_official = models.ForeignKey(
        PlayerProfile,
        null=True,
        blank=True,
        related_name='state_games',
        on_delete=models.SET_NULL,
    )
    last_election_time = models.DateTimeField(default=timezone.now)
    STATE_ELECTION_INTERVAL = datetime.timedelta(hours=1, minutes=30)

    paused_at = models.DateTimeField(null=True, blank=True)
    total_paused_seconds = models.IntegerField(default=0)

    def is_paused(self):
        return self.paused_at is not None

    def pause(self):
        if not self.is_paused():
            self.paused_at = timezone.now()
            self.save(update_fields=['paused_at'])

    def resume(self):
        if self.is_paused():
            delta = timezone.now() - self.paused_at
            self.total_paused_seconds += int(delta.total_seconds())
            self.paused_at = None
            self.save(update_fields=['paused_at', 'total_paused_seconds'])

    def elapsed_seconds(self):
        base = self.paused_at if self.is_paused() else timezone.now()
        elapsed = int((base - self.start_time).total_seconds()) - self.total_paused_seconds
        return max(elapsed, 0)

    def election_due(self):
        return timezone.now() - self.last_election_time >= self.STATE_ELECTION_INTERVAL

    def __str__(self):
        return self.name


class GamePlayer(models.Model):
    ROLE_CHOICES = [
        (0, 'Наблюдатель'),
        (1, 'Безработный'),
        (2, 'Работник'),
        (3, 'Предприниматель'),
        (4, 'Банкир'),
        (5, 'Государственный деятель'),
    ]
    role = models.IntegerField(choices=ROLE_CHOICES, default=0)
    entrepreneur_chance = models.FloatField(default=0.3)
    game = models.ForeignKey(Game, related_name='game_players', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='game_players', on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    money = models.IntegerField(default=10000)
    influence = models.IntegerField(default=0)

    class Meta:
        unique_together = ('game', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.game.name}"
