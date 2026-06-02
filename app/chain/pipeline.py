from app.chain.steps import PromptBuilder, LLMRunner, ResponseParser, ShotClassifierPrompt, ShotClassifierParser

oraklet = PromptBuilder() | LLMRunner() | ResponseParser()
slag_klassificerare = ShotClassifierPrompt() | LLMRunner() | ShotClassifierParser()
