from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np
from collections import defaultdict
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    query_id: str
    retrieved_docs: List[str]
    relevance_scores: List[float]
    ground_truth: List[str]
    metadata: Dict[str, Any] = None


@dataclass
class MetricsReport:
    timestamp: datetime
    dataset_name: str
    num_queries: int
    metrics: Dict[str, float]
    per_query_metrics: List[Dict[str, Any]]
    config: Dict[str, Any]


class RetrievalMetrics:
    def __init__(self):
        self.results: List[RetrievalResult] = []
        self.metrics_history: List[MetricsReport] = []
    
    def add_result(self, result: RetrievalResult):
        self.results.append(result)
    
    def precision_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        if k <= 0:
            return 0.0
        
        retrieved_k = retrieved[:k]
        relevant_set = set(relevant)
        
        num_relevant_retrieved = sum(1 for doc in retrieved_k if doc in relevant_set)
        
        return num_relevant_retrieved / k if k > 0 else 0.0
    
    def recall_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        if not relevant or k <= 0:
            return 0.0
        
        retrieved_k = retrieved[:k]
        relevant_set = set(relevant)
        
        num_relevant_retrieved = sum(1 for doc in retrieved_k if doc in relevant_set)
        
        return num_relevant_retrieved / len(relevant)
    
    def f1_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        precision = self.precision_at_k(retrieved, relevant, k)
        recall = self.recall_at_k(retrieved, relevant, k)
        
        if precision + recall == 0:
            return 0.0
        
        return 2 * (precision * recall) / (precision + recall)
    
    def average_precision(self, retrieved: List[str], relevant: List[str]) -> float:
        if not relevant:
            return 0.0
        
        relevant_set = set(relevant)
        num_relevant = 0
        sum_precision = 0.0
        
        for i, doc in enumerate(retrieved, 1):
            if doc in relevant_set:
                num_relevant += 1
                precision_at_i = num_relevant / i
                sum_precision += precision_at_i
        
        return sum_precision / len(relevant) if relevant else 0.0
    
    def mean_average_precision(self, results: List[RetrievalResult] = None) -> float:
        if results is None:
            results = self.results
        
        if not results:
            return 0.0
        
        ap_scores = [
            self.average_precision(r.retrieved_docs, r.ground_truth)
            for r in results
        ]
        
        return np.mean(ap_scores)
    
    def reciprocal_rank(self, retrieved: List[str], relevant: List[str]) -> float:
        relevant_set = set(relevant)
        
        for i, doc in enumerate(retrieved, 1):
            if doc in relevant_set:
                return 1.0 / i
        
        return 0.0
    
    def mean_reciprocal_rank(self, results: List[RetrievalResult] = None) -> float:
        if results is None:
            results = self.results
        
        if not results:
            return 0.0
        
        rr_scores = [
            self.reciprocal_rank(r.retrieved_docs, r.ground_truth)
            for r in results
        ]
        
        return np.mean(rr_scores)
    
    def dcg_at_k(self, relevance_scores: List[float], k: int) -> float:
        if k <= 0:
            return 0.0
        
        relevance_k = relevance_scores[:k]
        
        dcg = 0.0
        for i, rel in enumerate(relevance_k, 1):
            dcg += (2**rel - 1) / np.log2(i + 1)
        
        return dcg
    
    def ndcg_at_k(
        self,
        retrieved: List[str],
        relevant: List[str],
        relevance_scores: List[float],
        k: int
    ) -> float:
        if k <= 0 or not relevant:
            return 0.0
        
        actual_dcg = self.dcg_at_k(relevance_scores, k)
        
        ideal_scores = sorted(relevance_scores, reverse=True)
        ideal_dcg = self.dcg_at_k(ideal_scores, k)
        
        if ideal_dcg == 0:
            return 0.0
        
        return actual_dcg / ideal_dcg
    
    def hit_rate_at_k(self, results: List[RetrievalResult], k: int) -> float:
        if not results:
            return 0.0
        
        hits = 0
        for result in results:
            retrieved_k = result.retrieved_docs[:k]
            relevant_set = set(result.ground_truth)
            
            if any(doc in relevant_set for doc in retrieved_k):
                hits += 1
        
        return hits / len(results)
    
    def success_at_k(self, results: List[RetrievalResult], k: int) -> float:
        return self.hit_rate_at_k(results, k)
    
    def calculate_all_metrics(
        self,
        results: List[RetrievalResult] = None,
        k_values: List[int] = None
    ) -> Dict[str, Any]:
        if results is None:
            results = self.results
        
        if k_values is None:
            k_values = [1, 3, 5, 10]
        
        if not results:
            return {}
        
        metrics = {
            "map": self.mean_average_precision(results),
            "mrr": self.mean_reciprocal_rank(results)
        }
        
        for k in k_values:
            precision_scores = []
            recall_scores = []
            f1_scores = []
            ndcg_scores = []
            
            for result in results:
                precision_scores.append(
                    self.precision_at_k(result.retrieved_docs, result.ground_truth, k)
                )
                recall_scores.append(
                    self.recall_at_k(result.retrieved_docs, result.ground_truth, k)
                )
                f1_scores.append(
                    self.f1_at_k(result.retrieved_docs, result.ground_truth, k)
                )
                
                if result.relevance_scores:
                    ndcg_scores.append(
                        self.ndcg_at_k(
                            result.retrieved_docs,
                            result.ground_truth,
                            result.relevance_scores,
                            k
                        )
                    )
            
            metrics[f"precision@{k}"] = np.mean(precision_scores)
            metrics[f"recall@{k}"] = np.mean(recall_scores)
            metrics[f"f1@{k}"] = np.mean(f1_scores)
            metrics[f"hit_rate@{k}"] = self.hit_rate_at_k(results, k)
            
            if ndcg_scores:
                metrics[f"ndcg@{k}"] = np.mean(ndcg_scores)
        
        return metrics
    
    def calculate_per_query_metrics(
        self,
        results: List[RetrievalResult] = None,
        k: int = 10
    ) -> List[Dict[str, Any]]:
        if results is None:
            results = self.results
        
        per_query = []
        
        for result in results:
            query_metrics = {
                "query_id": result.query_id,
                "num_retrieved": len(result.retrieved_docs),
                "num_relevant": len(result.ground_truth),
                "precision": self.precision_at_k(
                    result.retrieved_docs, result.ground_truth, k
                ),
                "recall": self.recall_at_k(
                    result.retrieved_docs, result.ground_truth, k
                ),
                "f1": self.f1_at_k(
                    result.retrieved_docs, result.ground_truth, k
                ),
                "ap": self.average_precision(
                    result.retrieved_docs, result.ground_truth
                ),
                "rr": self.reciprocal_rank(
                    result.retrieved_docs, result.ground_truth
                )
            }
            
            if result.relevance_scores:
                query_metrics["ndcg"] = self.ndcg_at_k(
                    result.retrieved_docs,
                    result.ground_truth,
                    result.relevance_scores,
                    k
                )
            
            if result.metadata:
                query_metrics["metadata"] = result.metadata
            
            per_query.append(query_metrics)
        
        return per_query
    
    def generate_report(
        self,
        dataset_name: str,
        config: Dict[str, Any] = None,
        save_path: Optional[str] = None
    ) -> MetricsReport:
        metrics = self.calculate_all_metrics()
        per_query = self.calculate_per_query_metrics()
        
        report = MetricsReport(
            timestamp=datetime.now(),
            dataset_name=dataset_name,
            num_queries=len(self.results),
            metrics=metrics,
            per_query_metrics=per_query,
            config=config or {}
        )
        
        self.metrics_history.append(report)
        
        if save_path:
            self.save_report(report, save_path)
        
        return report
    
    def save_report(self, report: MetricsReport, save_path: str):
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        report_dict = asdict(report)
        report_dict["timestamp"] = report.timestamp.isoformat()
        
        with open(path, "w") as f:
            json.dump(report_dict, f, indent=2)
        
        logger.info(f"Saved metrics report to {save_path}")
    
    def compare_systems(
        self,
        baseline_results: List[RetrievalResult],
        improved_results: List[RetrievalResult],
        k_values: List[int] = None
    ) -> Dict[str, Any]:
        if k_values is None:
            k_values = [1, 3, 5, 10]
        
        baseline_metrics = self.calculate_all_metrics(baseline_results, k_values)
        improved_metrics = self.calculate_all_metrics(improved_results, k_values)
        
        comparison = {
            "baseline": baseline_metrics,
            "improved": improved_metrics,
            "improvements": {}
        }
        
        for metric_name in baseline_metrics:
            baseline_val = baseline_metrics[metric_name]
            improved_val = improved_metrics[metric_name]
            
            if baseline_val > 0:
                improvement_pct = ((improved_val - baseline_val) / baseline_val) * 100
            else:
                improvement_pct = 100 if improved_val > 0 else 0
            
            comparison["improvements"][metric_name] = {
                "absolute": improved_val - baseline_val,
                "relative_pct": improvement_pct
            }
        
        return comparison
    
    def statistical_significance_test(
        self,
        results1: List[RetrievalResult],
        results2: List[RetrievalResult],
        metric: str = "map",
        num_bootstrap: int = 1000
    ) -> Dict[str, Any]:
        from scipy import stats
        
        scores1 = []
        scores2 = []
        
        for r1, r2 in zip(results1, results2):
            if metric == "map" or metric == "ap":
                scores1.append(self.average_precision(r1.retrieved_docs, r1.ground_truth))
                scores2.append(self.average_precision(r2.retrieved_docs, r2.ground_truth))
            elif metric == "mrr" or metric == "rr":
                scores1.append(self.reciprocal_rank(r1.retrieved_docs, r1.ground_truth))
                scores2.append(self.reciprocal_rank(r2.retrieved_docs, r2.ground_truth))
            elif metric.startswith("precision@"):
                k = int(metric.split("@")[1])
                scores1.append(self.precision_at_k(r1.retrieved_docs, r1.ground_truth, k))
                scores2.append(self.precision_at_k(r2.retrieved_docs, r2.ground_truth, k))
            elif metric.startswith("recall@"):
                k = int(metric.split("@")[1])
                scores1.append(self.recall_at_k(r1.retrieved_docs, r1.ground_truth, k))
                scores2.append(self.recall_at_k(r2.retrieved_docs, r2.ground_truth, k))
        
        t_stat, p_value = stats.ttest_rel(scores1, scores2)
        
        mean_diff = np.mean(scores2) - np.mean(scores1)
        std_diff = np.std(np.array(scores2) - np.array(scores1))
        
        return {
            "metric": metric,
            "mean_system1": np.mean(scores1),
            "mean_system2": np.mean(scores2),
            "mean_difference": mean_diff,
            "std_difference": std_diff,
            "t_statistic": t_stat,
            "p_value": p_value,
            "significant_at_0.05": p_value < 0.05,
            "significant_at_0.01": p_value < 0.01
        }