from Task import Task
from typing import Literal
from pydantic import BaseModel

class NotificationItem(BaseModel):
    taskname: str
    task: Task
    retries: int
    status: Literal['started', 'healthy', 'stopped', 'crashed']
