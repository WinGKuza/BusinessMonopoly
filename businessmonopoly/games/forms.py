from django import forms
from .models import Game
from datetime import timedelta


class GameCreateForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = ['name']
        labels = {
            'name': 'Название игры',
        }


class GameSettingsForm(forms.ModelForm):
    entrepreneur_chance = forms.FloatField(
        label='Шанс стать предпринимателем (0.0 - 1.0)',
        min_value=0.0,
        max_value=1.0,
        step_size=0.01,
    )

    election_interval = forms.DurationField(
        label='Интервал переизбрания Политика',
        help_text='Формат: чч:мм:сс',
    )

    election_duration = forms.DurationField(
        label='Длительность выборов',
        help_text='Формат: чч:мм:сс',
    )

    class Meta:
        model = Game
        fields = ['entrepreneur_chance', 'election_interval', 'election_duration']
