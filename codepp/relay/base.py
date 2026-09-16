from abc import ABC, abstractmethod


class RelayProvider(ABC):
    @abstractmethod
    def send(self, request: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def receive(self) -> str:
        raise NotImplementedError
