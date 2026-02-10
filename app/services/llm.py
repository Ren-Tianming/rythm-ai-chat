import json
import boto3
from typing import List
from app.core.config import MODEL_ID, AWS_REGION
from app.schemas.chat import Message

class BedrockLLMService:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION
        )

    def chat(self, prompt: str, history: List[Message]) -> str:
        messages = []

        # 把历史对话塞进 Claude
        for msg in history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # 当前用户输入
        messages.append({
            "role": "user",
            "content": prompt
        })

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "temperature": 0.7,
            "messages": messages
        }

        response = self.client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]


llm_service = BedrockLLMService()
