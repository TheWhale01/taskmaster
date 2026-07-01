from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, PositiveInt, NonNegativeInt, field_validator

class Task(BaseModel):
    cmd: str
    numprocs: PositiveInt
    umask: NonNegativeInt
    workingdir: Path
    autostart: bool
    autorestart: Literal['unexpected', 'never', 'always']
    exitcodes: list[NonNegativeInt] | NonNegativeInt
    startretries: NonNegativeInt
    starttime: NonNegativeInt
    stopsignal: str
    stoptime: NonNegativeInt
    stdout: Path
    stderr: Path
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator('env', mode='before')
    @classmethod
    def convert_str_env(cls, env):
        return {str(k): str(v) for k, v in env.items()}
