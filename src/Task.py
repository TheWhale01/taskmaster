from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, PositiveInt, NonNegativeInt

class Task(BaseModel):
    cmd: str
    numprocs: PositiveInt
    umask: NonNegativeInt
    workingdir: Path
    autostart: bool
    autorestart: Literal['unexpected', 'never', 'always']
    exitcodes: list[NonNegativeInt]
    startretries: NonNegativeInt
    starttime: NonNegativeInt
    stopsignal: str
    stoptime: NonNegativeInt
    stdout: Path
    stderr: Path
    env: dict = Field(default_factory=dict)
