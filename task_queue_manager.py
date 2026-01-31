"""
Task Queue Manager - Python Queue + Threading
Handles parallel processing for multiple modules
"""

import queue
import threading
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class TaskStatus:
    """Task status tracking"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingTask:
    """Represents a single processing task"""
    
    def __init__(self, task_id: str, module_name: str, input_df: pd.DataFrame, 
                 model_key: str, user_id: str = "default"):
        self.task_id = task_id
        self.module_name = module_name
        self.input_df = input_df
        self.model_key = model_key
        self.user_id = user_id
        self.status = TaskStatus.PENDING
        self.results = []
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.total_records = len(input_df)
        self.processed_records = 0


class TaskQueueManager:
    """
    Manages parallel exception processing using Python Queue + Threading
    Supports multiple concurrent users/modules
    """
    
    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self.task_queue = queue.Queue()
        self.tasks: Dict[str, ProcessingTask] = {}
        self.workers: List[threading.Thread] = []
        self.shutdown_flag = threading.Event()
        self.lock = threading.Lock()
        
        # Start worker threads
        self._start_workers()
        
        logger.info(f"✅ TaskQueueManager initialized with {max_workers} workers")
    
    def _start_workers(self):
        """Start worker threads"""
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"Worker-{i+1}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
            logger.info(f"Started {worker.name}")
    
    def _worker_loop(self):
        """Worker thread main loop"""
        worker_name = threading.current_thread().name
        logger.info(f"{worker_name} started and waiting for tasks...")
        
        while not self.shutdown_flag.is_set():
            try:
                # Get task from queue (timeout to check shutdown flag)
                task = self.task_queue.get(timeout=1.0)
                
                if task is None:  # Poison pill
                    break
                
                logger.info(f"{worker_name} picked up task: {task.task_id} (Module: {task.module_name})")
                
                # Update task status
                with self.lock:
                    task.status = TaskStatus.PROCESSING
                    task.started_at = datetime.now()
                
                # Process the task
                self._process_task(task, worker_name)
                
                # Mark task as done in queue
                self.task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"{worker_name} error: {str(e)}", exc_info=True)
        
        logger.info(f"{worker_name} shutting down")
    
    def _process_task(self, task: ProcessingTask, worker_name: str):
        """Process a single task with batch streaming"""
        try:
            from exception_processor import EnhancedExceptionProcessor
            
            # Initialize processor
            processor = EnhancedExceptionProcessor(
                model_key=task.model_key,
                kb_manager=None  # Will use shared instance
            )
            
            # Process in batches
            batch_size = 2  # Process 2-3 exceptions at a time
            total_exceptions = len(task.input_df)
            
            for batch_start in range(0, total_exceptions, batch_size):
                if self.shutdown_flag.is_set():
                    logger.warning(f"{worker_name} - Task {task.task_id} interrupted by shutdown")
                    break
                
                batch_end = min(batch_start + batch_size, total_exceptions)
                batch_df = task.input_df.iloc[batch_start:batch_end]
                
                logger.info(f"{worker_name} - Processing batch {batch_start}-{batch_end} of {total_exceptions}")
                
                # Process batch
                batch_results = processor.process_exceptions(batch_df, task.module_name)
                
                # Store results
                with self.lock:
                    task.results.append(batch_results)
                    task.processed_records = batch_end
                
                logger.info(f"{worker_name} - Batch complete: {batch_end}/{total_exceptions} processed")
            
            # Mark task as completed
            with self.lock:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
            
            logger.info(f"✅ {worker_name} - Task {task.task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"❌ {worker_name} - Task {task.task_id} failed: {str(e)}", exc_info=True)
            with self.lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()
    
    def submit_task(self, module_name: str, input_df: pd.DataFrame, 
                   model_key: str, user_id: str = "default") -> str:
        """
        Submit a new processing task
        Returns: task_id for tracking
        """
        task_id = str(uuid.uuid4())
        
        task = ProcessingTask(
            task_id=task_id,
            module_name=module_name,
            input_df=input_df,
            model_key=model_key,
            user_id=user_id
        )
        
        with self.lock:
            self.tasks[task_id] = task
        
        self.task_queue.put(task)
        
        logger.info(f"📋 Task submitted: {task_id} (Module: {module_name}, Records: {len(input_df)})")
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a task"""
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            
            return {
                'task_id': task.task_id,
                'module_name': task.module_name,
                'status': task.status,
                'total_records': task.total_records,
                'processed_records': task.processed_records,
                'progress_percentage': (task.processed_records / task.total_records * 100) if task.total_records > 0 else 0,
                'created_at': task.created_at.isoformat(),
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'error': task.error
            }
    
    def get_task_results(self, task_id: str) -> Optional[List[pd.DataFrame]]:
        """Get results for a completed task"""
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            return task.results.copy()
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get status of all tasks"""
        with self.lock:
            return [self.get_task_status(task_id) for task_id in self.tasks.keys()]
    
    def shutdown(self):
        """Gracefully shutdown the task queue"""
        logger.info("Shutting down TaskQueueManager...")
        self.shutdown_flag.set()
        
        # Send poison pills to workers
        for _ in self.workers:
            self.task_queue.put(None)
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5.0)
        
        logger.info("TaskQueueManager shutdown complete")

    def get_worker_status(self) -> List[Dict[str, Any]]:
        """Get status of all workers"""
        worker_status = []
        with self.lock:
            for worker in self.workers:
                status = {
                    'name': worker.name,
                    'alive': worker.is_alive(),
                    'daemon': worker.daemon
                }
                worker_status.append(status)
        return worker_status

    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self.task_queue.qsize()

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get all currently processing tasks"""
        with self.lock:
            active = []
            for task_id, task in self.tasks.items():
                if task.status == TaskStatus.PROCESSING:
                    active.append({
                        'task_id': task_id,
                        'module_name': task.module_name,
                        'user_id': task.user_id,
                        'total_records': task.total_records,
                        'processed_records': task.processed_records,
                        'progress': (task.processed_records / task.total_records * 100) if task.total_records > 0 else 0,
                        'started_at': task.started_at.isoformat() if task.started_at else None,
                        'elapsed_seconds': (datetime.now() - task.started_at).total_seconds() if task.started_at else 0
                    })
            return active

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending tasks"""
        with self.lock:
            pending = []
            for task_id, task in self.tasks.items():
                if task.status == TaskStatus.PENDING:
                    pending.append({
                        'task_id': task_id,
                        'module_name': task.module_name,
                        'user_id': task.user_id,
                        'total_records': task.total_records,
                        'created_at': task.created_at.isoformat()
                    })
            return pending

    def get_completed_tasks(self) -> List[Dict[str, Any]]:
        """Get all completed tasks"""
        with self.lock:
            completed = []
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    completed.append({
                        'task_id': task_id,
                        'module_name': task.module_name,
                        'user_id': task.user_id,
                        'status': task.status,
                        'total_records': task.total_records,
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                        'error': task.error,
                        'processing_time': (task.completed_at - task.started_at).total_seconds() if (task.completed_at and task.started_at) else 0
                    })
            return completed

    def get_system_stats(self) -> Dict[str, Any]:
        """Get overall system statistics"""
        with self.lock:
            total_tasks = len(self.tasks)
            processing = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PROCESSING)
            pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
            completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
            
            total_records_processed = sum(
                t.processed_records for t in self.tasks.values() 
                if t.status in [TaskStatus.PROCESSING, TaskStatus.COMPLETED]
            )
            
            return {
                'total_tasks': total_tasks,
                'processing': processing,
                'pending': pending,
                'completed': completed,
                'failed': failed,
                'queue_size': self.task_queue.qsize(),
                'active_workers': sum(1 for w in self.workers if w.is_alive()),
                'total_workers': len(self.workers),
                'total_records_processed': total_records_processed
            }


# Global instance
_task_manager_instance = None


def get_task_manager() -> TaskQueueManager:
    """Get singleton instance of TaskQueueManager"""
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskQueueManager(max_workers=2)
    return _task_manager_instance
