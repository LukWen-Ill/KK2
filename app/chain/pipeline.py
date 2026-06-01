from app.chain.steps import PromptBuilder, LLMRunner, ResponseParser

oraklet = PromptBuilder() | LLMRunner() | ResponseParser()
