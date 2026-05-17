# -*- coding: utf-8 -*-
# =====================
#
#
# Author: liumin.423
# Date:   2025/7/8
# =====================
import json
import os
from typing import List, Any, Optional, AsyncIterator

from litellm import acompletion

from genie_tool.util.log_util import logger
from genie_tool.util.sensitive_detection import SensitiveWordsReplace


def _prepare_messages(messages: str | List[Any]) -> List[Any]:
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    if os.getenv("SENSITIVE_WORD_REPLACE", "false") == "true":
        for message in messages:
            if isinstance(message.get("content"), str):
                message["content"] = SensitiveWordsReplace.replace(message["content"])
            else:
                message["content"] = json.loads(
                    SensitiveWordsReplace.replace(json.dumps(message["content"], ensure_ascii=False)))
    return messages


def _get_model_and_config(model_name: str = None) -> tuple:
    """获取模型名称和配置，优先使用 DeepSeek"""
    # 优先使用 DeepSeek 配置
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    deepseek_api_base = os.getenv("DEEPSEEK_API_BASE")
    
    if deepseek_api_key and deepseek_api_base:
        # 使用 DeepSeek - litellm 需要 deepseek/deepseek-chat 格式
        model = model_name or os.getenv("KNOWLEDGE_RAG_MODEL", "deepseek/deepseek-chat")
        api_key = deepseek_api_key
        api_base = deepseek_api_base
        logger.info(f"Using DeepSeek model: {model}")
    else:
        # 使用 OpenAI
        model = model_name or os.getenv("KNOWLEDGE_RAG_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_API_BASE")
        logger.info(f"Using OpenAI model: {model}")
    
    return model, api_key, api_base


async def ask_llm(
        messages: str | List[Any],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        extra_headers: Optional[dict] = None,
        **kwargs,
):
    messages = _prepare_messages(messages)
    model, api_key, api_base = _get_model_and_config(model)

    response = await acompletion(
        messages=messages,
        model=model,
        temperature=temperature,
        top_p=top_p,
        stream=False,
        api_key=api_key,
        api_base=api_base,
        extra_headers=extra_headers,
        **kwargs
    )

    return response


async def ask_llm_with_content(
        messages: str | List[Any],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        extra_headers: Optional[dict] = None,
        **kwargs,
) -> str:
    messages = _prepare_messages(messages)
    model, api_key, api_base = _get_model_and_config(model)

    response = await acompletion(
        messages=messages,
        model=model,
        temperature=temperature,
        top_p=top_p,
        stream=False,
        api_key=api_key,
        api_base=api_base,
        extra_headers=extra_headers,
        **kwargs
    )

    # 兼容不同格式的响应
    try:
        # litellm 返回的对象格式
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                return choice.message.content
            # 字典格式
            elif isinstance(choice, dict) and 'message' in choice and 'content' in choice['message']:
                return choice['message']['content']
        
        # 纯字典格式响应
        if isinstance(response, dict) and 'choices' in response and response['choices']:
            choice = response['choices'][0]
            if 'message' in choice and 'content' in choice['message']:
                return choice['message']['content']
        
        logger.error(f"Unexpected response format: {type(response)}")
        return ""
    except Exception as e:
        logger.error(f"Error parsing response: {str(e)}")
        return ""


async def ask_llm_stream(
        messages: str | List[Any],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        **kwargs,
) -> AsyncIterator[str]:
    messages = _prepare_messages(messages)
    model, api_key, api_base = _get_model_and_config(model)

    response = await acompletion(
        messages=messages,
        model=model,
        temperature=temperature,
        top_p=top_p,
        stream=True,
        api_key=api_key,
        api_base=api_base,
        **kwargs
    )

    async for chunk in response:
        if chunk.choices and chunk.choices[0] and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


if __name__ == "__main__":
    pass