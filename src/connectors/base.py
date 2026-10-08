import logging
from abc import ABC, abstractmethod
from typing import List
from src.models import Job

logger = logging.getLogger("connectors")

class BaseConnector(ABC):
    platform: str = "Unknown"
    tier: int = 1

    @abstractmethod
    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        pass
