"""Queued LLM client wrapper for sequential request processing."""
import concurrent.futures
import queue
import threading
from typing import Callable, List

from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation


class QueuedLLMClient(ILLMClient):
    """Wrapper around an LLM client that queues requests for sequential processing."""
    
    def __init__(self, llm_client: ILLMClient):
        """Initialize the queued LLM client."""
        self.llm_client = llm_client
        self._lock = threading.Lock()
        self._processing = False
        self._request_queue = queue.Queue()
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._start_worker()
    
    def _start_worker(self):
        """Start the worker thread that processes requests sequentially."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()
    
    def _process_queue(self):
        """Process requests from the queue sequentially."""
        while not self._stop_event.is_set():
            request = None
            try:
                # Get request from queue with timeout to allow checking stop event
                request = self._request_queue.get(timeout=1.0)
                
                # Process the request
                try:
                    result = request['func'](*request['args'], **request['kwargs'])
                    request['future'].set_result(result)
                except Exception as e:
                    request['future'].set_exception(e)
                finally:
                    self._request_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                # If there's an error processing, mark the future as failed
                if request is not None and 'future' in request:
                    request['future'].set_exception(e)
    
    def _enqueue_request(self, func: Callable, *args, **kwargs):
        """Enqueue a request for sequential processing."""
        future = concurrent.futures.Future()
        request = {
            'func': func,
            'args': args,
            'kwargs': kwargs,
            'future': future
        }
        
        self._request_queue.put(request)
        return future
    
    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        """
        Generate text from a prompt (queued for sequential processing).
        
        Args:
            invocation: Normalized provider invocation.
            
        Returns:
            Normalized generation result.
            
        Raises:
            Exception: If generation fails
        """
        future = self._enqueue_request(
            self.llm_client.generate,
            invocation,
        )
        
        # Wait for the result with the specified timeout
        try:
            return future.result(timeout=invocation.timeout + 10)  # Add buffer for queue time
        except concurrent.futures.TimeoutError:
            raise RuntimeError(f"Request timed out after {invocation.timeout} seconds")
        except Exception as e:
            raise e
    
    def list_models(self) -> List[str]:
        """
        List available models (non-blocking, can run concurrently).
        
        Returns:
            List of model names
        """
        # Model listing doesn't need to be queued as it's a read operation
        return self.llm_client.list_models()
    
    def is_available(self) -> bool:
        """Check if the LLM service is available (non-blocking)."""
        # Availability check doesn't need to be queued
        return self.llm_client.is_available()
    
    def shutdown(self):
        """Shutdown the worker thread."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
