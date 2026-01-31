"""
Knowledge Base Manager Module - V5.0 Production
With EVENT_INFORMATION JSON parsing and enhanced matching
"""

import pandas as pd
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Any, Optional, Set
import logging
from pathlib import Path
import hashlib
import json
import re
import config

logger = logging.getLogger(__name__)


class MultiModuleKBManager:
    """
    Enhanced KB manager with EVENT_INFORMATION JSON parsing
    Uses full exception details for superior matching accuracy
    """
    
    def __init__(self, chroma_dir: Path):
        self.chroma_dir = chroma_dir
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Load embedding model
        logger.info("Loading embedding model for KB vectorization...")
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
        
        # Store module collections and metadata
        self.module_collections = {}
        self.module_metadata = {}
        
        # Track unique entries per module for deduplication
        self.module_signatures: Dict[str, Set[str]] = {}
        
        # Load existing collections from ChromaDB
        self._load_existing_collections()
        
        logger.info("Enhanced KB Manager V5.0 initialized with EVENT_INFORMATION support")
    
    def _parse_json_safely(self, json_str: str) -> Optional[Dict]:
        """Safely parse JSON string with auto-fix for missing opening brace and closing braces"""
        if not json_str or pd.isna(json_str):
            return None
        
        try:
            json_str = str(json_str).strip()
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                # Clean and retry
                json_str = json_str.replace('\ufeff', '')
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    # [2025-12-04] FIX: Auto-fix missing opening brace and closing braces
                    # Many KB files have malformed JSON:
                    # 1. Missing opening brace: "Exception": instead of {"Exception":
                    # 2. Missing closing braces at the end
                    # This permanently fixes the parsing issue for 156+ records
                    if json_str.startswith('"Exception":') or json_str.strip().startswith('"Exception":'):
                        json_str = json_str.strip()
                        
                        # Add opening brace
                        json_str = '{' + json_str
                        
                        # Count braces to determine if we need closing braces
                        open_count = json_str.count('{')
                        close_count = json_str.count('}')
                        
                        # Add missing closing braces
                        while open_count > close_count:
                            json_str = json_str + '}'
                            close_count += 1
                        
                        logger.debug(f"Auto-fixed missing braces in JSON")
                        return json.loads(json_str)
                    else:
                        # Don't log warning here - regex fallback will try next
                        return None
                except:
                    # Don't log warning here - regex fallback will try next
                    return None
    
    def _extract_exception_from_event_info(self, event_info_str: str) -> Dict[str, Any]:
        """Extract exception details from EVENT_INFORMATION JSON with fallback regex extraction"""
        parsed = self._parse_json_safely(event_info_str)
        
        if parsed and isinstance(parsed, dict):
            # Successfully parsed JSON
            exception_data = parsed.get('Exception', {})
            
            return {
                'exception_type': exception_data.get('Exception Type', ''),
                'message': exception_data.get('Message', ''),
                'stack_trace': exception_data.get('StackTrace', ''),
                'inner_exception_type': exception_data.get('InnerException', {}).get('Exception Type', ''),
                'inner_exception_message': exception_data.get('InnerException', {}).get('Message', ''),
                'error_code': exception_data.get('InnerException', {}).get('Code', 
                                               exception_data.get('InnerException', {}).get('ErrorCode', ''))
            }
        else:
            # [2025-12-04] FALLBACK: Extract from malformed JSON using regex
            # Many KB rows have severely malformed JSON that can't be parsed
            # But we can still extract key fields using regex patterns
            
            result = {
                'exception_type': '',
                'message': '',
                'stack_trace': '',
                'inner_exception_type': '',
                'inner_exception_message': '',
                'error_code': ''
            }
            
            if not event_info_str or pd.isna(event_info_str):
                logger.warning(f"EVENT_INFORMATION is empty or NaN")
                return result
            
            event_str = str(event_info_str)
            
            # Extract Exception Type
            match = re.search(r'"Exception Type":\s*"([^"]+)"', event_str)
            if match:
                result['exception_type'] = match.group(1)
            
            # Extract Message
            match = re.search(r'"Message":\s*"([^"]+)"', event_str)
            if match:
                result['message'] = match.group(1)
            
            # Extract StackTrace (if properly quoted)
            match = re.search(r'"StackTrace":\s*"([^"]+)"', event_str, re.DOTALL)
            if match:
                result['stack_trace'] = match.group(1)[:1000]  # Limit length
            
            # Extract Inner Exception Type
            match = re.search(r'"InnerException".*?"Exception Type":\s*"([^"]+)"', event_str, re.DOTALL)
            if match:
                result['inner_exception_type'] = match.group(1)
            
            # Extract Inner Exception Message
            match = re.search(r'"InnerException".*?"Message":\s*"([^"]+)"', event_str, re.DOTALL)
            if match:
                result['inner_exception_message'] = match.group(1)
            
            # Extract Error Code
            match = re.search(r'"(?:Code|ErrorCode)":\s*"([^"]+)"', event_str)
            if match:
                result['error_code'] = match.group(1)
            
            if not result['exception_type']:
                logger.warning(f"Failed to extract exception_type even with regex fallback. First 250 chars: {event_str[:250]}")
            
            return result
    
    # [2025-12-03] FIX 1: Normalize KB resolutions at storage time
    # Date: 2025-12-03 15:14 UTC-06:00
    # Reason: KB stores free-text resolutions like "Message Can be purged" which causes UNDEFINED results
    # Purpose: Convert all KB resolutions to standard format (PURGE/REPROCESS/INVESTIGATE) at storage time
    # Impact: This is the ROOT CAUSE FIX - ensures KB always has valid resolutions
    def _normalize_resolution(self, resolution_str: str) -> str:
        """Normalize resolution to standard format (PURGE/REPROCESS/INVESTIGATE)"""
        if not resolution_str or pd.isna(resolution_str):
            logger.warning(f"Empty resolution provided, defaulting to UNDEFINED")
            return 'UNDEFINED'
        
        res_upper = str(resolution_str).upper().strip()
        logger.debug(f"Normalizing resolution: '{resolution_str}' -> '{res_upper}'")
        
        # Check for PURGE keywords
        if any(keyword in res_upper for keyword in ['PURGE', 'DELETE', 'REMOVE', 'DISCARD']):
            logger.info(f"✅ Normalized '{resolution_str}' -> 'PURGE'")
            return 'PURGE'
        
        # Check for REPROCESS keywords
        elif any(keyword in res_upper for keyword in ['REPROCESS', 'RETRY', 'RESEND', 'RE-PROCESS']):
            logger.info(f"✅ Normalized '{resolution_str}' -> 'REPROCESS'")
            return 'REPROCESS'
        
        # Check for INVESTIGATE/ESCALATE keywords
        elif any(keyword in res_upper for keyword in ['INVESTIGATE', 'ESCALATE', 'REVIEW', 'ANALYZE', 'CHECK']):
            logger.info(f"✅ Normalized '{resolution_str}' -> 'INVESTIGATE'")
            return 'INVESTIGATE'
        
        else:
            logger.warning(f"⚠️ Could not normalize resolution '{resolution_str}' - defaulting to UNDEFINED")
            return 'UNDEFINED'
    
    def _load_existing_collections(self):
        """Load existing collections from ChromaDB on initialization"""
        try:
            existing_collections = self.client.list_collections()
            
            for collection in existing_collections:
                if collection.name.startswith(config.CHROMA_COLLECTION_PREFIX):
                    metadata = collection.metadata
                    
                    if metadata and 'module' in metadata:
                        module_name = metadata['module']
                    elif metadata and 'original_module_name' in metadata:
                        module_name = metadata['original_module_name']
                    else:
                        module_name_from_collection = collection.name.replace(config.CHROMA_COLLECTION_PREFIX, "")
                        module_name = module_name_from_collection.replace("_", " ").title()
                    
                    self.module_collections[module_name] = collection
                    
                    count = collection.count()
                    self.module_metadata[module_name] = {
                        'entries_count': count,
                        'collection_name': collection.name,
                        'loaded_from_disk': True
                    }
                    
                    self.module_signatures[module_name] = set()
                    
                    logger.info(f"Loaded KB collection: '{collection.name}' for '{module_name}' ({count} entries)")
            
            if self.module_collections:
                logger.info(f"Successfully loaded {len(self.module_collections)} KB collections")
            else:
                logger.info("No existing KB collections found")
                
        except Exception as e:
            logger.warning(f"Could not load existing collections: {str(e)}")
    
    def load_or_append_knowledge_base(self, kb_df: pd.DataFrame, module_name: str, 
                                     append_mode: bool = False) -> Dict[str, Any]:
        """Load or append knowledge base for a module"""
        try:
            logger.info(f"{'Appending to' if append_mode else 'Loading'} knowledge base for module: {module_name}")
            
            kb_df = self._normalize_kb_columns(kb_df)
            
            # Validate EVENT_INFORMATION presence
            if 'EVENT_INFORMATION' not in kb_df.columns:
                logger.error("EVENT_INFORMATION column missing in KB file!")
                return {
                    'status': 'error',
                    'message': 'EVENT_INFORMATION is required in KB files',
                    'entries': 0
                }
            
            if kb_df.empty:
                logger.warning(f"KB dataframe is empty for module: {module_name}")
                return {
                    'status': 'warning',
                    'message': f'KB is empty for module {module_name}',
                    'entries': 0
                }
            
            collection_name = f"{config.CHROMA_COLLECTION_PREFIX}{module_name.lower().replace(' ', '_')}"
            
            if append_mode and module_name in self.module_collections:
                logger.info(f"Appending to existing KB for {module_name}...")
                result = self._append_to_kb(kb_df, module_name, collection_name)
            else:
                logger.info(f"Creating fresh KB for {module_name}...")
                result = self._create_fresh_kb(kb_df, module_name, collection_name)
            
            return result
            
        except Exception as e:
            logger.error(f"Error loading/appending KB: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'entries': 0
            }
    
    def _create_fresh_kb(self, kb_df: pd.DataFrame, module_name: str, 
                        collection_name: str) -> Dict[str, Any]:
        """Create fresh knowledge base (replace existing)"""
        
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted existing collection: {collection_name}")
        except:
            pass
        
        collection = self.client.create_collection(
            name=collection_name,
            metadata={"module": module_name, "version": "5.0", "original_module_name": module_name}
        )
        
        documents = []
        metadatas = []
        ids = []
        signatures = set()
        duplicates_removed = 0
        skipped_no_event_info = 0
        
        for idx, row in kb_df.iterrows():
            # CRITICAL: Skip if EVENT_INFORMATION missing or empty
            event_info = row.get('EVENT_INFORMATION', '')
            if not event_info or pd.isna(event_info):
                logger.warning(f"Skipping KB entry {idx}: EVENT_INFORMATION missing")
                skipped_no_event_info += 1
                continue
            
            # Parse EVENT_INFORMATION
            exception_details = self._extract_exception_from_event_info(event_info)
            if not exception_details or not exception_details.get('exception_type'):
                logger.warning(f"Skipping KB entry {idx}: Could not extract exception_type from EVENT_INFORMATION")
                logger.debug(f"  EVENT_INFORMATION preview: {str(event_info)[:200]}")
                skipped_no_event_info += 1
                continue
            
            signature = self._create_kb_signature(row, exception_details)
            
            if signature in signatures:
                logger.debug(f"Skipping duplicate KB entry: {signature[:50]}")
                duplicates_removed += 1
                continue
            
            signatures.add(signature)
            
            # Create rich document with EVENT_INFORMATION details (60% weight)
            doc_text = self._create_kb_document_text(row, exception_details)
            documents.append(doc_text)
            
            # Store metadata with parsed exception details
            # [2025-12-03] FIX 1: Apply resolution normalization at storage time
            # Date: 2025-12-03 14:42 UTC-06:00
            # Purpose: Store only standard resolutions (PURGE/REPROCESS/INVESTIGATE) in KB
            raw_resolution = str(row.get('Resolution', ''))
            normalized_resolution = self._normalize_resolution(raw_resolution)
            logger.debug(f"KB Entry {idx}: Raw='{raw_resolution}' -> Normalized='{normalized_resolution}'")
            
            metadata = {
                'module': module_name,
                'exception_type': exception_details.get('exception_type', ''),
                'resolution': normalized_resolution,  # ✅ Store normalized resolution
                'root_cause': str(row.get('Root_Cause', row.get('Explanation', ''))),
                'action': str(row.get('Action', ''))[:300],
                'stack_trace': exception_details.get('stack_trace', ''),
                'inner_exception_type': exception_details.get('inner_exception_type', ''),
                'inner_exception_message': exception_details.get('inner_exception_message', ''),
                'error_code': str(exception_details.get('error_code', '')),
                'process_name': str(row.get('ProcessNameColumn', row.get('Process_Name', '')))
            }
            metadatas.append(metadata)
            
            ids.append(f"{module_name}_{idx}_{signature[:8]}")
        
        if not documents:
            logger.warning(f"No valid KB entries for module: {module_name}")
            return {
                'status': 'warning',
                'message': f'No valid KB entries for {module_name} (EVENT_INFORMATION missing/invalid in all entries)',
                'entries': 0,
                'skipped_no_event_info': skipped_no_event_info
            }
        
        logger.info(f"Generating embeddings for {len(documents)} KB entries...")
        embeddings = self.embedding_model.encode(documents, show_progress_bar=False)
        
        collection.add(
            documents=documents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
            ids=ids
        )
        
        self.module_collections[module_name] = collection
        self.module_signatures[module_name] = signatures
        self.module_metadata[module_name] = {
            'entries_count': len(documents),
            'collection_name': collection_name,
            'unique_signatures': len(signatures),
            'duplicates_removed': duplicates_removed,
            'skipped_no_event_info': skipped_no_event_info,
            'last_updated': pd.Timestamp.now().isoformat()
        }
        
        logger.info(f"="*80)
        logger.info(f"KB LOADING SUMMARY for {module_name}")
        logger.info(f"="*80)
        logger.info(f"Total rows in CSV: {len(kb_df)}")
        logger.info(f"Unique entries loaded: {len(documents)}")
        logger.info(f"Duplicates filtered: {duplicates_removed}")
        if skipped_no_event_info > 0:
            logger.warning(f"Skipped (parsing failed): {skipped_no_event_info}")
        logger.info(f"="*80)
        
        return {
            'status': 'success',
            'message': f'KB created for {module_name}',
            'entries': len(documents),
            'duplicates_removed': duplicates_removed,
            'skipped_no_event_info': skipped_no_event_info
        }
    
    def _append_to_kb(self, new_kb_df: pd.DataFrame, module_name: str, 
                     collection_name: str) -> Dict[str, Any]:
        """Append new KB entries with deduplication"""
        
        collection = self.module_collections[module_name]
        existing_signatures = self.module_signatures[module_name]
        
        new_entries = 0
        duplicates_skipped = 0
        skipped_no_event_info = 0
        
        documents_to_add = []
        embeddings_to_add = []
        metadatas_to_add = []
        ids_to_add = []
        
        for idx, row in new_kb_df.iterrows():
            # Skip if EVENT_INFORMATION missing
            event_info = row.get('EVENT_INFORMATION', '')
            if not event_info or pd.isna(event_info):
                logger.warning(f"Skipping KB entry {idx}: EVENT_INFORMATION missing")
                skipped_no_event_info += 1
                continue
            
            exception_details = self._extract_exception_from_event_info(event_info)
            if not exception_details or not exception_details.get('exception_type'):
                logger.warning(f"Skipping KB entry {idx}: Could not parse EVENT_INFORMATION")
                skipped_no_event_info += 1
                continue
            
            signature = self._create_kb_signature(row, exception_details)
            
            if signature in existing_signatures:
                logger.debug(f"Skipping duplicate entry: {signature}")
                duplicates_skipped += 1
                continue
            
            existing_signatures.add(signature)
            new_entries += 1
            
            doc_text = self._create_kb_document_text(row, exception_details)
            documents_to_add.append(doc_text)
            
            # [2025-12-03] FIX 1: Apply resolution normalization for appended entries
            # Date: 2025-12-03 14:42 UTC-06:00
            raw_resolution = str(row.get('Resolution', ''))
            normalized_resolution = self._normalize_resolution(raw_resolution)
            logger.debug(f"KB Append {idx}: Raw='{raw_resolution}' -> Normalized='{normalized_resolution}'")
            
            metadata = {
                'module': module_name,
                'exception_type': exception_details.get('exception_type', ''),
                'resolution': normalized_resolution,  # ✅ Store normalized resolution
                'root_cause': str(row.get('Root_Cause', row.get('Explanation', ''))),
                'action': str(row.get('Action', ''))[:300],
                'stack_trace': exception_details.get('stack_trace', ''),
                'inner_exception_type': exception_details.get('inner_exception_type', ''),
                'error_code': str(exception_details.get('error_code', '')),
                'added_via': 'append',
                'added_at': pd.Timestamp.now().isoformat()
            }
            metadatas_to_add.append(metadata)
            
            ids_to_add.append(f"{module_name}_append_{signature[:12]}")
        
        if documents_to_add:
            logger.info(f"Generating embeddings for {len(documents_to_add)} new entries...")
            embeddings_list = self.embedding_model.encode(documents_to_add, show_progress_bar=False)
            
            collection.add(
                documents=documents_to_add,
                embeddings=embeddings_list.tolist(),
                metadatas=metadatas_to_add,
                ids=ids_to_add
            )
            
            self.module_signatures[module_name] = existing_signatures
            if module_name in self.module_metadata:
                self.module_metadata[module_name]['entries_count'] += new_entries
                self.module_metadata[module_name]['unique_signatures'] = len(existing_signatures)
                self.module_metadata[module_name]['last_updated'] = pd.Timestamp.now().isoformat()
        
        logger.info(f"✅ Appended to KB for {module_name}: {new_entries} new entries")
        if skipped_no_event_info > 0:
            logger.warning(f"⚠️ Skipped {skipped_no_event_info} entries due to missing EVENT_INFORMATION")
        
        return {
            'status': 'success',
            'message': f'Appended to KB for {module_name}',
            'entries': new_entries,
            'duplicates_skipped': duplicates_skipped,
            'skipped_no_event_info': skipped_no_event_info,
            'total_entries': self.module_metadata[module_name]['entries_count']
        }
    
    def _normalize_kb_columns(self, kb_df: pd.DataFrame) -> pd.DataFrame:
        """Map incoming Excel/CSV columns to internal names using config.KB_COLUMNS"""
        def _coalesce_columns(df, target_col, source_cols):
            """Helper to combine multiple source columns into one target"""
            if target_col not in df.columns:
                for sc in source_cols:
                    if sc in df.columns:
                        df[target_col] = df[sc]
                        break
            return df
        
        # Use configurable column mappings from config
        for excel_col, internal_col in config.KB_COLUMNS.items():
            if excel_col in kb_df.columns and excel_col != internal_col:
                if internal_col not in kb_df.columns:
                    kb_df[internal_col] = kb_df[excel_col]
        
        # EVENT_INFORMATION (REQUIRED)
        kb_df = _coalesce_columns(kb_df, 'EVENT_INFORMATION', ['EVENT_INFORMATION', 'Event_Information'])
        
        # Exception Type
        kb_df = _coalesce_columns(kb_df, 'Exception_Type', ['ExceptionType', 'Exception_Type', 'exception_type'])
        
        # Exception Message
        kb_df = _coalesce_columns(kb_df, 'Exception_Message', ['Message', 'ExceptionTemplate', 'Exception_Message'])
        
        # Root Cause - check multiple possible column names
        # [2025-11-22] Added 'Summary' to support KB files with Summary column
        kb_df = _coalesce_columns(kb_df, 'Root_Cause', ['Root_Cause', 'RootCause_text', 'Summary', 'Explanation'])
        
        # Resolution  
        kb_df = _coalesce_columns(kb_df, 'Resolution', ['Resolution'])
        
        # Action - check multiple possible column names
        # [2025-11-22] Added 'Suggested Step' to support KB files with this column name
        # Date: 2025-11-22
        # Reason: KB file uses 'Suggested Step' column but code was looking for 'Action'
        # Purpose: Map 'Suggested Step' to 'Action' so metadata extraction works correctly
        kb_df = _coalesce_columns(kb_df, 'Action', ['Action', 'Suggested Step', 'Suggested_Action', 'suggested_step'])
        
        # Stack Trace
        kb_df = _coalesce_columns(kb_df, 'Stack_Trace', ['StackTrace', 'Stack_Trace'])
        
        # Remove duplicate columns
        if kb_df.columns.duplicated().any():
            kb_df = kb_df.loc[:, ~kb_df.columns.duplicated(keep='first')]
        
        return kb_df
    
    def _create_kb_document_text(self, row: pd.Series, exception_details: Dict[str, Any]) -> str:
        """
        Create rich document text with EVENT_INFORMATION details (60% weight)
        This is the primary matching content
        """
        parts = []
        
        # PRIMARY: Exception details from EVENT_INFORMATION (60% weight)
        parts.append("=== EVENT INFORMATION (PRIMARY) ===")
        
        exc_type = exception_details.get('exception_type', '')
        if exc_type:
            parts.append(f"Exception Type: {exc_type}")
        
        message = exception_details.get('message', '')
        if message:
            parts.append(f"Message: {message}")
        
        stack_trace = exception_details.get('stack_trace', '')
        if stack_trace:
            # Include more stack trace detail for better matching
            parts.append(f"Stack Trace: {stack_trace}")
        
        inner_exc_type = exception_details.get('inner_exception_type', '')
        if inner_exc_type:
            parts.append(f"Inner Exception: {inner_exc_type}")
        
        inner_exc_msg = exception_details.get('inner_exception_message', '')
        if inner_exc_msg:
            parts.append(f"Inner Message: {inner_exc_msg}")
        
        error_code = exception_details.get('error_code', '')
        if error_code:
            parts.append(f"Error Code: {error_code}")
        
        # SECONDARY: Other KB fields (40% weight)
        parts.append("\n=== RESOLUTION CONTEXT (SECONDARY) ===")
        
        resolution = row.get('Resolution', '')
        if resolution:
            parts.append(f"Resolution: {resolution}")
        
        root_cause = row.get('Root_Cause', row.get('Explanation', ''))
        if root_cause and not pd.isna(root_cause):
            parts.append(f"Root Cause: {str(root_cause)}")
        
        action = row.get('Action', '')
        if action and not pd.isna(action):
            parts.append(f"Action: {str(action)}")
        
        return "\n".join(parts)
    
    def _create_kb_signature(self, row: pd.Series, exception_details: Dict[str, Any]) -> str:
        """Create unique signature using EVENT_INFORMATION details"""
        # [2025-11-24] Include Suggested Step in signature to differentiate user-provided solutions
        components = [
            str(exception_details.get('exception_type', '')).lower().strip(),
            str(exception_details.get('message', '')).lower().strip(),
            str(exception_details.get('stack_trace', '')).lower().strip(),
            str(row.get('Resolution', '')).upper().strip(),
            str(row.get('Suggested Step', row.get('Action', ''))).lower().strip()  # Include suggested step
        ]
        
        combined = '|'.join(components)
        signature = hashlib.md5(combined.encode()).hexdigest()
        
        return signature
    
    def get_kb_context_string(self, similar_cases: List[Dict[str, Any]]) -> str:
        """Convert similar cases to rich context string for LLM"""
        # [2025-11-19] Enhanced KB context with explicit resolution matching instructions
        # Purpose: Ensure LLM uses KB Resolution verbatim when similarity >= 70%
        if not similar_cases:
            return "No similar cases found in knowledge base (First occurrence or unique pattern)."
        
        # Calculate max similarity
        max_similarity = max([case.get('similarity', 0) for case in similar_cases])
        
        context_parts = []
        
        # [2025-12-02] CRITICAL FIX: When similarity >= 70%, show ONLY the best match
        # Date: 2025-12-02
        # Reason: Multiple similar cases with different resolutions (based on inner exceptions) confuse LLM
        # Purpose: Trust vector similarity to find the RIGHT match based on inner exception details, then show ONLY that match
        # Note: KB entries are intentionally different - same exception type but different inner exceptions = different resolutions
        if max_similarity >= 0.70:
            # Show ONLY the best match - it already has the correct resolution based on inner exception
            best_match = max(similar_cases, key=lambda x: x.get('similarity', 0))
            metadata = best_match['metadata']
            similarity = best_match.get('similarity', 0.5)
            
            context_parts.append(f"Found {len(similar_cases)} similar case(s) in knowledge base.\n")
            # [2025-12-02] CRITICAL FIX: Include inner exception MESSAGE
            # Date: 2025-12-02
            # Reason: KB differentiates entries by inner exception MESSAGE, not just type
            # Purpose: LLM needs to see the full inner exception details to match correct KB entry
            inner_exc_type = metadata.get('inner_exception_type', '')
            inner_exc_msg = metadata.get('inner_exception_message', '')
            error_code = metadata.get('error_code', '')
            
            # Build inner exception display
            inner_exc_display = inner_exc_type if inner_exc_type else ''
            if inner_exc_msg:
                inner_exc_display += f"\nInner Message: {inner_exc_msg}"
            if error_code:
                inner_exc_display += f"\nError Code: {error_code}"
            
            # [2025-12-03] FIX 2: KB context now shows normalized resolutions
            # Date: 2025-12-03 14:42 UTC-06:00
            # Purpose: LLM receives only standard resolutions (PURGE/REPROCESS/INVESTIGATE)
            kb_resolution = metadata.get('resolution', 'UNDEFINED')
            logger.info(f"📋 KB Context - Resolution: {kb_resolution}, Similarity: {similarity:.1%}")
            
            context_parts.append(f"""
⚠️ IMPORTANT: High confidence KB match found (Similarity: {similarity:.1%})
The KB Resolution is already normalized to standard format.

═══ BEST MATCH FROM KNOWLEDGE BASE ═══
Exception Type: {metadata.get('exception_type', '')}
Stack Trace Match: {metadata.get('stack_trace', '')}
Inner Exception: {inner_exc_display}

RESOLUTION TO USE: {kb_resolution}
ROOT CAUSE: {metadata.get('root_cause', '')}
RECOMMENDED ACTION: {metadata.get('action', '')}

Instructions:
1. Use the RESOLUTION exactly as shown above (it's already in standard format: PURGE/REPROCESS/INVESTIGATE)
2. Expand the ROOT CAUSE into full multi-line format if needed (Summary, Explanation, Key Identifiers, Action)
3. Use the RECOMMENDED ACTION as your Suggested_Action
4. Set high Confidence (80-95) based on similarity score
""")
        else:
            # Show all cases for reference when similarity < 70%
            context_parts.append(f"Found {len(similar_cases)} similar case(s) in knowledge base (similarity < 70%):\n")
            
            for i, case in enumerate(similar_cases, 1):
                metadata = case['metadata']
                similarity = case.get('similarity', 0.5)
                
                context_parts.append(f"""
═══ Similar Case #{i} (Similarity: {similarity:.1%}) ═══
Exception Type: {metadata.get('exception_type', '')}
Stack Trace Match: {metadata.get('stack_trace', '')}
Inner Exception: {metadata.get('inner_exception_type', '')}
Error Code: {metadata.get('error_code', '')}
Resolution: {metadata.get('resolution', '')}
Root Cause: {metadata.get('root_cause', '')}
Recommended Action: {metadata.get('action', '')}
""")
        
        return "\n".join(context_parts)
    
    def search_similar_cases(self, module_name: str, exception_features: Dict[str, Any], 
                           top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar cases using EVENT_INFORMATION for enhanced matching
        """
        try:
            module_variations = [
                module_name,
                module_name.lower(),
                module_name.upper(),
                module_name.title(),
                module_name.replace(" ", "_"),
                module_name.replace("_", " ")
            ]
            
            collection = None
            
            for variation in module_variations:
                if variation in self.module_collections:
                    collection = self.module_collections[variation]
                    break
            
            if collection is None:
                collection_name = f"{config.CHROMA_COLLECTION_PREFIX}{module_name.lower().replace(' ', '_')}"
                try:
                    collection = self.client.get_collection(collection_name)
                    self.module_collections[module_name] = collection
                    logger.info(f"Loaded collection {collection_name} for module {module_name}")
                except:
                    logger.warning(f"No KB found for module: {module_name}")
                    return []
            
            if collection is None:
                logger.warning(f"No KB loaded for module: {module_name}")
                return []
            
            # Build query with EVENT_INFORMATION details (60% weight in structure)
            query_parts = []
            
            query_parts.append("=== EVENT INFORMATION (PRIMARY) ===")
            
            if exception_features.get('exception_type'):
                query_parts.append(f"Exception Type: {exception_features['exception_type']}")
            
            if exception_features.get('message'):
                query_parts.append(f"Message: {exception_features['message'][:500]}")
            
            if exception_features.get('stack_trace'):
                query_parts.append(f"Stack Trace: {exception_features['stack_trace'][:800]}")
            
            if exception_features.get('inner_exception_type'):
                query_parts.append(f"Inner Exception: {exception_features['inner_exception_type']}")
            
            if exception_features.get('inner_exception_message'):
                query_parts.append(f"Inner Message: {exception_features['inner_exception_message'][:300]}")
            
            if exception_features.get('error_code'):
                query_parts.append(f"Error Code: {exception_features['error_code']}")
            
            if not query_parts or len(query_parts) <= 1:
                logger.warning("No query features available from EVENT_INFORMATION")
                return []
            
            query_text = "\n".join(query_parts)
            
            query_embedding = self.embedding_model.encode([query_text], show_progress_bar=False)[0]
            
            results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=min(top_k, 5)
            )
            
            similar_cases = []
            if results['documents'] and len(results['documents'][0]) > 0:
                for i in range(len(results['documents'][0])):
                    distance = results['distances'][0][i] if 'distances' in results else 0.5
                    similarity_score = max(0, 1.0 - distance)
                    
                    similar_cases.append({
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': distance,
                        'similarity': similarity_score
                    })
            
            logger.info(f"Found {len(similar_cases)} similar cases for {module_name} using EVENT_INFORMATION")
            return similar_cases
            
        except Exception as e:
            logger.error(f"Error searching KB for {module_name}: {str(e)}")
            return []
    
    def get_loaded_modules(self) -> List[str]:
        """Get list of modules with loaded KBs"""
        return list(self.module_collections.keys())
    
    def get_module_stats(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific module"""
        return self.module_metadata.get(module_name)
    
    def clear_module_kb(self, module_name: str) -> bool:
        """
        Clear/delete the knowledge base for a specific module
        [2025-11-24] Added method to support KB clearing functionality
        """
        try:
            # Check if module exists
            if module_name not in self.module_collections:
                logger.warning(f"No KB found for module: {module_name}")
                return False
            
            # Delete the ChromaDB collection
            collection = self.module_collections[module_name]
            try:
                self.chroma_client.delete_collection(collection.name)
                logger.info(f"Deleted ChromaDB collection for {module_name}")
            except Exception as e:
                logger.warning(f"Could not delete collection: {str(e)}")
            
            # Remove from internal tracking
            del self.module_collections[module_name]
            
            if module_name in self.module_signatures:
                del self.module_signatures[module_name]
            
            if module_name in self.module_metadata:
                del self.module_metadata[module_name]
            
            logger.info(f"✅ Cleared KB for module: {module_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing KB for {module_name}: {str(e)}")
            return False

    def search_all_modules(self, exception_features: Dict[str, Any], 
                       primary_module: str, 
                       top_k: int = 5,
                       min_similarity: float = 0.70) -> tuple[List[Dict[str, Any]], str]:
        """
        Search primary module first, then all other modules if no good match found
        Returns:
            tuple: (similar_cases, source_module)
        """
        logger.info(f"="*80)
        logger.info(f"CROSS-MODULE KB SEARCH - START")
        logger.info(f"="*80)
        logger.info(f"Primary module: {primary_module}")
        # Step 1: Search primary module
        logger.info(f"Step 1: Searching primary module '{primary_module}'...")
        primary_results = self.search_similar_cases(primary_module, exception_features, top_k=top_k)
        if primary_results:
            max_similarity = max([case.get('similarity', 0) for case in primary_results])
            logger.info(f"  Found {len(primary_results)} cases in primary module (max similarity: {max_similarity:.1%})")
            if max_similarity >= min_similarity:
                logger.info(f"✅ Good match found in primary module (similarity: {max_similarity:.1%})")
                logger.info(f"="*80)
                logger.info(f"CROSS-MODULE KB SEARCH - END (Primary module used)")
                logger.info(f"="*80)
                return primary_results, primary_module
            else:
                logger.warning(f"⚠️ Primary module similarity {max_similarity:.1%} below threshold {min_similarity:.1%}")
        else:
            logger.warning(f"⚠️ No results found in primary module")
        # Step 2: Search all other modules
        logger.info(f"Step 2: Searching all other modules...")
        all_modules = self.get_loaded_modules()
        other_modules = [m for m in all_modules if m != primary_module]
        if not other_modules:
            logger.warning(f"⚠️ No other modules available to search")
            logger.info(f"="*80)
            logger.info(f"CROSS-MODULE KB SEARCH - END (No other modules)")
            logger.info(f"="*80)
            return primary_results, primary_module
        logger.info(f"  Searching {len(other_modules)} other modules: {other_modules}")
        best_results = primary_results
        best_module = primary_module
        best_similarity = max([case.get('similarity', 0) for case in primary_results]) if primary_results else 0.0
        for module in other_modules:
            logger.info(f"  Searching module: {module}...")
            module_results = self.search_similar_cases(module, exception_features, top_k=top_k)
            if module_results:
                module_max_similarity = max([case.get('similarity', 0) for case in module_results])
                logger.info(f"    Found {len(module_results)} cases (max similarity: {module_max_similarity:.1%})")
                if module_max_similarity > best_similarity:
                    best_results = module_results
                    best_module = module
                    best_similarity = module_max_similarity
                    logger.info(f"    🆕 New best match! Module: {module}, Similarity: {best_similarity:.1%}")
            else:
                logger.info(f"    No results found")
        logger.info(f"="*80)
        logger.info(f"CROSS-MODULE KB SEARCH - COMPLETE")
        logger.info(f"  Best module: {best_module}")
        logger.info(f"  Best similarity: {best_similarity:.1%}")
        logger.info(f"  Total cases: {len(best_results)}")
        logger.info(f"="*80)
        return best_results, best_module
