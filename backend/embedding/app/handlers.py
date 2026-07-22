"""Business logic handlers for the embedding service."""
from typing import Dict, Any, List, Optional
import os
import uuid
import httpx
from shared.auth import attach_internal_auth_context
import time

from app.messaging.interfaces import IProducer
from app.embedding.interfaces import IEmbeddingModel
from app.extraction.interfaces import IFileExtractor
from app.logger import ServiceLogger
from app.config import EmbeddingConfig
from app.utils.chunking import TextChunker


class EmbeddingHandler:
    """Handler for embedding generation requests."""
    
    def __init__(
        self,
        producer: IProducer,
        embedding_model: Optional[IEmbeddingModel],
        logger: ServiceLogger,
        response_topic: str,
        vector_db_topic: str,
        files_topic: str,
        config: EmbeddingConfig
    ):
        """
        Initialize the embedding handler.
        
        Args:
            producer: Message producer
            embedding_model: Embedding model instance
            logger: Service logger
            response_topic: Topic for responses
            vector_db_topic: Topic for sending vectors to vectordb
            files_topic: Topic for updating files service
            config: Service configuration
        """
        self.producer = producer
        self.embedding_model = embedding_model
        self.logger = logger
        self.response_topic = response_topic
        self.vector_db_topic = vector_db_topic
        self.files_topic = files_topic
        self.batch_size = config.embedding_batch_size
        self.query_prefix = getattr(config, "embedding_query_prefix", "") or ""
        self.passage_prefix = getattr(config, "embedding_passage_prefix", "") or ""
        self.metadata_fetch_timeout = getattr(config, "metadata_fetch_timeout", 5.0)
        
        # Initialize text chunker
        self.chunker = TextChunker(
            strategy=config.chunking_strategy,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
    
    def process_request(self, request: Dict[str, Any]) -> None:
        """Process an embedding request."""
        correlation_id = request.get("correlation_id")
        text = request.get("text", "")
        file_id = request.get("file_id")  # Optional file_id for tracking
        filename = request.get("filename", "")  # Original filename for metadata tags
        
        self.logger.log(
            "handler:process_embedding",
            "Processing embedding request",
            {"correlation_id": correlation_id, "text_length": len(text), "file_id": file_id, "filename": filename}
        )
        
        try:
            if not self.embedding_model or not self.embedding_model.is_loaded():
                self._send_error(correlation_id, "Embedding model not available")
                if file_id:
                    self._update_files_stage(file_id, "embedding", "error")
                return
            
            # Chunk the text
            chunks = self._chunk_text(text)
            
            # E5/BGE models: apply query prefix for RAG queries, passage prefix for document chunks
            # Prefix is used only for encoding; store original chunks in vectordb for display
            chunks_to_encode = chunks
            if file_id and self.passage_prefix:
                chunks_to_encode = [self.passage_prefix + c for c in chunks]
            elif not file_id and self.query_prefix:
                chunks_to_encode = [self.query_prefix + c for c in chunks]
            
            self.logger.log(
                "handler:process_embedding",
                "Text chunked",
                {"correlation_id": correlation_id, "num_chunks": len(chunks)}
            )
            
            # Fetch metadata keywords if file_id is available
            keywords = None
            if file_id:
                keywords = self._fetch_metadata_keywords(file_id)
                if keywords:
                    self.logger.log(
                        "handler:process_embedding",
                        "Metadata keywords fetched",
                        {"file_id": file_id, "keywords_count": len(keywords)}
                    )
                else:
                    self.logger.log(
                        "handler:process_embedding",
                        "Metadata keywords not available yet",
                        {"file_id": file_id},
                        hypothesis_id="W"
                    )
            
            # Batch embed all chunks for better performance (use prefixed text for E5/BGE)
            embeddings = self.embedding_model.encode_batch(chunks_to_encode, batch_size=self.batch_size)
            first_embedding = embeddings[0] if embeddings else []
            
            # Send vectors to vectordb (only for file uploads, not RAG queries)
            vectors_sent = 0
            if file_id and embeddings:
                self._send_batch_to_vectordb(
                    embeddings=embeddings,
                    chunks=chunks,  # Store original chunks (no prefix) for display and hybrid search
                    file_id=file_id,
                    filename=filename,
                    keywords=keywords
                )
                vectors_sent = len(embeddings)
                self.producer.flush()
            
            # Update files service that embedding stage is done
            if file_id:
                self._update_files_stage(file_id, "embedding", "done")
            
            self._send_response(correlation_id, {
                "embedding": first_embedding,
                "num_chunks": len(chunks),
                "vectors_sent": vectors_sent
            })
            
            self.logger.log(
                "handler:process_embedding",
                "Embedding generated and sent to vectordb",
                {
                    "correlation_id": correlation_id,
                    "embedding_dim": len(first_embedding) if first_embedding else 0,
                    "num_chunks": len(chunks),
                    "file_id": file_id
                }
            )
        except Exception as e:
            self.logger.log(
                "handler:process_embedding",
                "Error generating embedding",
                {"correlation_id": correlation_id, "error": str(e)},
                hypothesis_id="E"
            )
            if file_id:
                self._update_files_stage(file_id, "embedding", "error")
            self._send_error(correlation_id, str(e))
    
    def _send_response(self, correlation_id: str, data: Dict[str, Any]) -> None:
        """Send a success response."""
        message = {
            "correlation_id": correlation_id,
            "data": data
        }
        self.producer.send(self.response_topic, message)
        self.producer.flush()
    
    def _send_error(self, correlation_id: str, error_message: str) -> None:
        """Send an error response."""
        message = {
            "correlation_id": correlation_id,
            "data": {
                "embedding": [],
                "error": error_message
            }
        }
        self.producer.send(self.response_topic, message)
        self.producer.flush()
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Chunk text into pieces.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        return self.chunker.chunk(text)
    
    def _send_batch_to_vectordb(
        self,
        embeddings: List[List[float]],
        chunks: List[str],
        file_id: str,
        filename: str,
        keywords: Optional[List[str]] = None
    ) -> None:
        """
        Send all vectors to vectordb in one batch message for better performance.
        """
        total_chunks = len(embeddings)
        keywords_str = ",".join(keywords) if isinstance(keywords, list) and keywords else None
        metadatas = []
        for i in range(total_chunks):
            meta = {
                "chunk_index": str(i),
                "total_chunks": str(total_chunks),
                "file_id": file_id
            }
            if filename:
                meta["filename"] = filename
            if keywords_str:
                meta["keywords"] = keywords_str
            metadatas.append(meta)
        
        batch_message = {
            "action": "batch_insert",
            "vectors": embeddings,
            "metadata": metadatas,
            "documents": chunks
        }
        self.producer.send(self.vector_db_topic, batch_message)
        
        self.logger.log(
            "handler:send_batch_to_vectordb",
            "Batch sent to vectordb",
            {"file_id": file_id, "count": total_chunks, "has_keywords": keywords is not None}
        )
    
    def _send_to_vectordb(
        self,
        embedding: List[float],
        chunk_text: str,
        file_id: Optional[str],
        filename: str,
        chunk_index: int,
        total_chunks: int,
        keywords: Optional[List[str]] = None
    ) -> None:
        """
        Send vector to vectordb service with text and metadata tags.
        
        Args:
            embedding: Embedding vector
            chunk_text: Raw text of chunk for semantic search
            file_id: File identifier (optional)
            filename: Original filename for metadata tags
            chunk_index: Index of the chunk
            total_chunks: Total number of chunks
            keywords: Optional list of metadata keywords
        """
        vector_id = str(uuid.uuid4())
        
        # Prepare metadata tags for chunk search
        metadata = {
            "chunk_index": str(chunk_index),
            "total_chunks": str(total_chunks)
        }
        
        if file_id:
            metadata["file_id"] = file_id
        
        if filename:
            metadata["filename"] = filename
        
        # Add keywords to metadata if available (store as comma-separated for ChromaDB string requirement)
        if keywords:
            metadata["keywords"] = ",".join(keywords) if isinstance(keywords, list) else str(keywords)
        
        # Send to vectordb with text for semantic search
        vectordb_message = {
            "action": "insert",
            "id": vector_id,
            "vector": embedding,
            "metadata": metadata,
            "text": chunk_text
        }
        
        self.producer.send(self.vector_db_topic, vectordb_message)
        
        self.logger.log(
            "handler:send_to_vectordb",
            "Vector sent to vectordb",
            {
                "vector_id": vector_id,
                "file_id": file_id,
                "chunk_index": chunk_index,
                "has_keywords": keywords is not None,
                "has_text": bool(chunk_text)
            }
        )
    
    def _fetch_metadata_keywords(self, file_id: str, max_retries: int = 3, retry_delay: float = 1.0) -> Optional[List[str]]:
        """
        Fetch metadata keywords from files service via HTTP.
        
        Args:
            file_id: File identifier
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            List of keywords or None if not available
        """
        files_service_url = os.getenv("FILES_SERVICE_URL", "http://localhost:8005").rstrip("/")
        url = f"{files_service_url}/v1/files/{file_id}"
        
        for attempt in range(max_retries):
            try:
                auth_envelope = attach_internal_auth_context({})
                with httpx.Client(timeout=self.metadata_fetch_timeout) as client:
                    response = client.get(
                        url,
                        headers={"X-Internal-Auth": auth_envelope.get("auth_context", "")},
                    )
                    if response.status_code == 404:
                        return None
                    response.raise_for_status()
                    data = response.json()
                    metadata = data.get("metadata", {})
                    keywords = metadata.get("keywords")
                    if keywords and isinstance(keywords, list):
                        return keywords
                    return None
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                self.logger.log(
                    "handler:fetch_metadata",
                    "Error fetching metadata keywords",
                    {"file_id": file_id, "error": str(e), "attempt": attempt + 1},
                    hypothesis_id="W"
                )
                return None
        
        return None
    
    def _update_files_stage(self, file_id: str, stage: str, status: str) -> None:
        """
        Update file stage in files service.
        
        Args:
            file_id: File identifier
            stage: Stage name
            status: Stage status
        """
        update_message = {
            "action": "update_stage",
            "file_id": file_id,
            "stage": stage,
            "status": status
        }
        self.producer.send(self.files_topic, update_message)
        self.producer.flush()
        
        self.logger.log(
            "handler:update_files_stage",
            "Updated file stage",
            {"file_id": file_id, "stage": stage, "status": status}
        )


class ExtractionHandler:
    """Handler for file extraction requests."""
    
    def __init__(
        self,
        producer: IProducer,
        extractors: List[IFileExtractor],
        logger: ServiceLogger,
        files_topic: str,
        summary_topic: str,
        metadata_topic: str,
        embedding_topic: str
    ):
        """Initialize the extraction handler."""
        self.producer = producer
        self.extractors = extractors
        self.logger = logger
        self.files_topic = files_topic
        self.summary_topic = summary_topic
        self.metadata_topic = metadata_topic
        self.embedding_topic = embedding_topic
    
    def process_request(self, request: Dict[str, Any]) -> None:
        """Process a file extraction request."""
        file_id = request.get("file_id")
        file_path = request.get("path")
        filename = request.get("filename", "unknown")
        
        self.logger.log(
            "handler:process_extraction",
            "Processing extraction request",
            {"file_id": file_id, "filename": filename, "path": file_path}
        )
        
        try:
            # Verify file exists
            if not os.path.exists(file_path):
                self.logger.log(
                    "handler:process_extraction",
                    "File not found",
                    {"file_id": file_id, "file_path": file_path},
                    hypothesis_id="E"
                )
                self._update_stage(file_id, "extraction", "error")
                return
            
            # Get appropriate extractor
            extractor = self._get_extractor(filename)
            if not extractor:
                raise ValueError(f"Unsupported file type: {os.path.splitext(filename)[1]}")
            
            # Extract text
            extracted_text = extractor.extract(file_path, filename)
            
            self.logger.log(
                "handler:process_extraction",
                "Text extracted successfully",
                {"file_id": file_id, "text_length": len(extracted_text)}
            )
            
            # Update files service: set extraction stage to "done"
            self._update_stage(file_id, "extraction", "done")
            
            # Send extracted text to embedding service for vectorization + vector DB storage
            embedding_message = {
                "text": extracted_text,
                "file_id": file_id,
                "filename": filename,
                "correlation_id": str(uuid.uuid4())
            }
            self.producer.send(self.embedding_topic, embedding_message)
            self.producer.flush()
            
            # Send extracted text to LLM agent for summarization
            summary_message = {
                "file_id": file_id,
                "text": extracted_text,
                "prompt": "TL;DR"
            }
            self.producer.send(self.summary_topic, summary_message)
            self.producer.flush()
            
            # Send extracted text to LLM agent for metadata extraction (in parallel)
            metadata_message = {
                "file_id": file_id,
                "text": extracted_text
            }
            self.producer.send(self.metadata_topic, metadata_message)
            self.producer.flush()
            
            self.logger.log(
                "handler:process_extraction",
                "Text sent to embedding, summary and metadata topics",
                {"file_id": file_id, "embedding_topic": self.embedding_topic, "summary_topic": self.summary_topic, "metadata_topic": self.metadata_topic}
            )
            
        except Exception as e:
            self.logger.log(
                "handler:process_extraction",
                "Error extracting text",
                {"file_id": file_id, "error": str(e)},
                hypothesis_id="E"
            )
            # Update files service: set extraction stage to "error"
            self._update_stage(file_id, "extraction", "error")
    
    def _get_extractor(self, filename: str) -> Optional[IFileExtractor]:
        """Get the appropriate extractor for a file."""
        from app.extraction.factories import FileExtractorFactory
        return FileExtractorFactory.get_extractor_for_file(self.extractors, filename)
    
    def _update_stage(self, file_id: str, stage: str, status: str) -> None:
        """Update file stage in files service."""
        update_message = {
            "action": "update_stage",
            "file_id": file_id,
            "stage": stage,
            "status": status
        }
        self.producer.send(self.files_topic, update_message)
        self.producer.flush()
