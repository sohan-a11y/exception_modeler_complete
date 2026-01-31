"""
Code Repository Manager - V1.0
Intelligent code indexing and retrieval system
Indexes codebase, retrieves relevant code snippets based on stack traces
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import hashlib
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class CodeRepositoryManager:
    """
    Manages code repository indexing and retrieval
    - Indexes code files into vector database
    - Retrieves relevant code based on stack traces
    - Keeps everything local and private
    """
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        '.cs',      # C#
        '.py',      # Python
        '.java',    # Java
        '.js',      # JavaScript
        '.ts',      # TypeScript
        '.cpp',     # C++
        '.c',       # C
        '.h',       # Header files
        '.sql',     # SQL
        '.vb',      # Visual Basic
        '.php',     # PHP
        '.rb',      # Ruby
        '.go',      # Go
    }
    
    # Directories to skip
    SKIP_DIRECTORIES = {
        'node_modules', 'bin', 'obj', '.git', '.vs', 
        '__pycache__', 'venv', '.venv', 'packages',
        'Debug', 'Release', '.idea', 'build', 'dist'
    }
    
    def __init__(self, repo_path: str, chroma_dir: Path):
        self.repo_path = Path(repo_path)
        self.chroma_dir = chroma_dir / "code_repository"
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client for code
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Load embedding model
        logger.info("Loading embedding model for code indexing...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Code collection
        self.code_collection = None
        self.indexed_files: Dict[str, Dict[str, Any]] = {}
        
        # Load or create collection
        self._load_or_create_collection()
        
        logger.info(f"✅ Code Repository Manager initialized")
        logger.info(f"Repository: {self.repo_path}")
        logger.info(f"Indexed files: {len(self.indexed_files)}")
    
    def _load_or_create_collection(self):
        """Load existing collection or create new one"""
        try:
            self.code_collection = self.client.get_collection("code_repository")
            count = self.code_collection.count()
            logger.info(f"Loaded existing code collection with {count} entries")
            
            # Load indexed files metadata
            self._load_indexed_files_metadata()
            
        except:
            logger.info("Creating new code collection...")
            self.code_collection = self.client.create_collection(
                name="code_repository",
                metadata={"version": "1.0"}
            )
    
    def _load_indexed_files_metadata(self):
        """Load metadata about indexed files"""
        try:
            metadata_file = self.chroma_dir / "indexed_files.json"
            if metadata_file.exists():
                import json
                with open(metadata_file, 'r') as f:
                    self.indexed_files = json.load(f)
                logger.info(f"Loaded metadata for {len(self.indexed_files)} indexed files")
        except Exception as e:
            logger.warning(f"Could not load indexed files metadata: {str(e)}")
    
    def _save_indexed_files_metadata(self):
        """Save metadata about indexed files"""
        try:
            import json
            metadata_file = self.chroma_dir / "indexed_files.json"
            with open(metadata_file, 'w') as f:
                json.dump(self.indexed_files, f, indent=2, default=str)
            logger.info(f"Saved metadata for {len(self.indexed_files)} indexed files")
        except Exception as e:
            logger.error(f"Could not save indexed files metadata: {str(e)}")
    
    def index_repository(self, force_reindex: bool = False) -> Dict[str, Any]:
        """
        Index the entire repository
        
        Args:
            force_reindex: If True, re-index all files even if already indexed
        
        Returns:
            Statistics about indexing
        """
        logger.info("="*80)
        logger.info("CODE REPOSITORY INDEXING - START")
        logger.info("="*80)
        logger.info(f"Repository path: {self.repo_path}")
        logger.info(f"Force reindex: {force_reindex}")
        
        if not self.repo_path.exists():
            logger.error(f"Repository path does not exist: {self.repo_path}")
            return {
                'status': 'error',
                'message': f'Repository path does not exist: {self.repo_path}',
                'files_indexed': 0
            }
        
        stats = {
            'total_files_found': 0,
            'files_indexed': 0,
            'files_skipped': 0,
            'files_updated': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        
        # Collect all code files
        code_files = self._collect_code_files()
        stats['total_files_found'] = len(code_files)
        
        logger.info(f"Found {len(code_files)} code files to process")
        
        # Index each file
        for file_path in code_files:
            try:
                # Check if file needs indexing
                if not force_reindex and self._is_file_indexed(file_path):
                    stats['files_skipped'] += 1
                    continue
                
                # Index the file
                success = self._index_file(file_path)
                
                if success:
                    stats['files_indexed'] += 1
                    if str(file_path) in self.indexed_files:
                        stats['files_updated'] += 1
                else:
                    stats['errors'] += 1
                
                # Log progress every 100 files
                if (stats['files_indexed'] + stats['files_skipped']) % 100 == 0:
                    logger.info(f"Progress: {stats['files_indexed']} indexed, {stats['files_skipped']} skipped")
                
            except Exception as e:
                logger.error(f"Error indexing {file_path}: {str(e)}")
                stats['errors'] += 1
        
        # Save metadata
        self._save_indexed_files_metadata()
        
        stats['end_time'] = datetime.now()
        stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
        
        logger.info("="*80)
        logger.info("CODE REPOSITORY INDEXING - COMPLETE")
        logger.info(f"Total files found: {stats['total_files_found']}")
        logger.info(f"Files indexed: {stats['files_indexed']}")
        logger.info(f"Files skipped: {stats['files_skipped']}")
        logger.info(f"Files updated: {stats['files_updated']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info(f"Duration: {stats['duration_seconds']:.1f} seconds")
        logger.info("="*80)
        
        return stats
    
    def _collect_code_files(self) -> List[Path]:
        """Collect all code files from repository"""
        code_files = []
        
        for root, dirs, files in os.walk(self.repo_path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRECTORIES]
            
            for file in files:
                file_path = Path(root) / file
                
                # Check if file extension is supported
                if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    code_files.append(file_path)
        
        return code_files
    
    def _is_file_indexed(self, file_path: Path) -> bool:
        """Check if file is already indexed and up-to-date"""
        file_key = str(file_path.relative_to(self.repo_path))
        
        if file_key not in self.indexed_files:
            return False
        
        # Check if file has been modified since indexing
        current_mtime = file_path.stat().st_mtime
        indexed_mtime = self.indexed_files[file_key].get('mtime', 0)
        
        return current_mtime <= indexed_mtime
    
    def _index_file(self, file_path: Path) -> bool:
        """
        Index a single code file
        Strategy: Split into chunks (functions/classes) for better retrieval
        """
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if not content.strip():
                return False
            
            # Get relative path for storage
            relative_path = str(file_path.relative_to(self.repo_path))
            
            # Split content into chunks (by functions/classes)
            chunks = self._split_code_into_chunks(content, file_path.suffix)
            
            if not chunks:
                # If splitting fails, use entire file as one chunk
                chunks = [{'content': content, 'line_start': 1, 'line_end': len(content.split('\n'))}]
            
            # Create embeddings and store
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{relative_path}__chunk_{idx}"
                
                # Create embedding
                embedding = self.embedding_model.encode([chunk['content']], show_progress_bar=False)[0]
                
                # Store in ChromaDB
                self.code_collection.add(
                    documents=[chunk['content']],
                    embeddings=[embedding.tolist()],
                    metadatas=[{
                        'file_path': relative_path,
                        'full_path': str(file_path),
                        'file_extension': file_path.suffix,
                        'line_start': chunk['line_start'],
                        'line_end': chunk['line_end'],
                        'chunk_index': idx,
                        'indexed_at': datetime.now().isoformat()
                    }],
                    ids=[chunk_id]
                )
            
            # Update indexed files metadata
            self.indexed_files[relative_path] = {
                'full_path': str(file_path),
                'mtime': file_path.stat().st_mtime,
                'indexed_at': datetime.now().isoformat(),
                'chunks': len(chunks),
                'size_bytes': len(content)
            }
            
            return True
            
        except Exception as e:
            logger.error(f"Error indexing file {file_path}: {str(e)}")
            return False
    
    def _split_code_into_chunks(self, content: str, file_extension: str) -> List[Dict[str, Any]]:
        """
        Split code into logical chunks (functions, classes, etc.)
        This is a simple implementation - can be enhanced with AST parsing
        """
        chunks = []
        lines = content.split('\n')
        
        # Simple heuristic-based chunking
        current_chunk_lines = []
        current_chunk_start = 1
        
        for line_num, line in enumerate(lines, 1):
            current_chunk_lines.append(line)
            
            # Check for chunk boundaries (simple heuristics)
            stripped = line.strip()
            
            # Chunk size limit: 100 lines or logical boundaries
            if len(current_chunk_lines) >= 100 or (
                stripped.startswith('}') or 
                stripped.startswith('end') or
                stripped.startswith('End Sub') or
                stripped.startswith('End Function')
            ):
                # Create chunk
                chunk_content = '\n'.join(current_chunk_lines)
                if chunk_content.strip():
                    chunks.append({
                        'content': chunk_content,
                        'line_start': current_chunk_start,
                        'line_end': line_num
                    })
                
                # Start new chunk
                current_chunk_lines = []
                current_chunk_start = line_num + 1
        
        # Add remaining lines as final chunk
        if current_chunk_lines:
            chunk_content = '\n'.join(current_chunk_lines)
            if chunk_content.strip():
                chunks.append({
                    'content': chunk_content,
                    'line_start': current_chunk_start,
                    'line_end': len(lines)
                })
        
        return chunks
    
    def retrieve_code_by_stack_trace(self, stack_trace: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant code files based on stack trace
        
        Args:
            stack_trace: Stack trace from exception
            top_k: Number of relevant files to retrieve
        
        Returns:
            List of code snippets with metadata
        """
        from stack_trace_parser import StackTraceParser
        
        parser = StackTraceParser()
        parsed = parser.parse_stack_trace(stack_trace)
        
        code_snippets = []
        
        # Strategy 1: Direct file path matching
        for frame in parsed['frames']:
            file_path = frame['file_path']
            line_number = frame['line_number']
            
            if file_path:
                snippet = self._retrieve_code_by_file_path(file_path, line_number)
                if snippet:
                    snippet['match_type'] = 'direct'
                    code_snippets.append(snippet)
        
        # Strategy 2: Semantic search if not enough direct matches
        if len(code_snippets) < top_k:
            semantic_results = self._retrieve_code_by_semantic_search(stack_trace, top_k - len(code_snippets))
            for result in semantic_results:
                result['match_type'] = 'semantic'
                code_snippets.append(result)
        
        # Limit to top_k
        code_snippets = code_snippets[:top_k]
        
        logger.info(f"Retrieved {len(code_snippets)} code snippets for stack trace analysis")
        
        return code_snippets
    
    def _retrieve_code_by_file_path(self, file_path: str, line_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieve code by exact file path"""
        try:
            # Normalize file path
            file_path = file_path.replace('\\', '/')
            
            # Search in indexed files
            for indexed_path, metadata in self.indexed_files.items():
                if file_path.lower() in indexed_path.lower():
                    # Found the file - retrieve the relevant chunk
                    
                    # Query ChromaDB for chunks from this file
                    results = self.code_collection.get(
                        where={"file_path": indexed_path}
                    )
                    
                    if results and results['documents']:
                        # Find chunk containing the line number
                        best_chunk_idx = 0
                        
                        if line_number:
                            for idx, chunk_metadata in enumerate(results['metadatas']):
                                if chunk_metadata['line_start'] <= line_number <= chunk_metadata['line_end']:
                                    best_chunk_idx = idx
                                    break
                        
                        return {
                            'file_path': indexed_path,
                            'full_path': metadata['full_path'],
                            'content': results['documents'][best_chunk_idx],
                            'line_start': results['metadatas'][best_chunk_idx]['line_start'],
                            'line_end': results['metadatas'][best_chunk_idx]['line_end'],
                            'target_line': line_number
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving code by file path: {str(e)}")
            return None
    
    def _retrieve_code_by_semantic_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve code using semantic search"""
        try:
            # Create query embedding
            query_embedding = self.embedding_model.encode([query], show_progress_bar=False)[0]
            
            # Search ChromaDB
            results = self.code_collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=top_k
            )
            
            snippets = []
            
            if results and results['documents'] and len(results['documents'][0]) > 0:
                for i in range(len(results['documents'][0])):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i] if 'distances' in results else 0.5
                    similarity = max(0, 1.0 - distance)
                    
                    snippets.append({
                        'file_path': metadata['file_path'],
                        'full_path': metadata['full_path'],
                        'content': results['documents'][0][i],
                        'line_start': metadata['line_start'],
                        'line_end': metadata['line_end'],
                        'similarity': similarity
                    })
            
            return snippets
            
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            return []
    
    def get_repository_stats(self) -> Dict[str, Any]:
        """Get statistics about indexed repository"""
        return {
            'repository_path': str(self.repo_path),
            'indexed_files': len(self.indexed_files),
            'total_chunks': self.code_collection.count() if self.code_collection else 0,
            'last_indexed': max([f['indexed_at'] for f in self.indexed_files.values()]) if self.indexed_files else None,
            'supported_extensions': list(self.SUPPORTED_EXTENSIONS)
        }
    
    def search_code(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search code repository with natural language query
        
        Args:
            query: Natural language search query
            top_k: Number of results to return
        
        Returns:
            List of matching code snippets
        """
        return self._retrieve_code_by_semantic_search(query, top_k)


if __name__ == "__main__":
    # Test the code repository manager
    repo_manager = CodeRepositoryManager(
        repo_path="C:/Source/repos/code",
        chroma_dir=Path("data/chromadb")
    )
    
    print("\n✅ Code Repository Manager initialized successfully!")
    print(f"Repository: {repo_manager.repo_path}")
    
    # Get stats
    stats = repo_manager.get_repository_stats()
    print(f"\nRepository Stats:")
    print(f"  Indexed files: {stats['indexed_files']}")
    print(f"  Total chunks: {stats['total_chunks']}")
