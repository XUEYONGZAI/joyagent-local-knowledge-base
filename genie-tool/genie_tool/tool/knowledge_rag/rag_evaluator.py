# -*- coding: utf-8 -*-
"""
RAG系统召回率评估模块
基于Chunk级别的评估指标，确保与底层向量存储的分块结构一致
"""
import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from uuid import uuid4

from genie_tool.util.log_util import logger
from genie_tool.tool.knowledge_rag.knowledge_rag import KnowledgeRAGAgent
from genie_tool.tool.knowledge_rag.file_processor import FileProcessor


class TestSample:
    """测试样本数据模型"""
    
    def __init__(
        self,
        query: str,
        expected_chunk_ids: List[str],
        doc_name: str = None,
        context: str = None
    ):
        """
        Args:
            query: 用户查询
            expected_chunk_ids: 期望被检索到的chunk ID列表（标注的相关chunk）
            doc_name: 关联的文档名称
            context: 查询上下文描述
        """
        self.query = query
        self.expected_chunk_ids = expected_chunk_ids
        self.doc_name = doc_name
        self.context = context
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "expected_chunk_ids": self.expected_chunk_ids,
            "doc_name": self.doc_name,
            "context": self.context
        }


class EvaluationResult:
    """评估结果数据模型"""
    
    def __init__(self):
        self.tp = 0  # True Positive: 被正确检索到的相关chunk数
        self.fn = 0  # False Negative: 未被检索到的相关chunk数
        self.fp = 0  # False Positive: 被错误检索到的非相关chunk数
        self.total_retrieved = 0  # 实际检索到的chunk数
        self.total_expected = 0  # 期望检索到的chunk数
        self.recall = 0.0  # 召回率 = TP / (TP + FN)
        self.precision = 0.0  # 精确率 = TP / (TP + FP)
        self.f1 = 0.0  # F1分数 = 2 * P * R / (P + R)
    
    def compute_metrics(self):
        """计算评估指标"""
        # 召回率 = 被正确检索的相关chunk数 / 总相关chunk数
        if self.total_expected > 0:
            self.recall = self.tp / self.total_expected
        
        # 精确率 = 被正确检索的相关chunk数 / 实际检索到的chunk数
        if self.total_retrieved > 0:
            self.precision = self.tp / self.total_retrieved
        
        # F1分数
        if self.precision + self.recall > 0:
            self.f1 = 2 * self.precision * self.recall / (self.precision + self.recall)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tp": self.tp,
            "fn": self.fn,
            "fp": self.fp,
            "total_retrieved": self.total_retrieved,
            "total_expected": self.total_expected,
            "recall": round(self.recall, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4)
        }


class RAGEvaluator:
    """RAG系统评估器"""
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        top_k: int = 5,
        max_context_length: int = 3000
    ):
        """
        Args:
            chunk_size: 文本分块大小
            chunk_overlap: 分块重叠大小
            top_k: 检索返回数量
            max_context_length: 最大上下文长度
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.max_context_length = max_context_length
        
        # 评估结果
        self.results: List[Dict[str, Any]] = []
        self.overall_result = EvaluationResult()
        
        # 测试数据集
        self.test_samples: List[TestSample] = []
        
        # 参数记录
        self.parameters = {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "top_k": top_k,
            "max_context_length": max_context_length,
            "evaluation_time": None,
            "total_samples": 0
        }
    
    def load_test_dataset(self, dataset_path: str) -> bool:
        """
        加载测试数据集
        
        Args:
            dataset_path: 测试数据集文件路径（JSON格式）
            
        Returns:
            是否加载成功
        """
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.test_samples = []
            for item in data.get("samples", []):
                sample = TestSample(
                    query=item.get("query", ""),
                    expected_chunk_ids=item.get("expected_chunk_ids", []),
                    doc_name=item.get("doc_name", None),
                    context=item.get("context", None)
                )
                self.test_samples.append(sample)
            
            self.parameters["total_samples"] = len(self.test_samples)
            logger.info(f"Loaded {len(self.test_samples)} test samples from {dataset_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load test dataset: {str(e)}")
            return False
    
    def create_test_dataset(
        self,
        file_paths: List[str],
        queries_with_expected: List[Dict[str, Any]]
    ) -> bool:
        """
        创建测试数据集并自动生成chunk标注
        
        Args:
            file_paths: 测试文档路径列表
            queries_with_expected: 查询与期望结果列表
            
        Returns:
            是否创建成功
        """
        try:
            # 处理文档并生成chunk
            processor = FileProcessor()
            results = asyncio.run(processor.process_files_batch(file_paths))
            
            # 创建RAG代理用于分块
            agent = KnowledgeRAGAgent("evaluation", "")
            
            # 存储所有chunk的映射关系
            all_chunks = []
            doc_chunk_map = {}
            
            for result in results:
                if result.get("status") == "success" and result.get("content"):
                    chunks = agent._chunk_text(result["content"])
                    file_name = result["file_name"]
                    
                    for i, chunk in enumerate(chunks):
                        chunk_id = f"{file_name}_{i}"
                        all_chunks.append({
                            "chunk_id": chunk_id,
                            "file_name": file_name,
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "content": chunk[:100] + "..." if len(chunk) > 100 else chunk
                        })
                    
                    doc_chunk_map[file_name] = [f"{file_name}_{i}" for i in range(len(chunks))]
            
            # 创建测试样本
            self.test_samples = []
            for item in queries_with_expected:
                query = item.get("query", "")
                doc_name = item.get("doc_name", "")
                
                # 根据文档名获取期望的chunk IDs
                expected_chunk_ids = doc_chunk_map.get(doc_name, [])
                
                sample = TestSample(
                    query=query,
                    expected_chunk_ids=expected_chunk_ids,
                    doc_name=doc_name,
                    context=item.get("context", "")
                )
                self.test_samples.append(sample)
            
            self.parameters["total_samples"] = len(self.test_samples)
            logger.info(f"Created {len(self.test_samples)} test samples")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create test dataset: {str(e)}", exc_info=True)
            return False
    
    async def evaluate_single_sample(self, sample: TestSample) -> Dict[str, Any]:
        """
        评估单个测试样本
        
        Args:
            sample: 测试样本
            
        Returns:
            评估结果字典
        """
        result = {
            "query": sample.query,
            "doc_name": sample.doc_name,
            "context": sample.context,
            "expected_chunk_ids": sample.expected_chunk_ids,
            "retrieved_chunk_ids": [],
            "retrieved_chunks": [],
            "tp": 0,
            "fn": 0,
            "fp": 0,
            "recall": 0.0,
            "precision": 0.0,
            "f1": 0.0
        }
        
        try:
            # 创建RAG代理执行检索
            agent = KnowledgeRAGAgent(
                request_id=f"eval_{uuid4()}",
                query=sample.query
            )
            
            # 设置评估参数
            agent.top_k = self.top_k
            
            # 执行检索
            retrieved_chunks = await agent.retrieve_relevant_context()
            
            # 提取检索到的chunk IDs
            retrieved_chunk_ids = []
            for chunk in retrieved_chunks:
                chunk_id = f"{chunk.get('file_name', '')}_{chunk.get('chunk_index', 0)}"
                retrieved_chunk_ids.append(chunk_id)
            
            result["retrieved_chunk_ids"] = retrieved_chunk_ids
            result["retrieved_chunks"] = retrieved_chunks
            
            # 计算TP, FN, FP
            expected_set = set(sample.expected_chunk_ids)
            retrieved_set = set(retrieved_chunk_ids)
            
            tp = len(expected_set & retrieved_set)  # True Positive
            fn = len(expected_set - retrieved_set)  # False Negative
            fp = len(retrieved_set - expected_set)  # False Positive
            
            result["tp"] = tp
            result["fn"] = fn
            result["fp"] = fp
            
            # 计算指标
            total_expected = len(expected_set)
            total_retrieved = len(retrieved_set)
            
            recall = tp / total_expected if total_expected > 0 else 0.0
            precision = tp / total_retrieved if total_retrieved > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            result["recall"] = round(recall, 4)
            result["precision"] = round(precision, 4)
            result["f1"] = round(f1, 4)
            
            logger.debug(f"Query: '{sample.query[:30]}...' - TP:{tp}, FN:{fn}, FP:{fp}, Recall:{recall:.4f}")
            
        except Exception as e:
            logger.error(f"Error evaluating sample: {str(e)}", exc_info=True)
            result["error"] = str(e)
        
        return result
    
    async def run_evaluation(self) -> EvaluationResult:
        """
        执行完整的评估流程
        
        Returns:
            总体评估结果
        """
        logger.info("=== Starting RAG Evaluation ===")
        self.parameters["evaluation_time"] = datetime.now().isoformat()
        
        # 初始化总体结果
        overall = EvaluationResult()
        
        # 逐个评估测试样本
        for i, sample in enumerate(self.test_samples, 1):
            logger.info(f"Evaluating sample {i}/{len(self.test_samples)}")
            
            result = await self.evaluate_single_sample(sample)
            self.results.append(result)
            
            # 累加统计
            overall.tp += result.get("tp", 0)
            overall.fn += result.get("fn", 0)
            overall.fp += result.get("fp", 0)
            overall.total_expected += len(sample.expected_chunk_ids)
            overall.total_retrieved += len(result.get("retrieved_chunk_ids", []))
        
        # 计算总体指标
        overall.compute_metrics()
        self.overall_result = overall
        
        logger.info(f"=== Evaluation Completed ===")
        logger.info(f"Overall Recall: {overall.recall:.4f}")
        logger.info(f"Overall Precision: {overall.precision:.4f}")
        logger.info(f"Overall F1: {overall.f1:.4f}")
        
        return overall
    
    def generate_report(self, output_path: str = None) -> str:
        """
        生成评估报告
        
        Args:
            output_path: 报告输出路径（可选）
            
        Returns:
            报告内容字符串
        """
        report = []
        
        # 报告标题
        report.append("=" * 80)
        report.append("          RAG系统召回率评估报告")
        report.append("=" * 80)
        report.append("")
        
        # 一、评估概述
        report.append("一、评估概述")
        report.append("-" * 40)
        report.append(f"评估时间: {self.parameters.get('evaluation_time', 'N/A')}")
        report.append(f"测试样本数: {self.parameters.get('total_samples', 0)}")
        report.append("")
        
        # 二、参数设置
        report.append("二、参数设置")
        report.append("-" * 40)
        report.append(f"  - Chunk大小: {self.parameters.get('chunk_size', 500)}")
        report.append(f"  - Chunk重叠: {self.parameters.get('chunk_overlap', 50)}")
        report.append(f"  - 检索数量(top_k): {self.parameters.get('top_k', 5)}")
        report.append(f"  - 最大上下文长度: {self.parameters.get('max_context_length', 3000)}")
        report.append("")
        
        # 三、数据集特征
        report.append("三、数据集特征")
        report.append("-" * 40)
        doc_names = set(s.doc_name for s in self.test_samples if s.doc_name)
        report.append(f"  - 测试文档数: {len(doc_names)}")
        report.append(f"  - 测试查询数: {len(self.test_samples)}")
        
        total_expected_chunks = sum(len(s.expected_chunk_ids) for s in self.test_samples)
        avg_expected_per_query = total_expected_chunks / len(self.test_samples) if self.test_samples else 0
        report.append(f"  - 标注的相关Chunk总数: {total_expected_chunks}")
        report.append(f"  - 平均每查询相关Chunk数: {avg_expected_per_query:.2f}")
        report.append("")
        
        # 四、总体评估结果
        report.append("四、总体评估结果")
        report.append("-" * 40)
        o = self.overall_result
        report.append(f"  - 真正例(TP): {o.tp}")
        report.append(f"  - 假负例(FN): {o.fn}")
        report.append(f"  - 假正例(FP): {o.fp}")
        report.append("")
        report.append("【指标计算】")
        report.append(f"  - 召回率(Recall) = TP / (TP + FN) = {o.tp} / ({o.tp} + {o.fn}) = {o.recall:.4f}")
        report.append(f"  - 精确率(Precision) = TP / (TP + FP) = {o.tp} / ({o.tp} + {o.fp}) = {o.precision:.4f}")
        report.append(f"  - F1分数 = 2 * P * R / (P + R) = {o.f1:.4f}")
        report.append("")
        
        # 五、逐样本详细结果
        report.append("五、逐样本详细结果")
        report.append("-" * 40)
        
        for i, result in enumerate(self.results, 1):
            report.append(f"\n样本 {i}:")
            report.append(f"  查询: {result.get('query', '')}")
            report.append(f"  文档: {result.get('doc_name', 'N/A')}")
            report.append(f"  期望Chunk数: {len(result.get('expected_chunk_ids', []))}")
            report.append(f"  检索Chunk数: {len(result.get('retrieved_chunk_ids', []))}")
            report.append(f"  TP/FN/FP: {result.get('tp', 0)}/{result.get('fn', 0)}/{result.get('fp', 0)}")
            report.append(f"  召回率: {result.get('recall', 0):.4f}")
            report.append(f"  精确率: {result.get('precision', 0):.4f}")
            
            if "error" in result:
                report.append(f"  错误: {result['error']}")
        
        report.append("\n" + "=" * 80)
        report.append("          报告结束")
        report.append("=" * 80)
        
        # 六、潜在影响因素分析
        report.append("\n六、潜在影响因素分析")
        report.append("-" * 40)
        report.append("【影响召回率的主要因素】")
        report.append("  1. Chunk大小设置：Chunk过大可能导致信息冗余，过小可能导致上下文断裂")
        report.append("  2. 检索数量(top_k)：设置过小可能遗漏相关Chunk，过大可能引入噪声")
        report.append("  3. Embedding模型质量：模型的语义理解能力直接影响检索准确性")
        report.append("  4. 向量数据库配置：距离度量方式、索引类型等会影响检索效果")
        report.append("  5. 查询表述方式：用户查询的清晰度和准确性影响检索结果")
        report.append("")
        report.append("【改进建议】")
        if self.overall_result.recall < 0.7:
            report.append("  - 建议增大top_k值，确保更多相关Chunk被检索到")
            report.append("  - 检查Embedding模型配置是否正确")
        if self.overall_result.precision < 0.7:
            report.append("  - 建议优化Chunk切分策略，提高Chunk语义完整性")
            report.append("  - 考虑添加相关性阈值过滤")
        
        report_content = "\n".join(report)
        
        # 输出到文件
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                logger.info(f"Evaluation report saved to: {output_path}")
            except Exception as e:
                logger.error(f"Failed to save report: {str(e)}")
        
        return report_content
    
    def run_sync(self) -> EvaluationResult:
        """同步执行评估（用于测试）"""
        return asyncio.run(self.run_evaluation())


# ============== 示例使用 ==============
def create_sample_test_dataset(output_path: str):
    """创建示例测试数据集"""
    dataset = {
        "description": "RAG系统召回率测试数据集",
        "created_at": datetime.now().isoformat(),
        "parameters": {
            "chunk_size": 500,
            "chunk_overlap": 50
        },
        "samples": [
            {
                "query": "什么是RAG技术？",
                "expected_chunk_ids": ["knowledge_base.txt_0", "knowledge_base.txt_1"],
                "doc_name": "knowledge_base.txt",
                "context": "测试RAG基本概念的检索"
            },
            {
                "query": "向量数据库有哪些应用场景？",
                "expected_chunk_ids": ["vector_db_intro.txt_0", "vector_db_intro.txt_2"],
                "doc_name": "vector_db_intro.txt",
                "context": "测试向量数据库相关内容的检索"
            },
            {
                "query": "如何优化检索性能？",
                "expected_chunk_ids": ["optimization_guide.txt_1", "optimization_guide.txt_3"],
                "doc_name": "optimization_guide.txt",
                "context": "测试性能优化相关内容的检索"
            }
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Sample dataset created at: {output_path}")


if __name__ == "__main__":
    # 创建评估器
    evaluator = RAGEvaluator(
        chunk_size=500,
        chunk_overlap=50,
        top_k=5,
        max_context_length=3000
    )
    
    # 加载测试数据集
    # evaluator.load_test_dataset("test_dataset.json")
    
    # 或者创建测试数据集
    # evaluator.create_test_dataset(
    #     file_paths=["/path/to/documents/*.txt"],
    #     queries_with_expected=[
    #         {"query": "问题1", "doc_name": "doc1.txt", "context": "描述"},
    #         {"query": "问题2", "doc_name": "doc2.txt", "context": "描述"},
    #     ]
    # )
    
    # 执行评估
    # result = evaluator.run_sync()
    
    # 生成报告
    # report = evaluator.generate_report("rag_evaluation_report.txt")
    # print(report)