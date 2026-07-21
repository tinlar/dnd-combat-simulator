import pytest

from dnd_combat_simulator.combat import (
    AttackResult,
    AttackRollMode,
    SuccessfulSaveDamage,
    resolve_saving_throw_damage,
    resolve_weapon_attack,
)


class PredictableRng:
    def __init__(self, rolls: list[int]) -> None:
        self.rolls = rolls
        self.calls: list[tuple[int, int]] = []

    def randint(self, a: int, b: int) -> int:
        self.calls.append((a, b))
        return self.rolls.pop(0)


def test_natural_1_automatically_misses_even_when_total_meets_ac() -> None:
    rng = PredictableRng([1])

    assert resolve_weapon_attack(
        attack_bonus=99,
        target_armor_class=10,
        damage_dice="1d8",
        damage_modifier=4,
        rng=rng,
    ) == AttackResult(
        attack_roll_mode=AttackRollMode.NORMAL,
        natural_d20_roll=1,
        d20_rolls=(1,),
        modified_attack_total=100,
        hit=False,
        critical_hit=False,
        damage_dealt=0,
    )
    assert rng.calls == [(1, 20)]


def test_natural_20_automatically_hits_and_is_critical() -> None:
    rng = PredictableRng([20, 3, 4])

    assert resolve_weapon_attack(
        attack_bonus=-99,
        target_armor_class=30,
        damage_dice="1d8",
        damage_modifier=2,
        rng=rng,
    ) == AttackResult(
        attack_roll_mode=AttackRollMode.NORMAL,
        natural_d20_roll=20,
        d20_rolls=(20,),
        modified_attack_total=-79,
        hit=True,
        critical_hit=True,
        damage_dealt=9,
    )
    assert rng.calls == [(1, 20), (1, 8), (1, 8)]


def test_normal_hit_rolls_damage_once_and_adds_modifier() -> None:
    rng = PredictableRng([14, 5])

    assert resolve_weapon_attack(
        attack_bonus=4,
        target_armor_class=16,
        damage_dice="1d8",
        damage_modifier=3,
        rng=rng,
    ) == AttackResult(
        attack_roll_mode=AttackRollMode.NORMAL,
        natural_d20_roll=14,
        d20_rolls=(14,),
        modified_attack_total=18,
        hit=True,
        critical_hit=False,
        damage_dealt=8,
    )
    assert rng.calls == [(1, 20), (1, 8)]


def test_attack_total_tie_hits_target_armor_class() -> None:
    rng = PredictableRng([12, 6])

    result = resolve_weapon_attack(
        attack_bonus=3,
        target_armor_class=15,
        damage_dice="1d6",
        damage_modifier=1,
        rng=rng,
    )

    assert result.hit is True
    assert result.modified_attack_total == 15
    assert result.damage_dealt == 7


def test_miss_deals_zero_damage_and_does_not_roll_damage() -> None:
    rng = PredictableRng([7])

    result = resolve_weapon_attack(
        attack_bonus=2,
        target_armor_class=20,
        damage_dice="2d6",
        damage_modifier=10,
        rng=rng,
    )

    assert result == AttackResult(
        attack_roll_mode=AttackRollMode.NORMAL,
        natural_d20_roll=7,
        d20_rolls=(7,),
        modified_attack_total=9,
        hit=False,
        critical_hit=False,
        damage_dealt=0,
    )
    assert rng.calls == [(1, 20)]


def test_critical_damage_doubles_only_damage_dice_and_adds_modifier_once() -> None:
    rng = PredictableRng([20, 2, 3, 4, 5])

    result = resolve_weapon_attack(
        attack_bonus=5,
        target_armor_class=18,
        damage_dice="2d6",
        damage_modifier=4,
        rng=rng,
    )

    assert result.damage_dealt == 18
    assert result.critical_hit is True
    assert rng.calls == [(1, 20), (1, 6), (1, 6), (1, 6), (1, 6)]


def test_hit_damage_cannot_be_below_zero() -> None:
    rng = PredictableRng([15, 1])

    result = resolve_weapon_attack(
        attack_bonus=5,
        target_armor_class=12,
        damage_dice="1d4",
        damage_modifier=-10,
        rng=rng,
    )

    assert result.hit is True
    assert result.damage_dealt == 0


def test_damage_dice_modifiers_must_be_passed_separately() -> None:
    with pytest.raises(ValueError, match="Damage dice must not include a modifier"):
        resolve_weapon_attack(
            attack_bonus=5,
            target_armor_class=12,
            damage_dice="1d8+2",
            damage_modifier=0,
            rng=PredictableRng([15]),
        )


def test_advantage_uses_higher_selected_die_for_hit() -> None:
    rng = PredictableRng([4, 16, 5])

    result = resolve_weapon_attack(
        attack_bonus=2,
        target_armor_class=18,
        damage_dice="1d8",
        damage_modifier=1,
        attack_roll_mode=AttackRollMode.ADVANTAGE,
        rng=rng,
    )

    assert result == AttackResult(
        attack_roll_mode=AttackRollMode.ADVANTAGE,
        natural_d20_roll=16,
        d20_rolls=(4, 16),
        modified_attack_total=18,
        hit=True,
        critical_hit=False,
        damage_dealt=6,
    )
    assert rng.calls == [(1, 20), (1, 20), (1, 8)]


def test_disadvantage_uses_lower_selected_die_for_miss() -> None:
    rng = PredictableRng([17, 6])

    result = resolve_weapon_attack(
        attack_bonus=8,
        target_armor_class=15,
        damage_dice="1d8",
        damage_modifier=1,
        attack_roll_mode=AttackRollMode.DISADVANTAGE,
        rng=rng,
    )

    assert result == AttackResult(
        attack_roll_mode=AttackRollMode.DISADVANTAGE,
        natural_d20_roll=6,
        d20_rolls=(17, 6),
        modified_attack_total=14,
        hit=False,
        critical_hit=False,
        damage_dealt=0,
    )
    assert rng.calls == [(1, 20), (1, 20)]


def test_advantage_selected_natural_20_is_critical() -> None:
    rng = PredictableRng([1, 20, 2, 3])

    result = resolve_weapon_attack(
        attack_bonus=-99,
        target_armor_class=30,
        damage_dice="1d6",
        damage_modifier=1,
        attack_roll_mode=AttackRollMode.ADVANTAGE,
        rng=rng,
    )

    assert result.natural_d20_roll == 20
    assert result.hit is True
    assert result.critical_hit is True
    assert result.damage_dealt == 6
    assert rng.calls == [(1, 20), (1, 20), (1, 6), (1, 6)]


def test_disadvantage_selected_natural_1_automatically_misses() -> None:
    rng = PredictableRng([20, 1])

    result = resolve_weapon_attack(
        attack_bonus=99,
        target_armor_class=10,
        damage_dice="1d8",
        damage_modifier=4,
        attack_roll_mode=AttackRollMode.DISADVANTAGE,
        rng=rng,
    )

    assert result.natural_d20_roll == 1
    assert result.hit is False
    assert result.critical_hit is False
    assert result.damage_dealt == 0
    assert rng.calls == [(1, 20), (1, 20)]


def test_saving_throw_succeeds_when_total_equals_save_dc() -> None:
    result = resolve_saving_throw_damage(
        save_dc=15,
        enemy_save_bonus=3,
        damage_dice="1d6",
        damage_modifier=2,
        rng=PredictableRng([12]),
    )

    assert result.successful_save is True
    assert result.failed_save is False
    assert result.damage_dealt == 0


def test_saving_throw_fails_when_total_below_save_dc_and_deals_full_damage() -> None:
    result = resolve_saving_throw_damage(
        save_dc=15,
        enemy_save_bonus=3,
        damage_dice="1d6",
        damage_modifier=2,
        rng=PredictableRng([11, 4]),
    )

    assert result.failed_save is True
    assert result.damage_dealt == 6


def test_saving_throw_natural_1_can_succeed_with_sufficient_bonus() -> None:
    result = resolve_saving_throw_damage(
        save_dc=15,
        enemy_save_bonus=14,
        damage_dice="1d6",
        damage_modifier=2,
        rng=PredictableRng([1]),
    )

    assert result.successful_save is True


def test_saving_throw_natural_20_can_fail_against_high_dc() -> None:
    result = resolve_saving_throw_damage(
        save_dc=25,
        enemy_save_bonus=3,
        damage_dice="1d6",
        damage_modifier=2,
        rng=PredictableRng([20, 5]),
    )

    assert result.failed_save is True
    assert result.damage_dealt == 7


def test_successful_save_can_deal_half_damage_rounded_down_after_modifier() -> None:
    result = resolve_saving_throw_damage(
        save_dc=15,
        enemy_save_bonus=3,
        damage_dice="1d6",
        damage_modifier=2,
        successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
        rng=PredictableRng([12, 3]),
    )

    assert result.successful_save is True
    assert result.damage_dealt == 2


def test_saving_throws_never_critically_hit() -> None:
    result = resolve_saving_throw_damage(
        save_dc=15,
        enemy_save_bonus=0,
        damage_dice="1d6",
        damage_modifier=2,
        rng=PredictableRng([20, 3]),
    )

    assert result.critical_hit is False
