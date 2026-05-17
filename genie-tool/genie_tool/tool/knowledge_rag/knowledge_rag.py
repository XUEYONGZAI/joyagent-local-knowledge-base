# -*- coding: utf-8 -*-
# =====================
#
#
# Author: your_name
# Date:   YYYY/MM/DD
# =====================
import os
import asyncio
import json
from typing import List, Dict, Any, Optional
from uuid import uuid4

from genie_tool.util.log_util import logger
from genie_tool.tool.knowledge_rag.file_processor import FileProcessor
from genie_tool.tool.knowledge_rag.vector_store import VectorStore
from genie_tool.tool.knowledge_rag.incremental_updater import IncrementalUpdater

class KnowledgeRAGAgent:
    """知识库RAG代理"""

    def __init__(self, request_id: str, query: str, file_paths: List[str] = None):
        self.request_id = request_id or str(uuid4())
        self.query = query
        self.file_paths = file_paths or []

        # 组件初始化
        self.file_processor = FileProcessor()
        self.vector_store = VectorStore(self.request_id)
        self.incremental_updater = IncrementalUpdater(self.vector_store)

        # 配置参数
        self.chunk_size = int(os.getenv("KNOWLEDGE_RAG_CHUNK_SIZE", 500))
        self.chunk_overlap = int(os.getenv("KNOWLEDGE_RAG_CHUNK_OVERLAP", 50))
        self.top_k = int(os.getenv("KNOWLEDGE_RAG_TOP_K", 5))
        self.max_context_length = int(os.getenv("KNOWLEDGE_RAG_MAX_CONTEXT_LENGTH", 3000))

        # 支持的分隔符（中英文）
        self.sentence_separators = set('.!?\n。！？；;、')

    def _chunk_text(self, content: str) -> List[str]:
        """
        将文本切分为小块，尽量在语义边界处切分

        Args:
            content: 原始文本

        Returns:
            切分后的文本块列表
        """
        if not content:
            return []

        chunks = []
        start = 0
        content_length = len(content)
        overlap = self.chunk_overlap

        while start < content_length:
            ideal_end = min(start + self.chunk_size, content_length)
            end = ideal_end

            if ideal_end < content_length:
                search_start = max(start, ideal_end - overlap)
                search_end = ideal_end

                paragraph_pos = content.rfind('\n\n', search_start, search_end)
                if paragraph_pos != -1:
                    end = paragraph_pos + 2
                else:
                    for i in range(search_end - search_start):
                        pos = search_end - i - 1
                        if content[pos] in self.sentence_separators:
                            end = pos + 1
                            break

            chunk = content[start:end].strip()

            if chunk and len(chunk) > 10:
                chunks.append(chunk)
            elif chunk:
                if chunks:
                    chunks[-1] = chunks[-1] + ' ' + chunk
                else:
                    chunks.append(chunk)

            if len(chunk) < self.chunk_size // 2:
                start = end
            else:
                start = max(start + self.chunk_size - overlap, end - overlap)

            if start >= content_length:
                break

        cleaned_chunks = []
        for chunk in chunks:
            if len(chunk) < 30 and cleaned_chunks:
                cleaned_chunks[-1] = cleaned_chunks[-1] + ' ' + chunk
            else:
                cleaned_chunks.append(chunk)

        logger.debug(f"Text chunked into {len(cleaned_chunks)} pieces (original length: {content_length})")
        return cleaned_chunks

    async def process_and_store(self) -> Dict[str, Any]:
        """
        处理文件并存储到向量数据库

        Returns:
            处理结果
        """
        if not self.file_paths:
            logger.info("No files to process")
            return {"status": "success", "processed_count": 0, "failed_count": 0, "stored_chunks": 0}

        logger.info(f"Processing {len(self.file_paths)} files")

        results = await self.file_processor.process_files_batch(self.file_paths)

        documents = []
        success_count = 0
        failed_count = 0
        total_chunks = 0

        for result in results:
            if result.get("status") == "success" and result.get("content"):
                content = result["content"]
                file_name = result["file_name"]
                file_path = result["file_path"]

                chunks = self._chunk_text(content)
                chunk_count = len(chunks)
                total_chunks += chunk_count

                logger.debug(f"File '{file_name}' split into {chunk_count} chunks")

                for i, chunk in enumerate(chunks):
                    documents.append({
                        "id": f"{file_path}_{i}",
                        "content": chunk,
                        "file_name": file_name,
                        "file_path": file_path,
                        "chunk_index": i,
                        "total_chunks": chunk_count,
                        "update_time": str(os.path.getmtime(file_path)),
                        "request_id": self.request_id
                    })

                success_count += 1
                logger.info(f"Processed file '{file_name}': {chunk_count} chunks created")
            else:
                failed_count += 1
                error_msg = result.get("error", "Unknown error")
                logger.warning(f"Failed to process file '{result.get('file_name', 'unknown')}': {error_msg}")

        stored_chunks = 0
        store_success = True

        if documents:
            logger.info(f"Storing {len(documents)} document chunks to vector store")
            store_success = await self.vector_store.store_vectors(documents)
            stored_chunks = len(documents) if store_success else 0

            if store_success:
                logger.info(f"Successfully stored {stored_chunks} document chunks")
            else:
                logger.error(f"Failed to store document chunks")
        else:
            logger.info("No documents to store")

        return {
            "status": "success" if store_success else "failed",
            "processed_count": success_count,
            "failed_count": failed_count,
            "stored_chunks": stored_chunks,
            "total_chunks_generated": total_chunks,
            "files_processed": [r.get("file_name") for r in results if r.get("status") == "success"]
        }

    async def retrieve_relevant_context(self) -> List[Dict[str, Any]]:
        """
        检索相关文档

        Returns:
            相关文档列表
        """
        if not self.query:
            logger.warning("Empty query")
            return []

        logger.info(f"Retrieving context for query: {self.query[:50]}...")

        results = await self.vector_store.search_vectors(
            query=self.query,
            limit=self.top_k
        )

        # 添加调试日志
        logger.debug(f"Search results type: {type(results)}")
        logger.debug(f"Search results: {results}")
        
        # 检查返回格式是否正确
        if isinstance(results, dict):
            logger.error(f"Expected list but got dict: {results}")
            # 如果返回的是字典，检查是否有错误信息
            if results.get("status") == "failed":
                logger.error(f"Search failed: {results.get('error')}")
            return []
        elif not isinstance(results, list):
            logger.error(f"Unexpected results type: {type(results)}")
            return []

        logger.info(f"Found {len(results)} relevant documents")
        return results

    def _build_prompt(self, context: List[Dict[str, Any]]) -> str:
        """构建提示词"""
        context_text = ""
        total_length = 0

        for i, doc in enumerate(context):
            doc_text = f"【文档{i+1}】\n{doc['content']}\n\n"
            if total_length + len(doc_text) <= self.max_context_length:
                context_text += doc_text
                total_length += len(doc_text)
            else:
                logger.debug(f"Context truncated after {i+1} documents")
                break

        system_prompt = """
您是一个专业的知识库问答助手，擅长根据提供的文档信息回答用户问题。

回答规则：
1. 必须基于提供的上下文信息进行回答，不要编造信息
2. 如果上下文信息不足以回答问题，请明确说明"根据当前知识库，无法回答该问题"
3. 回答应简洁明了，直接针对问题进行解答
4. 如果有多个相关文档，请综合所有相关信息进行回答
5. 回答语言应与用户问题语言保持一致
"""

        prompt = f"""
{system_prompt}

上下文信息：
{context_text}

用户问题：{self.query}

请根据以上上下文信息回答问题。
"""
        return prompt

    async def generate_answer(self, context: List[Dict[str, Any]] = None) -> str:
        """
        生成回答

        Args:
            context: 上下文文档列表

        Returns:
            生成的回答
        """
        if not context or len(context) == 0:
            logger.info("No relevant context found for query")
            return "知识库中没有找到相关信息，无法回答您的问题。"

        logger.info(f"Generating answer using {len(context)} context documents")

        prompt = self._build_prompt(context)

        try:
            from genie_tool.util.llm_util import ask_llm_with_content

            answer = await ask_llm_with_content(
                messages=prompt,
                model=os.getenv("KNOWLEDGE_RAG_MODEL", "gpt-4o-mini")
            )

            if answer:
                answer = answer.strip()
                logger.info(f"Answer generated successfully (length: {len(answer)})")
                return answer
            else:
                return "未能生成回答。"

        except ImportError:
            logger.error("llm_util module not found")
            return "无法生成回答：缺少必要的依赖模块。"
        except Exception as e:
            logger.error(f"Error generating answer: {str(e)}", exc_info=True)
            return f"生成回答时发生错误: {str(e)}"

    async def generate_answer_stream(self):
        """
        流式生成回答

        Yields:
            回答片段
        """
        context = await self.retrieve_relevant_context()

        if not context or len(context) == 0:
            logger.info("No relevant context found for streaming answer")
            yield "知识库中没有找到相关信息，无法回答您的问题。"
            return

        logger.info(f"Generating streaming answer using {len(context)} context documents")

        prompt = self._build_prompt(context)

        try:
            from genie_tool.util.llm_util import ask_llm_stream

            async for chunk in ask_llm_stream(
                messages=prompt,
                model=os.getenv("KNOWLEDGE_RAG_MODEL", "gpt-4o-mini")
            ):
                if chunk:
                    yield chunk

            logger.info("Streaming answer completed")

        except ImportError:
            logger.error("llm_util module not found for streaming")
            yield "无法生成流式回答：缺少必要的依赖模块。"
        except Exception as e:
            logger.error(f"Error generating streamed answer: {str(e)}", exc_info=True)
            yield f"生成回答时发生错误: {str(e)}"

    async def run(self) -> Dict[str, Any]:
        """
        执行完整的RAG流程

        Returns:
            包含回答和相关信息的字典
        """
        start_time = asyncio.get_event_loop().time()

        try:
            logger.info(f"Starting RAG workflow for request: {self.request_id}")

            if self.file_paths:
                process_result = await self.process_and_store()
                logger.info(f"File processing completed: {process_result}")

            context = await self.retrieve_relevant_context()

            answer = await self.generate_answer(context)

            elapsed_time = asyncio.get_event_loop().time() - start_time

            result = {
                "status": "success",
                "request_id": self.request_id,
                "answer": answer,
                "context_count": len(context),
                "retrieval_contexts": context,
                "processing_time_ms": int(elapsed_time * 1000)
            }

            logger.info(f"RAG workflow completed in {elapsed_time:.2f}s")
            return result

        except Exception as e:
            elapsed_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Error in RAG workflow: {str(e)}", exc_info=True)

            return {
                "status": "failed",
                "request_id": self.request_id,
                "error": str(e),
                "processing_time_ms": int(elapsed_time * 1000)
            }

    def run_sync(self) -> Dict[str, Any]:
        """
        同步执行RAG流程（用于测试）

        Returns:
            包含回答和相关信息的字典
        """
        return asyncio.run(self.run())

async def knowledge_rag_agent(
    task: str,
    file_paths: List[str],
    request_id: str,
    stream: bool = False,
):
    """
    知识库RAG工具入口函数

    Args:
        task: 任务描述
        file_paths: 文件路径列表
        request_id: 请求ID
        stream: 是否流式输出

    Yields:
        响应内容
    """
    agent = KnowledgeRAGAgent(
        request_id=request_id,
        query=task,
        file_paths=file_paths
    )

    if stream:
        if file_paths:
            await agent.process_and_store()

        async for chunk in agent.generate_answer_stream():
            yield chunk
    else:
        result = await agent.run()
        yield result["answer"]