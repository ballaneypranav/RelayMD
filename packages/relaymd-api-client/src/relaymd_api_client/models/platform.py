from enum import Enum


class Platform(str, Enum):
    HPC = "hpc"
    SALAD = "salad"

    def __str__(self) -> str:
        return str(self.value)
