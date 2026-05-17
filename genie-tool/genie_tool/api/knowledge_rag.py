# -*- coding: utf-8 -*-
import os
import asyncio
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from genie_tool.tool.knowledge_rag import FileProcessor, KnowledgeRAGAgent, IncrementalUpdater
from genie_tool.util.log_util import logger

router = APIRouter()

FILE_STORAGE_PATH = os.getenv("KNOWLEDGE_RAG_FILE_PATH", str(Path(__file__).parent.parent.parent / "knowledge_files"))

os.makedirs(FILE_STORAGE_PATH, exist_ok=True)

_uploaded_files: Dict[str, Dict[str, Any]] = {}

_agent_cache: Dict[str, KnowledgeRAGAgent] = {}

_updater: Optional[IncrementalUpdater] = None


def get_updater() -> IncrementalUpdater:
    global _updater
    if _updater is None:
        _updater = IncrementalUpdater(
            update_strategy="mixed",
            full_update_interval_days=7
        )
    return _updater


class QueryRequest(BaseModel):
    """查询请求模型"""
    task: str
    filePaths: Optional[List[str]] = None
    requestId: Optional[str] = None


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(FILE_STORAGE_PATH, file.filename)

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        file_id = str(uuid.uuid4())
        file_info = {
            "file_id": file_id,
            "file_name": file.filename,
            "file_path": file_path,
            "file_size": len(content),
            "upload_time": str(asyncio.get_event_loop().time())
        }
        _uploaded_files[file_id] = file_info

        logger.info(f"文件上传成功: {file.filename}, 大小: {len(content)} bytes")

        # 将文件内容处理并存储到向量数据库
        try:
            updater = get_updater()
            result = await updater.check_and_update([file_path])
            logger.info(f"文件向量存储结果: {result}")
        except Exception as e:
            logger.error(f"文件向量存储失败: {str(e)}", exc_info=True)
            # 存储失败不影响上传，继续返回成功
            pass

        return JSONResponse(content={
            "code": 200,
            "message": "上传成功",
            "data": {
                "fileId": file_id,
                "fileName": file.filename,
                "filePath": file_path,
                "fileSize": len(content)
            }
        })

    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.delete("/file")
async def delete_file(file_path: str = None, file_id: str = None):
    try:
        target_path = None

        if file_id and file_id in _uploaded_files:
            target_path = _uploaded_files[file_id]["file_path"]
            del _uploaded_files[file_id]
        elif file_path:
            target_path = file_path
            for fid, finfo in list(_uploaded_files.items()):
                if finfo["file_path"] == target_path:
                    del _uploaded_files[fid]
                    break

        if target_path and os.path.exists(target_path):
            os.remove(target_path)
            logger.info(f"文件删除成功: {target_path}")

        return JSONResponse(content={
            "code": 200,
            "message": "删除成功"
        })

    except Exception as e:
        logger.error(f"文件删除失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")


@router.delete("/clear")
async def clear_knowledge_base():
    try:
        cleared_count = 0

        for file_id, file_info in list(_uploaded_files.items()):
            if os.path.exists(file_info["file_path"]):
                os.remove(file_info["file_path"])
                cleared_count += 1

        _uploaded_files.clear()

        _agent_cache.clear()

        updater = get_updater()
        await updater.clear_all()

        logger.info(f"知识库已清空，共删除 {cleared_count} 个文件")

        return JSONResponse(content={
            "code": 200,
            "message": f"知识库已清空，共删除 {cleared_count} 个文件",
            "data": {
                "clearedFiles": cleared_count
            }
        })

    except Exception as e:
        logger.error(f"清空知识库失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"清空知识库失败: {str(e)}")


@router.post("/sync")
async def sync_knowledge_base():
    try:
        updater = get_updater()

        file_paths = [f["file_path"] for f in _uploaded_files.values()]

        if not file_paths:
            return JSONResponse(content={
                "code": 200,
                "message": "没有文件需要同步",
                "data": {
                    "processedFiles": 0,
                    "totalChunks": 0
                }
            })

        result = await updater.check_and_update(file_paths)

        logger.info(f"知识库同步完成: {result}")

        return JSONResponse(content={
            "code": 200,
            "message": "同步完成",
            "data": {
                "processedFiles": result.get("processed_files", len(file_paths)),
                "totalChunks": result.get("total_chunks", 0),
                "updatedChunks": result.get("updated_chunks", 0),
                "skippedChunks": result.get("skipped_chunks", 0),
                "errors": result.get("errors", [])
            }
        })

    except Exception as e:
        logger.error(f"同步知识库失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"同步知识库失败: {str(e)}")


@router.get("/stats")
async def get_stats():
    try:
        updater = get_updater()

        total_files = len(_uploaded_files)
        total_chunks = updater.get_chunk_count()
        last_update = updater.get_last_update_time()

        return JSONResponse(content={
            "code": 200,
            "data": {
                "totalFiles": total_files,
                "totalChunks": total_chunks,
                "lastUpdate": last_update
            }
        })

    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/files")
async def list_files():
    try:
        files = []
        for file_id, file_info in _uploaded_files.items():
            files.append({
                "fileId": file_id,
                "fileName": file_info["file_name"],
                "fileSize": file_info["file_size"],
                "uploadTime": file_info["upload_time"]
            })

        return JSONResponse(content={
            "code": 200,
            "data": {
                "files": files,
                "total": len(files)
            }
        })

    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")


@router.post("/process_files")
async def process_files(file_ids: List[str] = None):
    try:
        processor = FileProcessor()

        if file_ids:
            file_paths = []
            for fid in file_ids:
                if fid in _uploaded_files:
                    file_paths.append(_uploaded_files[fid]["file_path"])
        else:
            file_paths = [f["file_path"] for f in _uploaded_files.values()]

        if not file_paths:
            return JSONResponse(content={
                "code": 200,
                "message": "没有文件需要处理",
                "data": {
                    "processed": 0,
                    "failed": 0
                }
            })

        results = await processor.process_files_batch(file_paths)

        processed = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - processed

        logger.info(f"文件处理完成: 成功 {processed}, 失败 {failed}")

        return JSONResponse(content={
            "code": 200,
            "message": "处理完成",
            "data": {
                "processed": processed,
                "failed": failed,
                "results": results
            }
        })

    except Exception as e:
        logger.error(f"处理文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理文件失败: {str(e)}")


@router.post("/query")
async def query_knowledge(request: QueryRequest = Body(...)):
    try:
        request_id = request.requestId or str(uuid.uuid4())

        file_list = request.filePaths or []

        agent = KnowledgeRAGAgent(
            request_id=request_id,
            query=request.task,
            file_paths=file_list
        )

        _agent_cache[request_id] = agent

        result = await agent.run()

        if request_id in _agent_cache:
            del _agent_cache[request_id]

        return JSONResponse(content={
            "code": 200,
            "data": result.get("answer", ""),
            "requestId": request_id,
            "retrievalResults": result.get("retrieval_contexts", [])
        })

    except Exception as e:
        logger.error(f"查询失败: {str(e)}", exc_info=True)
        if request.requestId and request.requestId in _agent_cache:
            del _agent_cache[request.requestId]
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/query_stream")
async def query_knowledge_stream(request: QueryRequest = Body(...)):
    from fastapi.responses import StreamingResponse
    import json

    async def generate():
        try:
            request_id = request.requestId or str(uuid.uuid4())

            file_list = request.filePaths or []

            agent = KnowledgeRAGAgent(
                request_id=request_id,
                query=request.task,
                file_paths=file_list
            )

            _agent_cache[request_id] = agent

            async for chunk in agent.generate_answer_stream():
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            if request_id in _agent_cache:
                del _agent_cache[request_id]

            yield f"data: {json.dumps({'isFinal': True}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"流式查询失败: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )