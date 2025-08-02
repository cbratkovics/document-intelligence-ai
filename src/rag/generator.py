from typing import List, Dict, Any, Optional, AsyncGenerator
import logging
from datetime import datetime
import asyncio

from langchain_openai import ChatOpenAI
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import BaseMessage
from langchain.callbacks import AsyncIteratorCallbackHandler

from ..core.config import settings
from .retriever import RAGRetriever

logger = logging.getLogger(__name__)


class RAGGenerator:
    """RAG generator for answer generation based on retrieved context"""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.openai_model
        self.retriever = RAGRetriever()
        self.llm = self._initialize_llm()
        self.prompt_template = self._create_prompt_template()

    def _initialize_llm(self) -> ChatOpenAI:
        """Initialize the language model"""
        try:
            llm = ChatOpenAI(
                model=self.model_name,
                temperature=0.7,
                max_tokens=1000,
                openai_api_key=settings.openai_api_key,
            )
            logger.info(f"Initialized LLM: {self.model_name}")
            return llm
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise

    def _create_prompt_template(self) -> ChatPromptTemplate:
        """Create the RAG prompt template"""
        system_template = """You are a helpful AI assistant that answers questions based on the provided context.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer based on the context, just say that you don't know.
Don't try to make up an answer.
Always cite the specific parts of the context that support your answer.

Context:
{context}
"""

        human_template = """Question: {question}

Please provide a comprehensive answer based on the context above."""

        messages = [
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template(human_template),
        ]

        return ChatPromptTemplate.from_messages(messages)

    async def generate_answer(
        self,
        question: str,
        max_context_length: int = 3000,
        include_sources: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate an answer based on retrieved context

        Args:
            question: User question
            max_context_length: Maximum context length
            include_sources: Whether to include source references

        Returns:
            Dictionary with answer and metadata
        """
        try:
            start_time = datetime.utcnow()

            # Retrieve relevant context
            context, sources = await self.retriever.get_context_for_generation(
                question, max_context_length
            )

            if not context:
                return {
                    "answer": "I couldn't find any relevant information in the documents to answer your question.",
                    "sources": [],
                    "processing_time": 0,
                    "confidence": 0.0,
                }

            # Format the prompt
            prompt = self.prompt_template.format_messages(
                context=context, question=question
            )

            # Generate answer
            response = await self.llm.ainvoke(prompt)
            answer = response.content

            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            # Prepare response
            result = {
                "answer": answer,
                "processing_time": processing_time,
                "model": self.model_name,
                "context_chunks_used": len(sources),
            }

            if include_sources:
                result["sources"] = self._format_sources(sources)

            # Estimate confidence based on source relevance
            avg_relevance = sum(s["relevance_score"] for s in sources) / len(sources)
            result["confidence"] = avg_relevance

            logger.info(
                f"Generated answer for question: '{question[:50]}...' "
                f"in {processing_time:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise

    async def generate_answer_stream(
        self, question: str, max_context_length: int = 3000
    ) -> AsyncGenerator[str, None]:
        """
        Generate an answer with streaming response

        Args:
            question: User question
            max_context_length: Maximum context length

        Yields:
            Answer tokens as they're generated
        """
        try:
            # Retrieve relevant context
            context, sources = await self.retriever.get_context_for_generation(
                question, max_context_length
            )

            if not context:
                yield "I couldn't find any relevant information in the documents to answer your question."
                return

            # Create callback handler for streaming
            callback = AsyncIteratorCallbackHandler()

            # Create streaming LLM
            streaming_llm = ChatOpenAI(
                model=self.model_name,
                temperature=0.7,
                max_tokens=1000,
                openai_api_key=settings.openai_api_key,
                streaming=True,
                callbacks=[callback],
            )

            # Format the prompt
            prompt = self.prompt_template.format_messages(
                context=context, question=question
            )

            # Start generation in background
            task = asyncio.create_task(streaming_llm.ainvoke(prompt))

            # Stream tokens
            async for token in callback.aiter():
                yield token

            await task

        except Exception as e:
            logger.error(f"Error in streaming generation: {e}")
            yield f"\n\nError: {str(e)}"

    async def generate_summary(self, doc_id: str, max_length: int = 500) -> str:
        """
        Generate a summary of a document

        Args:
            doc_id: Document ID
            max_length: Maximum summary length

        Returns:
            Document summary
        """
        try:
            # Search for all chunks of the document
            results = await self.retriever.search(
                query="",  # Empty query to get all chunks
                filters={"doc_id": doc_id},
                top_k=100,  # Get all chunks
            )

            if not results:
                return "Document not found."

            # Combine chunks
            full_text = "\n\n".join([r["content"] for r in results])

            # Create summary prompt
            summary_prompt = f"""Please provide a concise summary of the following document in no more than {max_length} characters:

{full_text[:5000]}  # Limit input to avoid token limits

Summary:"""

            # Generate summary
            response = await self.llm.ainvoke(summary_prompt)
            summary = response.content

            # Truncate if necessary
            if len(summary) > max_length:
                summary = summary[: max_length - 3] + "..."

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Error generating summary."

    def _format_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format source references for output"""
        formatted_sources = []

        for source in sources:
            formatted = {
                "chunk_id": source.get("chunk_id", ""),
                "relevance_score": round(source.get("relevance_score", 0), 3),
                "filename": source.get("metadata", {}).get("filename", "Unknown"),
                "chunk_index": source.get("metadata", {}).get("chunk_index", 0),
                "total_chunks": source.get("metadata", {}).get("total_chunks", 0),
            }

            # Add page number for PDFs
            if "page_number" in source.get("metadata", {}):
                formatted["page_number"] = source["metadata"]["page_number"]

            formatted_sources.append(formatted)

        # Sort by relevance
        formatted_sources.sort(key=lambda x: x["relevance_score"], reverse=True)

        return formatted_sources

    async def evaluate_answer_quality(
        self, question: str, answer: str, context: str
    ) -> Dict[str, Any]:
        """
        Evaluate the quality of a generated answer

        Args:
            question: Original question
            answer: Generated answer
            context: Context used for generation

        Returns:
            Evaluation metrics
        """
        try:
            eval_prompt = f"""Evaluate the following answer based on the question and context provided.

Question: {question}

Context: {context[:1000]}

Answer: {answer}

Please evaluate the answer on the following criteria (1-5 scale):
1. Relevance: Does the answer address the question?
2. Accuracy: Is the answer factually correct based on the context?
3. Completeness: Does the answer fully address all aspects of the question?
4. Clarity: Is the answer clear and well-structured?

Provide scores for each criterion and a brief explanation.
Format: Relevance: X/5, Accuracy: X/5, Completeness: X/5, Clarity: X/5
"""

            response = await self.llm.ainvoke(eval_prompt)

            # Parse evaluation (simplified)
            eval_text = response.content
            scores = {
                "relevance": 3,
                "accuracy": 3,
                "completeness": 3,
                "clarity": 3,
                "explanation": eval_text,
            }

            # Try to extract scores from response
            import re

            for criterion in ["relevance", "accuracy", "completeness", "clarity"]:
                match = re.search(f"{criterion}:\\s*(\\d)/5", eval_text.lower())
                if match:
                    scores[criterion] = int(match.group(1))

            scores["overall"] = (
                sum(
                    scores[k]
                    for k in ["relevance", "accuracy", "completeness", "clarity"]
                )
                / 4
            )

            return scores

        except Exception as e:
            logger.error(f"Error evaluating answer: {e}")
            return {"error": str(e), "overall": 0}
