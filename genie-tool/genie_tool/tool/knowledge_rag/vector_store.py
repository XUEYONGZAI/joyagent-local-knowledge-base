# -*- coding: utf-8 -*-
# =====================
#
#
# Author: your_name
# Date:   YYYY/MM/DD
# =====================
import os
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple

from genie_tool.util.log_util import logger

class VectorStore:
    """向量存储模块"""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.embedding_model = os.getenv("KNOWLEDGE_RAG_EMBEDDING_MODEL_NAME", "text-embedding-3-small")
        self.qdrant_url = os.getenv("KNOWLEDGE_RAG_QDRANT_URL", None)
        self.qdrant_host = os.getenv("KNOWLEDGE_RAG_QDRANT_HOST", None)
        self.qdrant_port = int(os.getenv("KNOWLEDGE_RAG_QDRANT_PORT", 6333))
        self.qdrant_api_key = os.getenv("KNOWLEDGE_RAG_QDRANT_API_KEY", None)
        self.collection_name = os.getenv("KNOWLEDGE_RAG_QDRANT_COLLECTION", "knowledge_rag")

        # 根据模型设置向量维度
        self.vector_size = self._get_vector_size()

        # 批量处理配置
        self.batch_size = int(os.getenv("KNOWLEDGE_RAG_BATCH_SIZE", 32))
        self.embedding_batch_size = int(os.getenv("KNOWLEDGE_RAG_EMBEDDING_BATCH_SIZE", 100))

        # 缓存配置
        self.cache_max_size = int(os.getenv("KNOWLEDGE_RAG_CACHE_MAX_SIZE", 1000))
        self.cache_ttl = int(os.getenv("KNOWLEDGE_RAG_CACHE_TTL", 3600))  # 缓存过期时间（秒）

        # 初始化Qdrant客户端
        self.qdrant_client = self._init_qdrant_client()

        # 缓存已获取的embedding {text: (embedding, timestamp)}
        self._embedding_cache = {}
        # 缓存访问顺序，用于LRU淘汰
        self._cache_access_order = []

    def _get_vector_size(self) -> int:
        """获取向量维度"""
        model_sizes = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
            "text-embedding-v4": 1024,  # 阿里云 text-embedding-v4
            "text-embedding-v3": 1024,  # 阿里云 text-embedding-v3
        }
        return model_sizes.get(self.embedding_model, 1536)

    def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """从缓存获取embedding，处理过期缓存"""
        import time

        cached = self._embedding_cache.get(text)
        if cached:
            embedding, timestamp = cached
            # 检查缓存是否过期
            if time.time() - timestamp < self.cache_ttl:
                # 更新访问顺序
                if text in self._cache_access_order:
                    self._cache_access_order.remove(text)
                self._cache_access_order.append(text)
                return embedding
            else:
                # 缓存过期，删除
                del self._embedding_cache[text]
                if text in self._cache_access_order:
                    self._cache_access_order.remove(text)
        return None

    def _set_cached_embedding(self, text: str, embedding: List[float]):
        """设置embedding缓存，实现LRU淘汰"""
        import time

        # 如果缓存已满，淘汰最久未使用的
        if len(self._embedding_cache) >= self.cache_max_size:
            if self._cache_access_order:
                oldest = self._cache_access_order.pop(0)
                del self._embedding_cache[oldest]

        self._embedding_cache[text] = (embedding, time.time())
        if text in self._cache_access_order:
            self._cache_access_order.remove(text)
        self._cache_access_order.append(text)

    def _init_qdrant_client(self):
        """初始化Qdrant客户端"""
        try:
            from qdrant_client import QdrantClient

            if self.qdrant_url:
                logger.info(f"Initializing Qdrant client with URL: {self.qdrant_url}")
                try:
                    # 禁用gRPC以避免兼容性问题
                    client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key, prefer_grpc=False)
                    # 测试连接
                    client.get_collections()
                except Exception as e:
                    logger.warning(f"Failed to connect to Qdrant server: {str(e)}. Falling back to in-memory mode.")
                    client = QdrantClient(":memory:", api_key=self.qdrant_api_key, prefer_grpc=False)
            elif self.qdrant_host:
                logger.info(f"Initializing Qdrant client with host: {self.qdrant_host}:{self.qdrant_port}")
                try:
                    # 禁用gRPC以避免兼容性问题
                    client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port, api_key=self.qdrant_api_key, prefer_grpc=False)
                    # 测试连接
                    client.get_collections()
                except Exception as e:
                    logger.warning(f"Failed to connect to Qdrant server: {str(e)}. Falling back to in-memory mode.")
                    client = QdrantClient(":memory:", api_key=self.qdrant_api_key, prefer_grpc=False)
            else:
                logger.warning("Qdrant configuration not found, using in-memory mode")
                # 使用内存模式用于测试，不使用GRPC
                client = QdrantClient(":memory:", api_key=self.qdrant_api_key, prefer_grpc=False)

            # 确保集合存在
            from qdrant_client.models import VectorParams
            try:
                client.get_collection(collection_name=self.collection_name)
                logger.info(f"Collection '{self.collection_name}' already exists")
            except Exception:
                # 集合不存在，创建新集合
                logger.info(f"Creating collection '{self.collection_name}'")
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance="Cosine"),
                    optimizers_config={
                        "deleted_threshold": 0.2,
                        "vacuum_min_vector_number": 1000
                    }
                )

            return client
        except ImportError:
            logger.error("qdrant-client library not installed")
            return None
        except Exception as e:
            logger.error(f"Error initializing Qdrant client: {str(e)}", exc_info=True)
            return None

    def _generate_document_id(self, doc: Dict[str, Any]) -> str:
        """
        生成文档唯一ID

        Args:
            doc: 文档字典

        Returns:
            唯一ID字符串
        """
        id_str = f"{doc.get('file_path', '')}_{doc.get('chunk_index', 0)}_{doc.get('id', '')}"
        return hashlib.md5(id_str.encode()).hexdigest()

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的embedding向量"""
        # 先检查缓存
        cached = self._get_cached_embedding(text)
        if cached is not None:
            return cached

        # 获取embedding
        try:
            from genie_tool.util.embedding_util import get_embedding

            embedding = await get_embedding(text, self.embedding_model)

            # 设置缓存
            self._set_cached_embedding(text, embedding)

            return embedding
        except Exception as e:
            logger.error(f"Error getting embedding: {str(e)}", exc_info=True)
            raise

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取文本的embedding向量"""
        results = []
        uncached_texts = []
        text_indices = {}

        # 分离已缓存和未缓存的文本
        for i, text in enumerate(texts):
            cached = self._get_cached_embedding(text)
            if cached is not None:
                results.append((i, cached))
            else:
                text_indices[len(uncached_texts)] = i
                uncached_texts.append(text)

        # 批量获取未缓存文本的embedding
        if uncached_texts:
            try:
                from genie_tool.util.embedding_util import get_embeddings

                embeddings = await get_embeddings(uncached_texts, self.embedding_model)

                for i, embedding in enumerate(embeddings):
                    original_index = text_indices[i]
                    results.append((original_index, embedding))
                    # 设置缓存
                    self._set_cached_embedding(uncached_texts[i], embedding)
            except Exception as e:
                logger.error(f"Error getting embeddings batch: {str(e)}", exc_info=True)
                raise

        # 按原始顺序排序
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    async def store_vectors(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        存储文档向量

        Args:
            documents: 文档列表，每个文档包含id, content, file_name, file_path等字段

        Returns:
            存储结果
        """
        if not self.qdrant_client:
            return {"status": "failed", "error": "Qdrant client not initialized"}

        try:
            # 提取文本内容
            texts = [doc.get("content", "") for doc in documents]

            # 批量获取embedding
            embeddings = await self.get_embeddings_batch(texts)

            # 准备Qdrant points
            from qdrant_client.models import PointStruct

            points = []
            for doc, embedding in zip(documents, embeddings):
                point_id = self._generate_document_id(doc)
                metadata = {
                    "file_name": doc.get("file_name", ""),
                    "file_path": doc.get("file_path", ""),
                    "chunk_index": doc.get("chunk_index", 0),
                    "total_chunks": doc.get("total_chunks", 1),
                    "content": doc.get("content", ""),
                    "update_time": doc.get("update_time", "")
                }

                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=metadata
                ))

            # 批量插入
            operation_info = self.qdrant_client.upsert(
                collection_name=self.collection_name,
                wait=True,
                points=points
            )

            logger.info(f"Stored {len(points)} vectors in collection '{self.collection_name}'")

            return {
                "status": "success",
                "stored_count": len(points),
                "operation_info": str(operation_info)
            }

        except Exception as e:
            logger.error(f"Error storing vectors: {str(e)}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    async def search_vectors(self, query: str, limit: int = 5, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        搜索相似向量

        Args:
            query: 查询文本
            limit: 返回结果数量
            filters: 过滤条件

        Returns:
            搜索结果列表
        """
        if not self.qdrant_client:
            return []

        try:
            # 获取查询向量
            query_vector = await self.get_embedding(query)

            # 构建过滤器
            qdrant_filter = None
            if filters:
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                must_conditions = []
                for key, value in filters.items():
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )

                if must_conditions:
                    qdrant_filter = Filter(must=must_conditions)

            # 执行搜索
            try:
                logger.debug(f"Calling query_points with collection: {self.collection_name}, limit: {limit}")
                logger.debug(f"Query vector length: {len(query_vector) if query_vector else 0}")
                
                # qdrant-client >= 1.0 API
                search_result = self.qdrant_client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=limit,
                    query_filter=qdrant_filter,
                    with_payload=True
                )
                
                logger.debug(f"search_result type: {type(search_result)}")
                logger.debug(f"search_result repr: {repr(search_result)[:500]}")
                
                # 兼容对象和字典格式的响应
                if hasattr(search_result, 'points'):
                    results = search_result.points
                    logger.debug(f"Using object.points, results type: {type(results)}")
                elif isinstance(search_result, dict) and 'points' in search_result:
                    results = search_result['points']
                    logger.debug(f"Using dict['points'], results type: {type(results)}")
                elif isinstance(search_result, dict) and 'result' in search_result:
                    # 某些API版本可能返回 {'result': [...]}
                    results = search_result['result']
                    logger.debug(f"Using dict['result'], results type: {type(results)}")
                elif isinstance(search_result, dict) and 'status' in search_result:
                    # 错误响应格式
                    logger.error(f"Qdrant returned error response: {search_result}")
                    results = []
                else:
                    logger.error(f"Unexpected search result format: {type(search_result)} - {repr(search_result)[:300]}")
                    results = []
                    
            except AttributeError as e:
                logger.error(f"Search failed with AttributeError: {str(e)}")
                logger.error(f"Error type: {type(e)}, dir: {dir(e) if hasattr(e, '__dict__') else 'N/A'}")
                # 尝试使用旧版 search API
                try:
                    results = self.qdrant_client.search(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=limit,
                        query_filter=qdrant_filter,
                        with_payload=True
                    )
                    logger.debug(f"Using old search API, results type: {type(results)}")
                except Exception as e2:
                    logger.error(f"Search failed with search API: {str(e2)}")
                    results = []
            except TypeError as e:
                logger.error(f"Search failed with TypeError: {str(e)}")
                logger.error(f"Error args: {e.args}")
                # 尝试使用旧版 search API
                try:
                    results = self.qdrant_client.search(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=limit,
                        query_filter=qdrant_filter,
                        with_payload=True
                    )
                    logger.debug(f"Using old search API, results type: {type(results)}")
                except Exception as e2:
                    logger.error(f"Search failed with search API: {str(e2)}")
                    results = []
            except Exception as e:
                logger.error(f"Search failed with unexpected exception: {str(e)}")
                logger.error(f"Exception type: {type(e)}")
                logger.error(f"Exception args: {e.args}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                results = []

            # 转换结果格式
            search_results = []
            for result in results:
                # 安全获取 payload
                try:
                    if hasattr(result, 'payload'):
                        payload = result.payload
                    elif isinstance(result, dict) and 'payload' in result:
                        payload = result['payload']
                    else:
                        payload = {}
                except Exception as e:
                    logger.error(f"Error getting payload: {str(e)}")
                    payload = {}
                
                # 确保 payload 是字典
                if not isinstance(payload, dict):
                    logger.error(f"Payload is not a dict: {type(payload)} - {payload}")
                    payload = {}
                
                # 安全获取 score
                try:
                    if hasattr(result, 'score'):
                        score = result.score
                    elif isinstance(result, dict) and 'score' in result:
                        score = result['score']
                    else:
                        score = 0.0
                    # 确保 score 是数值
                    if not isinstance(score, (int, float)):
                        score = float(score) if score else 0.0
                except Exception as e:
                    logger.error(f"Error getting score: {str(e)}")
                    score = 0.0
                
                search_results.append({
                    "id": result.id if hasattr(result, 'id') else result.get('id', ''),
                    "content": payload.get("content", ""),
                    "file_name": payload.get("file_name", ""),
                    "file_path": payload.get("file_path", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "total_chunks": payload.get("total_chunks", 1),
                    "update_time": payload.get("update_time", ""),
                    "score": score
                })

            logger.debug(f"Search returned {len(search_results)} results")

            return search_results

        except Exception as e:
            logger.error(f"Error searching vectors: {str(e)}", exc_info=True)
            return []

    async def delete_by_file(self, file_name: str) -> int:
        """
        删除指定文件的所有向量

        Args:
            file_name: 文件名

        Returns:
            删除的向量数量
        """
        if not self.qdrant_client:
            return 0

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            qdrant_filter = Filter(
                must=[
                    FieldCondition(key="file_name", match=MatchValue(value=file_name))
                ]
            )

            result = self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=qdrant_filter,
                wait=True
            )

            deleted_count = result.deleted_count if hasattr(result, 'deleted_count') else 0
            logger.info(f"Deleted {deleted_count} vectors for file '{file_name}'")

            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting vectors by file: {str(e)}", exc_info=True)
            return 0

    async def clear_collection(self) -> Dict[str, Any]:
        """清空整个集合"""
        if not self.qdrant_client:
            return {"status": "failed", "error": "Qdrant client not initialized"}

        try:
            # 获取当前向量数量
            stats = self.get_collection_stats()
            vectors_before = stats.get("vector_count", 0)

            # 删除并重建集合 - 这是清空所有向量的最可靠方法
            collection_name = self.collection_name
            from qdrant_client.http.models import VectorParams
            vectors_config = VectorParams(size=self.vector_size, distance="Cosine")

            # 删除旧集合
            self.qdrant_client.delete_collection(collection_name=collection_name)

            # 重建集合
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config
            )

            logger.info(f"Cleared and recreated collection '{collection_name}'")

            return {
                "status": "success",
                "deleted_count": vectors_before
            }

        except Exception as e:
            logger.error(f"Error clearing collection: {str(e)}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        if not self.qdrant_client:
            return {
                "vector_count": 0,
                "status": "Qdrant client not initialized"
            }

        try:
            info = self.qdrant_client.get_collection(collection_name=self.collection_name)

            # 兼容新旧版本的 Qdrant API
            # 优先使用 points_count 作为 vector_count
            vector_count = getattr(info, 'points_count', 0)
            if vector_count == 0:
                vector_count = getattr(info, 'vectors_count', 0)
            if vector_count == 0:
                vector_count = getattr(info, 'total_vectors', 0)
            if vector_count == 0:
                vector_count = getattr(info, 'total_points', 0)

            status = info.status.value if hasattr(info, 'status') and info.status else "unknown"
            created_at = str(info.created_at) if hasattr(info, 'created_at') and info.created_at else None

            return {
                "vector_count": vector_count,
                "status": status,
                "created_at": created_at
            }

        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}", exc_info=True)
            return {
                "vector_count": 0,
                "status": str(e)
            }

    async def update_vectors(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        更新文档向量（先删除再插入）

        Args:
            documents: 文档列表

        Returns:
            更新结果
        """
        if not documents:
            return {"status": "success", "updated_count": 0}

        # 获取所有涉及的文件
        file_names = set(doc.get("file_name") for doc in documents if doc.get("file_name"))

        # 删除这些文件的旧向量
        deleted_count = 0
        for file_name in file_names:
            deleted_count += await self.delete_by_file(file_name)

        # 插入新向量
        result = await self.store_vectors(documents)

        if result.get("status") == "success":
            result["updated_count"] = result.get("stored_count", 0)
            result["deleted_count"] = deleted_count

        return result