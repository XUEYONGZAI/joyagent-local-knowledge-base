#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG系统召回率计算演示脚本
演示完整的评估流程：数据准备 → 评估执行 → 指标计算 → 报告生成
"""
import os
import sys
import json
import asyncio
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__)))

from genie_tool.tool.knowledge_rag import RAGEvaluator, TestSample, EvaluationResult


def create_demo_test_data():
    """创建演示用的测试数据"""
    print("\n" + "=" * 60)
    print("步骤1: 准备测试数据")
    print("=" * 60)
    
    # 模拟测试样本
    test_samples = [
        TestSample(
            query="什么是RAG技术？",
            expected_chunk_ids=["rag_intro.txt_0", "rag_intro.txt_1"],
            doc_name="rag_intro.txt",
            context="测试RAG基本概念的检索"
        ),
        TestSample(
            query="向量数据库有哪些应用场景？",
            expected_chunk_ids=["vector_db.txt_0", "vector_db.txt_2", "vector_db.txt_3"],
            doc_name="vector_db.txt",
            context="测试向量数据库相关内容的检索"
        ),
        TestSample(
            query="如何优化检索性能？",
            expected_chunk_ids=["optimization.txt_1", "optimization.txt_3"],
            doc_name="optimization.txt",
            context="测试性能优化相关内容的检索"
        ),
        TestSample(
            query="文本分块策略有哪些？",
            expected_chunk_ids=["chunking.txt_0", "chunking.txt_1", "chunking.txt_2"],
            doc_name="chunking.txt",
            context="测试文本分块相关内容的检索"
        ),
        TestSample(
            query="Embedding模型如何选择？",
            expected_chunk_ids=["embedding.txt_0", "embedding.txt_1"],
            doc_name="embedding.txt",
            context="测试Embedding模型相关内容的检索"
        )
    ]
    
    print(f"已创建 {len(test_samples)} 个测试样本")
    for i, sample in enumerate(test_samples, 1):
        print(f"  样本{i}: '{sample.query[:30]}...' → 期望 {len(sample.expected_chunk_ids)} 个相关Chunk")
    
    return test_samples


def simulate_retrieval_results(test_samples):
    """
    模拟检索结果（演示用）
    模拟实际RAG系统的检索行为，包含不同召回情况
    """
    print("\n" + "=" * 60)
    print("步骤2: 执行模拟检索")
    print("=" * 60)
    
    results = []
    
    # 样本1: 完美召回（召回所有相关Chunk）
    results.append({
        "query": test_samples[0].query,
        "expected_chunk_ids": test_samples[0].expected_chunk_ids,
        "retrieved_chunk_ids": ["rag_intro.txt_0", "rag_intro.txt_1"],  # 全部召回
        "doc_name": test_samples[0].doc_name
    })
    
    # 样本2: 部分召回（只召回2个中的3个）
    results.append({
        "query": test_samples[1].query,
        "expected_chunk_ids": test_samples[1].expected_chunk_ids,
        "retrieved_chunk_ids": ["vector_db.txt_0", "vector_db.txt_2", "other_doc.txt_0"],  # 漏1个，多1个无关
        "doc_name": test_samples[1].doc_name
    })
    
    # 样本3: 完全未召回
    results.append({
        "query": test_samples[2].query,
        "expected_chunk_ids": test_samples[2].expected_chunk_ids,
        "retrieved_chunk_ids": ["unrelated_doc.txt_0", "unrelated_doc.txt_1"],  # 完全不相关
        "doc_name": test_samples[2].doc_name
    })
    
    # 样本4: 完全召回但有噪声
    results.append({
        "query": test_samples[3].query,
        "expected_chunk_ids": test_samples[3].expected_chunk_ids,
        "retrieved_chunk_ids": ["chunking.txt_0", "chunking.txt_1", "chunking.txt_2", "noise.txt_0"],  # 全召回+噪声
        "doc_name": test_samples[3].doc_name
    })
    
    # 样本5: 部分召回
    results.append({
        "query": test_samples[4].query,
        "expected_chunk_ids": test_samples[4].expected_chunk_ids,
        "retrieved_chunk_ids": ["embedding.txt_0"],  # 只召回1个
        "doc_name": test_samples[4].doc_name
    })
    
    for i, result in enumerate(results, 1):
        exp = len(result["expected_chunk_ids"])
        ret = len(result["retrieved_chunk_ids"])
        print(f"  样本{i}: 期望={exp}个Chunk, 检索到={ret}个Chunk")
    
    return results


def calculate_metrics(results):
    """
    计算召回率指标
    召回率 = 被正确检索的相关文档数 / 总相关文档数
    """
    print("\n" + "=" * 60)
    print("步骤3: 计算召回率指标")
    print("=" * 60)
    
    overall = EvaluationResult()
    
    print("\n【逐样本计算】")
    print("-" * 40)
    
    for i, result in enumerate(results, 1):
        expected_set = set(result["expected_chunk_ids"])
        retrieved_set = set(result["retrieved_chunk_ids"])
        
        # 计算TP, FN, FP
        tp = len(expected_set & retrieved_set)  # True Positive
        fn = len(expected_set - retrieved_set)  # False Negative
        fp = len(retrieved_set - expected_set)  # False Positive
        
        # 计算指标
        total_expected = len(expected_set)
        total_retrieved = len(retrieved_set)
        
        recall = tp / total_expected if total_expected > 0 else 0.0
        precision = tp / total_retrieved if total_retrieved > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        # 累加总体统计
        overall.tp += tp
        overall.fn += fn
        overall.fp += fp
        overall.total_expected += total_expected
        overall.total_retrieved += total_retrieved
        
        # 输出详细计算过程
        print(f"\n样本{i}:")
        print(f"  查询: {result['query']}")
        print(f"  期望相关Chunk: {expected_set}")
        print(f"  实际检索Chunk: {retrieved_set}")
        print(f"  真正例(TP) = |期望 ∩ 检索| = {tp}")
        print(f"  假负例(FN) = |期望 - 检索| = {fn}")
        print(f"  假正例(FP) = |检索 - 期望| = {fp}")
        print(f"  召回率 = TP / (TP + FN) = {tp} / ({tp} + {fn}) = {recall:.4f}")
        print(f"  精确率 = TP / (TP + FP) = {tp} / ({tp} + {fp}) = {precision:.4f}")
        print(f"  F1分数 = 2 * {precision:.4f} * {recall:.4f} / ({precision:.4f} + {recall:.4f}) = {f1:.4f}")
    
    # 计算总体指标
    overall.compute_metrics()
    
    print("\n" + "-" * 40)
    print("【总体计算】")
    print(f"  总真正例(TP) = {overall.tp}")
    print(f"  总假负例(FN) = {overall.fn}")
    print(f"  总假正例(FP) = {overall.fp}")
    print(f"  总期望相关Chunk数 = {overall.total_expected}")
    print(f"  总检索Chunk数 = {overall.total_retrieved}")
    print(f"\n  总体召回率 = {overall.tp} / ({overall.tp} + {overall.fn}) = {overall.recall:.4f}")
    print(f"  总体精确率 = {overall.tp} / ({overall.tp} + {overall.fp}) = {overall.precision:.4f}")
    print(f"  总体F1分数 = 2 * {overall.precision:.4f} * {overall.recall:.4f} / ({overall.precision:.4f} + {overall.recall:.4f}) = {overall.f1:.4f}")
    
    return overall, results


def generate_report(overall, results, test_samples):
    """生成完整的评估报告"""
    print("\n" + "=" * 60)
    print("步骤4: 生成评估报告")
    print("=" * 60)
    
    report = []
    report.append("=" * 80)
    report.append("          RAG系统召回率评估报告")
    report.append("=" * 80)
    report.append("")
    
    # 评估信息
    report.append("【评估信息】")
    report.append(f"评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"测试样本数: {len(test_samples)}")
    report.append("")
    
    # 参数设置
    report.append("【参数设置】")
    report.append(f"  - Chunk大小: 500")
    report.append(f"  - Chunk重叠: 50")
    report.append(f"  - 检索数量(top_k): 5")
    report.append("")
    
    # 总体指标
    report.append("【总体评估结果】")
    report.append(f"  - 真正例(TP): {overall.tp}")
    report.append(f"  - 假负例(FN): {overall.fn}")
    report.append(f"  - 假正例(FP): {overall.fp}")
    report.append("")
    report.append("【指标计算】")
    report.append(f"  召回率(Recall) = {overall.tp} / ({overall.tp} + {overall.fn}) = {overall.recall:.4f} ({overall.recall * 100:.1f}%)")
    report.append(f"  精确率(Precision) = {overall.tp} / ({overall.tp} + {overall.fp}) = {overall.precision:.4f} ({overall.precision * 100:.1f}%)")
    report.append(f"  F1分数 = 2 * P * R / (P + R) = {overall.f1:.4f}")
    report.append("")
    
    # 逐样本结果
    report.append("【逐样本详细结果】")
    for i, (result, sample) in enumerate(zip(results, test_samples), 1):
        expected_set = set(result["expected_chunk_ids"])
        retrieved_set = set(result["retrieved_chunk_ids"])
        tp = len(expected_set & retrieved_set)
        fn = len(expected_set - retrieved_set)
        fp = len(retrieved_set - expected_set)
        
        recall = tp / len(expected_set) if len(expected_set) > 0 else 0.0
        precision = tp / len(retrieved_set) if len(retrieved_set) > 0 else 0.0
        
        report.append(f"\n样本{i}:")
        report.append(f"  查询: {result['query']}")
        report.append(f"  文档: {result['doc_name']}")
        report.append(f"  结果: TP={tp}, FN={fn}, FP={fp}")
        report.append(f"  召回率: {recall:.4f} | 精确率: {precision:.4f}")
    
    # 影响因素分析
    report.append("\n【潜在影响因素分析】")
    report.append("  1. Chunk大小设置：当前500字符，过大可能导致冗余，过小可能断裂上下文")
    report.append("  2. 检索数量：当前top_k=5，设置过小可能遗漏相关Chunk")
    report.append("  3. Embedding模型：模型质量直接影响语义匹配准确性")
    report.append("  4. 向量数据库配置：距离度量方式影响检索效果")
    report.append("")
    
    # 改进建议
    report.append("【改进建议】")
    if overall.recall < 0.7:
        report.append("  - 建议增大top_k值至10，确保更多相关Chunk被检索到")
        report.append("  - 检查Embedding模型配置是否正确")
    if overall.precision < 0.7:
        report.append("  - 建议优化Chunk切分策略，提高语义完整性")
        report.append("  - 考虑添加相关性阈值过滤")
    
    report.append("\n" + "=" * 80)
    report.append("          报告结束")
    report.append("=" * 80)
    
    report_content = "\n".join(report)
    print("\n" + report_content)
    
    # 保存报告
    report_path = "rag_recall_evaluation_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"\n报告已保存到: {os.path.abspath(report_path)}")


def main():
    """主执行函数"""
    print("\n" + "=" * 60)
    print("    RAG系统召回率计算演示")
    print("=" * 60)
    
    # 步骤1: 创建测试数据
    test_samples = create_demo_test_data()
    
    # 步骤2: 模拟检索结果
    results = simulate_retrieval_results(test_samples)
    
    # 步骤3: 计算指标
    overall, detailed_results = calculate_metrics(results)
    
    # 步骤4: 生成报告
    generate_report(overall, detailed_results, test_samples)
    
    print("\n" + "=" * 60)
    print("    计算完成！")
    print("=" * 60)
    print(f"\n最终结果:")
    print(f"  召回率(Recall): {overall.recall:.4f} ({overall.recall * 100:.1f}%)")
    print(f"  精确率(Precision): {overall.precision:.4f} ({overall.precision * 100:.1f}%)")
    print(f"  F1分数: {overall.f1:.4f}")


if __name__ == "__main__":
    main()