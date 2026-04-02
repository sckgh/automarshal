"""Flag state enumeration for track sectors and global overrides."""

from enum import Enum, auto


class FlagState(str, Enum):
    """All possible flag states, ordered by ascending priority."""

    GREEN = "GREEN"
    WHITE = "WHITE"
    BLUE = "BLUE"
    YELLOW = "YELLOW"
    SAFETY_CAR = "SAFETY_CAR"
    RED = "RED"
    CHEQUERED = "CHEQUERED"
    MANUAL_ONLY = "MANUAL_ONLY"  # Failsafe: telemetry lost

    def __lt__(self, other: "FlagState") -> bool:
        return _PRIORITY[self] < _PRIORITY[other]

    def __le__(self, other: "FlagState") -> bool:
        return _PRIORITY[self] <= _PRIORITY[other]

    def __gt__(self, other: "FlagState") -> bool:
        return _PRIORITY[self] > _PRIORITY[other]

    def __ge__(self, other: "FlagState") -> bool:
        return _PRIORITY[self] >= _PRIORITY[other]


# Higher number = higher priority
_PRIORITY: dict[FlagState, int] = {
    FlagState.GREEN: 0,
    FlagState.WHITE: 1,
    FlagState.BLUE: 2,
    FlagState.YELLOW: 3,
    FlagState.SAFETY_CAR: 4,
    FlagState.RED: 5,
    FlagState.CHEQUERED: 6,
    FlagState.MANUAL_ONLY: 7,
}
