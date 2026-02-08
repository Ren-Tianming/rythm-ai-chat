import os

# ===============================
# AWS 基础配置
# ===============================

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# ===============================
# Bedrock 模型配置（Claude 3 Haiku）
# ===============================
# ⚠️ 使用 invoke_model
# ⚠️ 不用 inference profile
# ⚠️ 直接跑通用这个

MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "anthropic.claude-3-haiku-20240307-v1:0"
)

# ===============================
# 推理参数（可选）
# ===============================

MAX_TOKENS = int(os.getenv("MAX_TOKENS", 512))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.7))


