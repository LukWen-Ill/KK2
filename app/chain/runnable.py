from abc import ABC, abstractmethod
from typing import Generic, TypeVar

I = TypeVar("I")
O = TypeVar("O")


class Runnable(ABC, Generic[I, O]):
    @abstractmethod
    def invoke(self, input: I) -> O: ...

    def __or__(self, other: "Runnable") -> "RunnableSequence":
        return RunnableSequence(self, other)

    def __ror__(self, other: "Runnable") -> "RunnableSequence":
        return RunnableSequence(other, self)


class RunnableSequence(Runnable):
    def __init__(self, *steps: Runnable):
        self.steps = list(steps)

    def __or__(self, other: "Runnable") -> "RunnableSequence":
        return RunnableSequence(*self.steps, other)

    def invoke(self, input):
        result = input
        for step in self.steps:
            result = step.invoke(result)
        return result
