import boto3
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
# 初始化 Bedrock 客户端 (注意选择你有权限的区域，如 us-east-1 或 ap-northeast-1)
client = boto3.client("bedrock-runtime", region_name="us-east-1")

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(request: ChatRequest):
    model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
    
    # 构造 Converse API 格式
    conversation = [
        {
            "role": "user",
            "content": [{"text": request.message}]
        }
    ]
    
    response = client.converse(
        modelId=model_id,
        messages=conversation,
        inferenceConfig={"maxTokens": 512, "temperature": 0.7}
    )
    
    # 提取返回文本
    output_text = response["output"]["message"]["content"]["text"]
    return {"reply": output_text}

# 本地调试入口
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)