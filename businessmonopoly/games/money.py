from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from django.db import transaction
from models import Game, GamePlayer

AccountType = Literal["personal", "state", "bank"]


@dataclass
class AccountRef:
    game: Game
    player: GamePlayer | None
    kind: AccountType  # "personal"/"state"/"bank"

    @property
    def balance(self) -> int:
        if self.kind == "personal":
            return self.player.money
        if self.kind == "state":
            return self.game.state_balance
        if self.kind == "bank":
            return self.game.bank_balance
        raise ValueError("Unknown account kind")

    def set_balance(self, value: int):
        if self.kind == "personal":
            self.player.money = value
            self.player.save(update_fields=["money"])
        elif self.kind == "state":
            self.game.state_balance = value
            self.game.save(update_fields=["state_balance"])
        elif self.kind == "bank":
            self.game.bank_balance = value
            self.game.save(update_fields=["bank_balance"])
        else:
            raise ValueError("Unknown account kind")


def resolve_actor_account(game: Game, actor: GamePlayer, source: AccountType | None = None) -> AccountRef:
    """
    Определяем, с какого счёта списывать деньги у актёра.
    source:
      - None  -> "авто" по роли
      - "personal" / "state" / "bank" -> жёсткий выбор (для банкира)
    """
    # Политик всегда работает с гос. счётом
    if actor.special_role == 2:
        return AccountRef(game=game, player=None, kind="state")

    # Банкир: если явно просят "bank" — даём банк, иначе личный
    if actor.special_role == 1:
        if source == "bank":
            return AccountRef(game=game, player=None, kind="bank")
        return AccountRef(game=game, player=actor, kind="personal")

    # Обычный игрок
    return AccountRef(game=game, player=actor, kind="personal")


@transaction.atomic
def transfer_money(
    game: Game,
    actor: GamePlayer,
    target: GamePlayer,
    amount: int,
    source: AccountType | None = None,
) -> tuple[bool, str]:
    """
    Универсальный перевод внутри игры.
    actor -> target, amount > 0.
    source:
      None     => авто: Политик -> гос. счёт, Банкир -> личный, остальные -> личный
      "bank"   => Банкир с банковского счёта
      "state"  => жёсткая работа с гос. счётом (на будущее)
      "personal" => личный
    """
    if amount <= 0:
        return False, "Сумма должна быть положительной."

    # нельзя переводить самому себе
    if actor.id == target.id:
        return False, "Нельзя переводить самому себе."

    # источник
    src = resolve_actor_account(game, actor, source)

    if src.balance < amount:
        return False, "Недостаточно средств на выбранном счёте."

    # списываем
    src.set_balance(src.balance - amount)

    # зачисляем всегда на ЛИЧНЫЙ счёт получателя
    target.money += amount
    target.save(update_fields=["money"])

    return True, "Перевод выполнен."
