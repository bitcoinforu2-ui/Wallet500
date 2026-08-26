from abc import ABC, abstractmethod
from collections.abc import Iterable
from ..models import MarketEvent


class ChainAdapter(ABC):
    name: str

    @abstractmethod
    def scan(self) -> Iterable[MarketEvent]:
        """Yield normalized market events for the chain."""
        raise NotImplementedError
