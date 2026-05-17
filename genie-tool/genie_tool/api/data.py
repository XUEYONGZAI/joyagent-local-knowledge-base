# -*- coding: utf-8 -*-
import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/allModels")
async def get_all_models():
    """
    获取所有可用的模型列表
    """
    try:
        # 返回一个空列表作为占位符
        # 实际实现应该从配置或数据库中获取模型列表
        models = []
        
        return JSONResponse(content=models)
    
    except Exception as e:
        return JSONResponse(content=[], status_code=200)