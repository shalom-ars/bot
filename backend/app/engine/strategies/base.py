from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseStrategy(ABC):
    @abstractmethod
    def evaluate(self, tick: Any, features: dict, **kwargs) -> Dict[str, Any]:
        pass
