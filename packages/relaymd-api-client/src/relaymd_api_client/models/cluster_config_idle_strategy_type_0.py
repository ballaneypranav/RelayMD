from enum import Enum


class ClusterConfigIdleStrategyType0(str, Enum):
    IMMEDIATE_EXIT = "immediate_exit"
    POLL_THEN_EXIT = "poll_then_exit"

    def __str__(self) -> str:
        return str(self.value)
