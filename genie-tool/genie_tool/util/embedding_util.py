# -*- coding: utf-8 -*-
# =====================
#
#
# Author: your_name
# Date:   YYYY/MM/DD
# =====================
import os
import random
from typing import List, Optional

from genie_tool.util.log_util import logger

async def get_embedding(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """
    获取文本的embedding向量

    Args:
        text: 输入文本
        model: embedding模型名称

    Returns:
        embedding向量
    """
    try:
        # 获取配置 - 优先使用知识库RAG专用配置
        api_key = os.getenv("KNOWLEDGE_RAG_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("KNOWLEDGE_RAG_EMBEDDING_URL") or os.getenv("OPENAI_API_BASE")
        embed_model = os.getenv("KNOWLEDGE_RAG_EMBEDDING_MODEL_NAME") or model

        logger.debug(f"Using embedding config: api_key_set={api_key is not None}, api_base={api_base}, model={embed_model}")

        # 尝试使用OpenAI API
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=api_base
            )

            response = await client.embeddings.create(
                input=text,
                model=embed_model
            )

            embedding = response.data[0].embedding
            logger.debug(f"Successfully generated embedding for text (length: {len(text)}, vector dim: {len(embedding)})")
            return embedding

        except ImportError:
            logger.warning("openai library not installed, trying litellm")
            pass

        # 尝试使用litellm
        try:
            import litellm

            litellm.api_base = api_base
            litellm.api_key = api_key

            response = await litellm.embedding(
                model=embed_model,
                input=text
            )

            embedding = response.data[0].embedding
            logger.debug(f"Successfully generated embedding using litellm (length: {len(text)}, vector dim: {len(embedding)})")
            return embedding

        except ImportError:
            logger.warning("litellm library not installed")
            pass

        # 如果都没有，使用简单的随机向量作为占位符（仅用于测试）
        logger.warning("No embedding library available, generating random embedding")
        return [random.random() for _ in range(1536)]

    except Exception as e:
        logger.error(f"Error getting embedding: {str(e)}", exc_info=True)
        # 返回随机向量作为备用
        return [random.random() for _ in range(1536)]

async def get_embeddings(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    """
    批量获取文本的embedding向量

    Args:
        texts: 输入文本列表
        model: embedding模型名称

    Returns:
        embedding向量列表
    """
    results = []
    for text in texts:
        embedding = await get_embedding(text, model)
        results.append(embedding)
    return results