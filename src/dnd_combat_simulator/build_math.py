"""Pure build-level combat math defaults."""

from dataclasses import dataclass, fields
from typing import Self


@dataclass(frozen=True, slots=True)
class BuildMathDefaults:
    """Numerical defaults for build-level combat math.

    The formulas are intentionally simple arithmetic defaults. This model is not
    a class system, character sheet, or rules engine.
    """

    ability_modifier: int = 3
    proficiency_bonus: int = 2
    attack_bonus_adjustment: int = 0
    save_dc_adjustment: int = 0

    def __post_init__(self: Self) -> None:
        """Validate stored values without coercion or range limits."""
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int:
                msg = f"{field.name} must be an integer"
                raise ValueError(msg)

    @property
    def attack_bonus(self: Self) -> int:
        return (
            self.ability_modifier
            + self.proficiency_bonus
            + self.attack_bonus_adjustment
        )

    @property
    def save_dc(self: Self) -> int:
        return (
            8 + self.ability_modifier + self.proficiency_bonus + self.save_dc_adjustment
        )
