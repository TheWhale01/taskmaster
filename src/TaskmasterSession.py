import requests
from typing import Optional
from urllib.parse import urljoin

class TaskmasterSession(requests.Session):
    def __init__(self, base_url: Optional[str] = None)
        super().__init__()
        self.base_url = base_url

    def request(self, method, url, *args, **kwargs):
        if self.base_url is None:
            raise ValueError("base_url attribute is None. Please instanciate the object before calling this function.")
        full_url: str = urljoin(self.base_url, url)
        return super().request(method, full_url, *args, **kwargs)
