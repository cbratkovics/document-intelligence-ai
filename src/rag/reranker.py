from typing import List, Dict, Any, Tuple, Optional
import logging
from langchain_openai import ChatOpenAI
from ..core.config import settings
import asyncio

logger = logging.getLogger(__name__)


class Reranker:
    """
    Cross-encoder style reranking using LLM for better relevance.
    Since we're using OpenAI API, we'll implement a prompt-based reranker.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.llm = ChatOpenAI(
            model=model_name or settings.openai_model,
            temperature=0.0,
            openai_api_key=settings.openai_api_key,
        )
        self.max_concurrent = 5  # Limit concurrent API calls

    async def rerank(
        self, query: str, documents: List[Dict[str, Any]], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using LLM-based relevance scoring.

        Args:
            query: The search query
            documents: List of documents to rerank
            top_k: Number of top documents to return

        Returns:
            List of reranked documents with scores
        """
        if not documents:
            return []

        # Limit documents to avoid excessive API calls
        max_docs = min(len(documents), 20)
        docs_to_rerank = documents[:max_docs]

        # Score documents in batches
        scored_docs = await self._score_documents_batch(query, docs_to_rerank)

        # Sort by score
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        # Return top-k with scores
        results = []
        for doc, score in scored_docs[:top_k]:
            doc_copy = doc.copy()
            doc_copy["rerank_score"] = score
            results.append(doc_copy)

        logger.info(
            f"Reranked {len(docs_to_rerank)} documents, returning top {len(results)}"
        )
        return results

    async def _score_documents_batch(
        self, query: str, documents: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Score documents in batches with rate limiting"""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def score_doc(doc):
            async with semaphore:
                score = await self._score_single_document(query, doc)
                return (doc, score)

        tasks = [score_doc(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out any failed scorings
        scored_docs = []
        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                scored_docs.append(result)
            else:
                logger.warning(f"Failed to score document: {result}")

        return scored_docs

    async def _score_single_document(
        self, query: str, document: Dict[str, Any]
    ) -> float:
        """Score a single document's relevance to the query"""
        try:
            content = document.get("content", "")
            if not content:
                return 0.0

            # Truncate content if too long
            max_content_length = 500
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."

            prompt = f"""Given the following query and document, rate the relevance of the document to the query on a scale from 0 to 10.
Only respond with a number between 0 and 10.

Query: {query}

Document:
{content}

Relevance score (0-10):"""

            response = await self.llm.ainvoke(prompt)

            # Extract score from response
            try:
                score_text = response.content.strip()
                # Handle various formats like "8", "8/10", "8.5", etc.
                score_text = score_text.split("/")[0].strip()
                score = float(score_text)
                # Normalize to 0-1 range
                return min(max(score / 10.0, 0.0), 1.0)
            except (ValueError, AttributeError):
                logger.warning(
                    f"Could not parse score from response: {response.content}"
                )
                return 0.5  # Default middle score

        except Exception as e:
            logger.error(f"Error scoring document: {e}")
            return 0.0

    async def rerank_with_feedback(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
        user_feedback: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank with optional user feedback to improve results.

        Args:
            query: The search query
            documents: List of documents to rerank
            top_k: Number of top documents to return
            user_feedback: Optional feedback on previous results

        Returns:
            List of reranked documents
        """
        # If we have feedback, adjust scoring
        if user_feedback:
            # This could be extended to use feedback for learning
            logger.info("Reranking with user feedback")
            # For now, just log it

        return await self.rerank(query, documents, top_k)


class SimpleReranker:
    """
    A simple, fast reranker based on keyword matching and heuristics.
    Useful when LLM-based reranking is too slow or expensive.
    """

    def rerank(
        self, query: str, documents: List[Dict[str, Any]], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using simple heuristics.

        Args:
            query: The search query
            documents: List of documents to rerank
            top_k: Number of top documents to return

        Returns:
            List of reranked documents
        """
        if not documents:
            return []

        query_terms = set(query.lower().split())

        scored_docs = []
        for doc in documents:
            content = doc.get("content", "").lower()

            # Score based on:
            # 1. Exact query match
            # 2. Individual term matches
            # 3. Term proximity
            # 4. Original relevance score

            score = 0.0

            # Exact match bonus
            if query.lower() in content:
                score += 2.0

            # Term frequency
            term_matches = sum(1 for term in query_terms if term in content)
            score += term_matches * 0.5

            # Consider original relevance score if available
            if "relevance_score" in doc:
                score += doc["relevance_score"] * 0.5

            scored_docs.append((doc, score))

        # Sort by score
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        results = []
        for doc, score in scored_docs[:top_k]:
            doc_copy = doc.copy()
            doc_copy["rerank_score"] = score
            results.append(doc_copy)

        return results
