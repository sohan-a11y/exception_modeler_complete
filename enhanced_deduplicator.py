"""
Enhanced Deduplicator Module - V5.0 Production
Advanced deduplication with bidirectional similarity
"""

import pandas as pd
import logging
from typing import Dict, List, Any, Tuple,Set
import re
import hashlib
from Levenshtein import distance as levenshtein_distance
import config
from difflib import SequenceMatcher
logger = logging.getLogger(__name__)


class EnhancedDeduplicator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.similarity_threshold = config.get('similarity_threshold', 0.85)
        self.semantic_threshold = config.get('semantic_threshold', 0.90)
        self.group_counter = 0
        
    def deduplicate_and_group(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        if df.empty:
            return df, {}
        
        logger.info(f"=" * 80)
        logger.info(f"ENHANCED DEDUPLICATION STARTED: {len(df)} exceptions")
        logger.info(f"=" * 80)
        
        # Step 1: Normalize data for comparison
        logger.info("Step 1: Normalizing data...")
        df_normalized = self._normalize_for_comparison(df.copy())
        
        # Step 2: Bidirectional similarity analysis
        logger.info("Step 2: Performing bidirectional similarity analysis...")
        similarity_groups = self._find_bidirectional_similar(df_normalized)
        
        # Step 3: Create groups and representatives
        logger.info("Step 3: Creating groups and representatives...")
        grouped_df, group_mapping = self._create_groups_and_representatives(df, similarity_groups)
        
        logger.info(f"=" * 80)
        logger.info(f"DEDUPLICATION COMPLETE:")
        logger.info(f"  Original:     {len(df)} exceptions")
        logger.info(f"  Deduplicated: {len(grouped_df)} unique patterns")
        logger.info(f"  Groups:       {len(group_mapping)} groups")
        logger.info(f"  Reduction:    {((len(df) - len(grouped_df)) / len(df) * 100):.1f}%")
        logger.info(f"=" * 80)
        
        return grouped_df, group_mapping
    
    def _normalize_for_comparison(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize exception data for accurate comparison"""
        
        for idx, row in df.iterrows():
            # Normalize exception message
            message = str(row.get('Exception_Message', ''))
            message = self._normalize_text(message)
            df.at[idx, 'Normalized_Message'] = message
            
            # Normalize error code
            error_code = str(row.get('Error_Code', ''))
            df.at[idx, 'Normalized_Error_Code'] = error_code.strip().upper()
            
            # Create signature
            signature = self._create_signature(
                row.get('Exception_Type', ''),
                message,
                error_code
            )
            df.at[idx, 'Signature'] = signature
        
        return df
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if pd.isna(text):
            return ""
        
        text = str(text).lower()
        
        # Remove timestamps
        text = re.sub(r'\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}', 'TIMESTAMP', text)
        
        # Remove machine names if configured
        if self.config.get('remove_machine_names', True):
            text = re.sub(r'machine[:\s]+\S+', 'MACHINE', text, flags=re.IGNORECASE)
            text = re.sub(r'server[:\s]+\S+', 'SERVER', text, flags=re.IGNORECASE)
        
        # Normalize numbers
        text = re.sub(r'\b\d+\b', 'NUM', text)
        
        # Normalize IDs and GUIDs
        text = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', 'GUID', text, flags=re.IGNORECASE)
        text = re.sub(r'\b[0-9a-f]{32,}\b', 'ID', text, flags=re.IGNORECASE)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _create_signature(self, exc_type: str, message: str, error_code: str) -> str:
        """Create unique signature for exception"""
        content = f"{exc_type}|{message}|{error_code}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _find_bidirectional_similar(self, df: pd.DataFrame) -> Dict[str, Set[int]]:
        # Find bidirectional similar exceptions
        
        # Returns: Dict mapping signature -> set of similar row indices
        similarity_groups = {}
        processed_indices = set()
        
        # Group by exception type first (optimization)
        for exc_type, group in df.groupby('Exception_Type'):
            group_indices = list(group.index)
            
            for i, idx1 in enumerate(group_indices):
                if idx1 in processed_indices:
                    continue
                
                # Start new group
                group_key = f"GROUP_{self.group_counter}"
                self.group_counter += 1
                similar_set = {idx1}
                
                row1 = df.loc[idx1]
                
                # Compare with remaining rows
                for idx2 in group_indices[i+1:]:
                    if idx2 in processed_indices:
                        continue
                    
                    row2 = df.loc[idx2]
                    
                    # Bidirectional similarity check
                    if self._are_bidirectionally_similar(row1, row2):
                        similar_set.add(idx2)
                        processed_indices.add(idx2)
                
                processed_indices.add(idx1)
                
                if len(similar_set) > 0:
                    similarity_groups[group_key] = similar_set
        
        logger.info(f"  Found {len(similarity_groups)} similarity groups")
        return similarity_groups
    
    def _are_bidirectionally_similar(self, row1: pd.Series, row2: pd.Series) -> bool:
        # Check if two rows are bidirectionally similar
        
        # Bidirectional means:
        # - Both ways similarity check (A->B and B->A)
        # - Multiple field comparison
        # - Weighted scoring
        
        # Quick check: same exception type
        if row1.get('Exception_Type') != row2.get('Exception_Type'):
            return False
        
        # Check normalized messages
        msg1 = row1.get('Normalized_Message', '')
        msg2 = row2.get('Normalized_Message', '')
        
        if not msg1 or not msg2:
            return False
        
        # Similarity A->B
        sim_ab = self._calculate_similarity(msg1, msg2)
        
        # Similarity B->A (should be same but we check for consistency)
        sim_ba = self._calculate_similarity(msg2, msg1)
        
        # Bidirectional similarity score
        bidirectional_sim = (sim_ab + sim_ba) / 2
        
        # Check error codes if available
        code1 = row1.get('Normalized_Error_Code', '')
        code2 = row2.get('Normalized_Error_Code', '')
        
        if code1 and code2 and code1 != code2:
            # Different error codes reduce similarity
            bidirectional_sim *= 0.8
        
        # Apply threshold
        return bidirectional_sim >= self.similarity_threshold
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher"""
        if not text1 or not text2:
            return 0.0
        
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _create_groups_and_representatives(self, df: pd.DataFrame, 
                                          similarity_groups: Dict[str, Set[int]]) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        # Create groups and select representatives
        
        # Returns:
        #     - DataFrame with representative exceptions
        #     - Mapping of group_id -> original exception IDs
        representatives = []
        group_mapping = {}
        
        for group_id, indices in similarity_groups.items():
            # Get all rows in this group
            group_rows = df.loc[list(indices)]
            
            # Select representative (first occurrence)
            representative = group_rows.iloc[0].copy()
            
            # Add group metadata
            representative['Dedup_Group_ID'] = group_id
            representative['Dedup_Count'] = len(indices)
            
            # Store all original exception IDs
            # [2025-11-24] Remove duplicates by converting to set then back to list
            # Date: 2025-11-24
            # Reason: Same Exception_ID was appearing multiple times (e.g., 7 duplicates)
            # Purpose: Ensure each Exception_ID appears only once in the pipe-delimited list
            original_ids = list(set(group_rows['Exception_ID'].tolist()))
            # [2025-12-04] FIX: For large groups, don't create massive ID strings
            # Reason: 180K records can create groups with 50K+ IDs causing MemoryError
            if len(original_ids) <= 100:
                representative['Original_Exception_IDs'] = '|'.join(map(str, sorted(original_ids)))
            else:
                representative['Original_Exception_IDs'] = f"{group_id} ({len(original_ids)} exceptions)"
            
            # Update aggregated info
            representative['Occurrence_Count'] = len(indices)
            representative['First_Seen'] = group_rows['Timestamp'].min() if 'Timestamp' in group_rows else None
            representative['Last_Seen'] = group_rows['Timestamp'].max() if 'Timestamp' in group_rows else None
            
            # Aggregate machine names
            if 'MACHINE_NAME' in group_rows.columns:
                machines = group_rows['MACHINE_NAME'].unique()
                representative['Affected_Machines'] = ', '.join([str(m) for m in machines[:5]])
            
            representatives.append(representative)
            group_mapping[group_id] = original_ids
        
        result_df = pd.DataFrame(representatives)
        
        # Ensure required columns exist
        if 'Dedup_Group_ID' not in result_df.columns:
            result_df['Dedup_Group_ID'] = None
        if 'Dedup_Count' not in result_df.columns:
            result_df['Dedup_Count'] = 1
        if 'Original_Exception_IDs' not in result_df.columns:
            result_df['Original_Exception_IDs'] = result_df['Exception_ID'].astype(str)
        
        return result_df, group_mapping
    
    def split_after_processing(self, processed_df: pd.DataFrame, 
                               group_mapping: Dict[str, List[str]]) -> pd.DataFrame:
        # [2025-11-19] Fixed duplicate exception records issue
        # Purpose: Ensure each original exception ID appears only once in the final output
        # Split processed results back to individual exceptions
        
        logger.info(f"Splitting {len(processed_df)} processed groups back to individual exceptions...")
        
        expanded_rows = []
        seen_exception_ids = set()  # Track processed IDs to prevent duplicates
        
        for _, row in processed_df.iterrows():
            group_id = row.get('Dedup_Group_ID')
            
            if group_id and group_id in group_mapping:
                # This was a grouped exception - split it back
                original_ids = group_mapping[group_id]
                
                for exc_id in original_ids:
                    # [2025-11-19] Skip if this exception ID was already processed
                    # Purpose: Prevent duplicate records in final output
                    if exc_id in seen_exception_ids:
                        logger.debug(f"Skipping duplicate exception ID: {exc_id}")
                        continue
                    
                    seen_exception_ids.add(exc_id)
                    expanded_row = row.copy()
                    expanded_row['Exception_ID'] = exc_id
                    expanded_row['Dedup_Count'] = len(original_ids)
                    expanded_row['Dedup_Group_ID'] = group_id
                    # [2025-12-04] FIX: For large datasets (180K records), don't store all IDs
                    # Reason: Pipe-delimited string of 50K+ IDs causes MemoryError
                    # Purpose: Store only essential info - group ID and count are enough
                    if len(original_ids) <= 10:
                        # Small group: store all IDs for traceability
                        expanded_row['Original_Exception_IDs'] = '|'.join(map(str, original_ids))
                    else:
                        # Large group: just store count to save memory
                        expanded_row['Original_Exception_IDs'] = f"{group_id} ({len(original_ids)} exceptions)"
                    expanded_rows.append(expanded_row)
            else:
                # Not grouped, keep as is (but check for duplicates)
                exc_id = row.get('Exception_ID')
                if exc_id not in seen_exception_ids:
                    seen_exception_ids.add(exc_id)
                    expanded_rows.append(row)
        
        result_df = pd.DataFrame(expanded_rows)
        
        logger.info(f"Split complete: {len(processed_df)} groups → {len(result_df)} individual exceptions")
        logger.info(f"Removed {len(expanded_rows) - len(result_df) if len(expanded_rows) > len(result_df) else 0} duplicate records")
        
        return result_df
    
    def deduplicate_for_kb(self, new_entries: pd.DataFrame, 
                          existing_kb: pd.DataFrame) -> pd.DataFrame:
        # Deduplicate new KB entries against existing KB
        
        # For self-healing: Only add truly unique patterns to KB
        if existing_kb.empty:
            logger.info("No existing KB, all entries are unique")
            return new_entries
        
        logger.info(f"Deduplicating {len(new_entries)} new entries against {len(existing_kb)} existing KB entries...")
        
        unique_entries = []
        
        for _, new_row in new_entries.iterrows():
            is_duplicate = False
            
            new_sig = self._create_signature(
                new_row.get('Exception_Type', ''),
                self._normalize_text(new_row.get('Exception_Message', '')),
                str(new_row.get('Error_Code', ''))
            )
            
            # Check against existing KB
            for _, existing_row in existing_kb.iterrows():
                existing_sig = self._create_signature(
                    existing_row.get('Exception_Type', ''),
                    self._normalize_text(existing_row.get('Exception_Message', '')),
                    str(existing_row.get('Error_Code', ''))
                )
                
                if new_sig == existing_sig:
                    is_duplicate = True
                    break
                
                # Also check high similarity
                new_msg = self._normalize_text(new_row.get('Exception_Message', ''))
                existing_msg = self._normalize_text(existing_row.get('Exception_Message', ''))
                
                similarity = self._calculate_similarity(new_msg, existing_msg)
                
                if similarity >= self.semantic_threshold and \
                   new_row.get('Exception_Type') == existing_row.get('Exception_Type'):
                    is_duplicate = True
                    logger.info(f"  Skipping duplicate: {new_row.get('Exception_ID')} (similarity: {similarity:.2f})")
                    break
            
            if not is_duplicate:
                unique_entries.append(new_row)
        
        result_df = pd.DataFrame(unique_entries) if unique_entries else pd.DataFrame()
        
        logger.info(f"KB deduplication complete: {len(new_entries)} → {len(result_df)} unique entries")
        logger.info(f"  Filtered out: {len(new_entries) - len(result_df)} duplicates")
        
        return result_df
    
    def get_unique_for_dev(self, exceptions_df: pd.DataFrame) -> pd.DataFrame:
        # Get unique exceptions to send to dev
        
        # For self-healing: Send only unique error patterns to dev, not all duplicates
        logger.info(f"Extracting unique patterns for dev from {len(exceptions_df)} exceptions...")
        
        # Group by dedup_group_id if available
        if 'Dedup_Group_ID' in exceptions_df.columns:
            unique_df = exceptions_df.drop_duplicates(subset=['Dedup_Group_ID'], keep='first')
        else:
            # No grouping info, deduplicate by signature
            exceptions_df = self._normalize_for_comparison(exceptions_df)
            unique_df = exceptions_df.drop_duplicates(subset=['Signature'], keep='first')
        
        logger.info(f"Unique patterns for dev: {len(unique_df)} (from {len(exceptions_df)} total)")
        
        return unique_df


class SelfHealingDeduplicator:
    # Specialized deduplicator for self-healing workflow
    # Ensures only unique patterns are added to KB
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_deduplicator = EnhancedDeduplicator(config)
    
    def prepare_for_kb_addition(self, reviewed_exceptions: pd.DataFrame,
                                existing_kb: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        # Prepare reviewed exceptions for KB addition
        
        # Returns:
        #     - DataFrame with unique exceptions to add
        #     - Statistics about deduplication
        logger.info(f"=" * 80)
        logger.info(f"SELF-HEALING KB PREPARATION")
        logger.info(f"=" * 80)
        
        # Step 1: Deduplicate within new entries
        logger.info("Step 1: Deduplicating within new entries...")
        deduplicated_new, _ = self.base_deduplicator.deduplicate_and_group(reviewed_exceptions)
        
        # Step 2: Deduplicate against existing KB
        logger.info("Step 2: Checking against existing KB...")
        unique_entries = self.base_deduplicator.deduplicate_for_kb(deduplicated_new, existing_kb)
        
        stats = {
            'original_count': len(reviewed_exceptions),
            'after_internal_dedup': len(deduplicated_new),
            'after_kb_dedup': len(unique_entries),
            'duplicates_removed': len(reviewed_exceptions) - len(unique_entries)
        }
        
        logger.info(f"=" * 80)
        logger.info(f"PREPARATION COMPLETE:")
        logger.info(f"  Original reviewed:    {stats['original_count']}")
        logger.info(f"  After internal dedup: {stats['after_internal_dedup']}")
        logger.info(f"  Unique to add to KB:  {stats['after_kb_dedup']}")
        logger.info(f"  Duplicates filtered:  {stats['duplicates_removed']}")
        logger.info(f"=" * 80)
        
        return unique_entries, stats

