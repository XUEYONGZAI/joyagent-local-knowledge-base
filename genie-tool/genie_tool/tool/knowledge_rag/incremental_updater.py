# -*- coding: utf-8 -*-
# =====================
#
#
# Author: your_name
# Date:   YYYY/MM/DD
# =====================
import os
import asyncio
import time
from typing import List, Dict, Any, Optional

from genie_tool.util.log_util import logger


class IncrementalUpdater:
    """增量更新器"""

    def __init__(
        self,
        vector_store=None,
        update_strategy: str = None,
        full_update_interval_days: int = None
    ):
        from genie_tool.tool.knowledge_rag.vector_store import VectorStore

        self.vector_store = vector_store or VectorStore(request_id="incremental_updater")

        self.update_strategy = update_strategy or os.getenv("KNOWLEDGE_RAG_UPDATE_STRATEGY", "mixed")
        self.full_update_interval = full_update_interval_days or int(os.getenv("KNOWLEDGE_RAG_FULL_UPDATE_INTERVAL", "24"))

        self._last_update_file = os.path.join(
            os.path.dirname(__file__),
            ".last_full_update"
        )
        self.last_full_update = self._load_last_update_time()

        self._chunk_count = 0
        self._last_update_timestamp = None

    def _load_last_update_time(self) -> Optional[float]:
        """从文件加载上次全量更新时间"""
        try:
            if os.path.exists(self._last_update_file):
                with open(self._last_update_file, 'r') as f:
                    return float(f.read().strip())
        except Exception as e:
            logger.warning(f"Failed to load last update time: {str(e)}")
        return None

    def _save_last_update_time(self):
        """保存上次全量更新时间到文件"""
        try:
            with open(self._last_update_file, 'w') as f:
                f.write(str(time.time()))
        except Exception as e:
            logger.warning(f"Failed to save last update time: {str(e)}")

    def get_chunk_count(self) -> int:
        """获取当前chunk数量"""
        try:
            stats = self.vector_store.get_collection_stats()
            self._chunk_count = stats.get("vector_count", 0)
            return self._chunk_count
        except Exception as e:
            logger.warning(f"Failed to get chunk count: {str(e)}")
            return self._chunk_count

    def get_last_update_time(self) -> Optional[str]:
        """获取最后更新时间"""
        if self._last_update_timestamp:
            return self._last_update_timestamp

        if self.last_full_update:
            self._last_update_timestamp = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(self.last_full_update)
            )
            return self._last_update_timestamp

        stats = self.vector_store.get_collection_stats()
        created_at = stats.get("created_at")
        if created_at:
            self._last_update_timestamp = created_at
            return created_at

        return None

    async def clear_all(self) -> Dict[str, Any]:
        """清空所有数据"""
        try:
            result = await self.vector_store.clear_collection()
            self._chunk_count = 0
            self._last_update_timestamp = None

            return {
                "status": "success",
                "message": "All knowledge base data cleared",
                "cleared_chunks": result.get("deleted_count", 0)
            }
        except Exception as e:
            logger.error(f"Failed to clear knowledge base: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e)
            }

    async def check_and_update(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        检查并执行更新

        Args:
            file_paths: 文件路径列表

        Returns:
            更新结果
        """
        if self.update_strategy == "full":
            return await self.full_update(file_paths)
        elif self.update_strategy == "incremental":
            return await self.incremental_update(file_paths)
        else:
            return await self.mixed_update(file_paths)

    async def full_update(self, file_paths: List[str]) -> Dict[str, Any]:
        """全量更新"""
        logger.info("=== Starting full update ===")

        try:
            stats_before = self.vector_store.get_collection_stats()
            vectors_before = stats_before.get("vector_count", 0)
            logger.info(f"Vector count before full update: {vectors_before}")

            await self.vector_store.clear_collection()
            logger.info("Collection cleared")

            total_stored = 0
            success_count = 0
            failed_count = 0
            errors = []

            if file_paths:
                from genie_tool.tool.knowledge_rag.file_processor import FileProcessor
                from genie_tool.tool.knowledge_rag.knowledge_rag import KnowledgeRAGAgent

                processor = FileProcessor()

                for file_path in file_paths:
                    try:
                        result = await processor.process_file(file_path)
                        if result.get("status") == "success" and result.get("content"):
                            agent = KnowledgeRAGAgent("update", "")
                            chunks = agent._chunk_text(result["content"])

                            file_mtime = str(os.path.getmtime(file_path))
                            documents = []
                            for i, chunk in enumerate(chunks):
                                documents.append({
                                    "id": f"{result['file_path']}_{i}",
                                    "content": chunk,
                                    "file_name": result["file_name"],
                                    "file_path": result["file_path"],
                                    "chunk_index": i,
                                    "total_chunks": len(chunks),
                                    "update_time": file_mtime
                                })

                            if documents:
                                await self.vector_store.store_vectors(documents)
                                total_stored += len(documents)
                            success_count += 1
                        else:
                            failed_count += 1
                            errors.append(f"Failed to process: {result.get('file_name')}")
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"Error processing {file_path}: {str(e)}")
                        logger.warning(f"Failed to process file: {file_path}, error: {str(e)}")

            self.last_full_update = time.time()
            self._save_last_update_time()
            self._last_update_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            stats_after = self.vector_store.get_collection_stats()
            vectors_after = stats_after.get("vector_count", 0)
            self._chunk_count = vectors_after

            return {
                "status": "success",
                "update_type": "full",
                "processed_files": success_count,
                "failed_files": failed_count,
                "total_chunks": total_stored,
                "updated_chunks": total_stored,
                "skipped_chunks": 0,
                "vectors_before": vectors_before,
                "vectors_after": vectors_after,
                "errors": errors,
                "message": f"Full update completed. {success_count} files processed, {total_stored} chunks stored."
            }

        except Exception as e:
            logger.error(f"Error during full update: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "update_type": "full",
                "error": str(e),
                "message": f"Full update failed: {str(e)}"
            }

    async def incremental_update(self, file_paths: List[str]) -> Dict[str, Any]:
        """增量更新"""
        logger.info("=== Starting incremental update ===")

        try:
            updated_count = 0
            added_count = 0
            deleted_count = 0
            skipped_count = 0
            errors = []

            if file_paths:
                from genie_tool.tool.knowledge_rag.file_processor import FileProcessor
                from genie_tool.tool.knowledge_rag.knowledge_rag import KnowledgeRAGAgent

                processor = FileProcessor()

                for file_path in file_paths:
                    try:
                        if not os.path.exists(file_path):
                            file_name = os.path.basename(file_path)
                            deleted = await self.vector_store.delete_by_file(file_name)
                            deleted_count += deleted
                            logger.info(f"Deleted {deleted} vectors for missing file: {file_name}")
                            continue

                        file_name = os.path.basename(file_path)
                        file_mtime = os.path.getmtime(file_path)

                        existing_vectors = await self.vector_store.search_vectors(
                            query="",
                            limit=1,
                            filters={"file_name": file_name}
                        )

                        need_update = True
                        if existing_vectors:
                            existing_mtime = existing_vectors[0].get("update_time", "0")
                            try:
                                if float(existing_mtime) >= file_mtime:
                                    need_update = False
                                    skipped_count += 1
                                    logger.debug(f"Skipping unchanged file: {file_name}")
                            except ValueError:
                                need_update = True

                        if need_update:
                            deleted = await self.vector_store.delete_by_file(file_name)

                            result = await processor.process_file(file_path)
                            if result.get("status") == "success" and result.get("content"):
                                agent = KnowledgeRAGAgent("update", "")
                                chunks = agent._chunk_text(result["content"])

                                documents = []
                                for i, chunk in enumerate(chunks):
                                    documents.append({
                                        "id": f"{file_path}_{i}",
                                        "content": chunk,
                                        "file_name": result["file_name"],
                                        "file_path": result["file_path"],
                                        "chunk_index": i,
                                        "total_chunks": len(chunks),
                                        "update_time": str(file_mtime)
                                    })

                                await self.vector_store.store_vectors(documents)

                                if deleted > 0:
                                    updated_count += 1
                                else:
                                    added_count += 1
                                logger.info(f"{'Updated' if deleted > 0 else 'Added'} file: {file_name}")
                    except Exception as e:
                        errors.append(f"Error processing {file_path}: {str(e)}")
                        logger.warning(f"Error processing file: {file_path}, error: {str(e)}")

            self._last_update_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self._chunk_count = self.get_chunk_count()

            return {
                "status": "success",
                "update_type": "incremental",
                "added_count": added_count,
                "updated_count": updated_count,
                "deleted_count": deleted_count,
                "skipped_count": skipped_count,
                "processed_files": added_count + updated_count,
                "total_chunks": self._chunk_count,
                "errors": errors,
                "message": f"Incremental update completed. {added_count} added, {updated_count} updated, {deleted_count} deleted, {skipped_count} skipped."
            }

        except Exception as e:
            logger.error(f"Error during incremental update: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "update_type": "incremental",
                "error": str(e),
                "message": f"Incremental update failed: {str(e)}"
            }

    async def mixed_update(self, file_paths: List[str]) -> Dict[str, Any]:
        """混合更新策略"""
        now = time.time()

        if self.last_full_update is None or \
           (now - self.last_full_update) / 3600 >= self.full_update_interval * 24:
            result = await self.full_update(file_paths)
            self.last_full_update = now
            return result
        else:
            return await self.incremental_update(file_paths)

    async def update_by_file(self, file_path: str) -> Dict[str, Any]:
        """更新单个文件"""
        if not file_path or not os.path.exists(file_path):
            return {"status": "failed", "error": "Invalid file path"}

        try:
            file_name = os.path.basename(file_path)
            file_mtime = os.path.getmtime(file_path)

            deleted = await self.vector_store.delete_by_file(file_name)

            from genie_tool.tool.knowledge_rag.file_processor import FileProcessor
            processor = FileProcessor()
            result = await processor.process_file(file_path)

            if result.get("status") == "success" and result.get("content"):
                documents = [{
                    "id": file_path,
                    "content": result["content"],
                    "file_name": result["file_name"],
                    "file_path": result["file_path"],
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "update_time": str(file_mtime)
                }]

                await self.vector_store.store_vectors(documents)

                return {
                    "status": "success",
                    "file_name": file_name,
                    "deleted_vectors": deleted,
                    "stored_vectors": 1
                }
            else:
                return {
                    "status": "failed",
                    "file_name": file_name,
                    "error": result.get("error", "Failed to process file")
                }

        except Exception as e:
            logger.error(f"Error updating file {file_path}: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "file_name": os.path.basename(file_path),
                "error": str(e)
            }

    async def delete_file(self, file_name: str) -> Dict[str, Any]:
        """删除指定文件的所有向量"""
        try:
            deleted_count = await self.vector_store.delete_by_file(file_name)
            self._chunk_count = self.get_chunk_count()

            return {
                "status": "success",
                "file_name": file_name,
                "deleted_count": deleted_count
            }

        except Exception as e:
            logger.error(f"Error deleting file {file_name}: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "file_name": file_name,
                "error": str(e)
            }