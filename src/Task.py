from pathlib import Path
from typing import Literal, Any
from pydantic import BaseModel, Field, PositiveInt, NonNegativeInt, field_validator, model_validator

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
    stdout: Path | None = None
    stderr: Path | None = None
    env: dict[str, str] = Field(default_factory=dict)
    retry_count: int = Field(default=1, exclude=True)

    @model_validator(mode='before')
    @classmethod
    def prevent_internal_fields(cls, data: Any) -> Any:
        internal_fields: list[str] = ['retry_count']
        if isinstance(data, dict):
            for field in internal_fields:
                if field in data:
                    raise ValueError("The 'retry_count field is strictly for internal use and cannot be defined in the configuration file.")
        return data

    @field_validator('env', mode='before')
    @classmethod
    def convert_str_env(cls, env):
        return {str(k): str(v) for k, v in env.items()}
