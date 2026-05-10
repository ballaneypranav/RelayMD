from enum import Enum


class ClusterConfigStrategy(str, Enum):
    CONTINUOUS = "continuous"
    JIT_THRESHOLD = "jit_threshold"
    REACTIVE = "reactive"

    def __str__(self) -> str:
        return str(self.value)
