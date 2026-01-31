
"""
Exception Processor Module - V5.0 Production
Main processing engine with KB integration
"""

import pandas as pd
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import config
from enhanced_llm_api import EnhancedLLMAPI 
from enhanced_deduplicator import EnhancedDeduplicator,SelfHealingDeduplicator
from  data_cleaner import JSONParser
from kb_manager import MultiModuleKBManager  # Added missing import so code runs

logger = logging.getLogger(__name__)

class EnhancedExceptionProcessor:
    """
    V5.0 Enhanced Processor with:
    - Support for multiple LLMs (local + API)
    - Advanced bidirectional deduplication
    - Improved confidence scoring
    - Self-healing KB management
    """
    
    def __init__(self, model_key: str = None, kb_manager=None):
        model_key = model_key or config.DEFAULT_MODEL
        
        # Get model config
        if model_key not in config.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_key}. Available: {list(config.AVAILABLE_MODELS.keys())}")
        
        model_config = config.AVAILABLE_MODELS[model_key]
        
        # Initialize components
        self.json_parser = JSONParser()
        self.llm_api = EnhancedLLMAPI(model_config)
        # Use provided kb_manager or create new one
        self.kb_manager = kb_manager if kb_manager is not None else MultiModuleKBManager(config.CHROMA_DIR)
        self.deduplicator = EnhancedDeduplicator(config.DEDUPLICATION_CONFIG)
        self.self_healing_dedup = SelfHealingDeduplicator(config.SELF_HEALING_CONFIG)
        self.model_key = model_key
        self.model_config = model_config
        
        logger.info(f"=" * 80)
        logger.info(f"✅ ENHANCED EXCEPTION PROCESSOR V5.0 INITIALIZED")
        logger.info(f"=" * 80)
        logger.info(f"Model: {model_config['name']}")
        logger.info(f"Type: {model_config.get('type', 'local')}")
        logger.info(f"Provider: {model_config.get('provider', 'local')}")
        logger.info(f"Max Length: {model_config.get('max_length', 4096)}")
        logger.info(f"Deduplication: {'✅ Enabled' if config.DEDUPLICATION_CONFIG.get('enabled') else '❌ Disabled'}")
        logger.info(f"Self-Healing: {'✅ Enabled' if config.SELF_HEALING_CONFIG.get('enabled') else '❌ Disabled'}")
        logger.info(f"=" * 80)

    def _parse_json_safely(self, json_str: str) -> Optional[Dict]:
        """Safely parse JSON string"""
        import json
        if not json_str or pd.isna(json_str):
            return None
        try:
            return json.loads(str(json_str).strip())
        except:
            return None

    
    def _extract_exception_from_event_info(self, event_info_str: str) -> Dict[str, Any]:
        """Extract exception details from EVENT_INFORMATION JSON"""
        parsed = self._parse_json_safely(event_info_str)
        if not parsed or not isinstance(parsed, dict):
            return {}
        
        exception_data = parsed.get('Exception', {})
        return {
            'exception_type': exception_data.get('Exception Type', ''),
            'message': exception_data.get('Message', ''),
            'stack_trace': exception_data.get('StackTrace', ''),
            'inner_exception_type': exception_data.get('InnerException', {}).get('Exception Type', ''),
            'inner_exception_message': exception_data.get('InnerException', {}).get('Message', ''),
            'error_code': exception_data.get('InnerException', {}).get('Code', '')
        }

    def _build_full_error_message(self, features: Dict, row: pd.Series) -> str:
        """
        Build comprehensive error message including inner exceptions
        [2025-12-02] Added to provide complete error details in Original_Error column
        """
        parts = []
        
        # Main message
        main_msg = features.get('message', '')
        if main_msg:
            parts.append(main_msg)
        
        # Inner exception details
        inner_type = features.get('inner_exception_type', '')
        inner_msg = features.get('inner_exception_message', '')
        error_code = features.get('error_code', '')
        
        if inner_type or inner_msg or error_code:
            inner_parts = []
            if inner_type:
                inner_parts.append(f"Inner Exception: {inner_type}")
            if inner_msg:
                inner_parts.append(f"Inner Message: {inner_msg}")
            if error_code:
                inner_parts.append(f"Error Code: {error_code}")
            
            if inner_parts:
                parts.append(" | " + " | ".join(inner_parts))
        
        return " ".join(parts) if parts else row.get('Exception_Message', '')

    def process_exceptions(self, input_df: pd.DataFrame, module_name: str) -> pd.DataFrame:
        """
        Enhanced processing pipeline with deduplication
        Pipeline:
        1. Parse & Clean
        2. Enhanced Deduplication (bidirectional + grouping)
        3. Feature Extraction
        4. Classification
        5. AI Analysis (on representatives)
        6. Split Results (back to individual errors)
        7. Output Formatting
        """
        try:
            logger.info(f"{'=' * 80}")
            logger.info(f"PROCESSING {len(input_df)} EXCEPTIONS FOR MODULE: {module_name}")
            logger.info(f"{'=' * 80}")

            # Step 1: Clean and parse
            logger.info("📋 Step 1/7: Parsing and cleaning data...")
            cleaned_df = self.json_parser.clean_dataframe(input_df.copy())
            logger.info(f" ✅ Parsed {len(cleaned_df)} exceptions")
            # Ensure module column
            if 'Module' not in cleaned_df.columns or cleaned_df['Module'].isna().all():
                cleaned_df['Module'] = module_name

            # Step 2: ENHANCED DEDUPLICATION
            logger.info("🔄 Step 2/7: Enhanced Deduplication (Bidirectional + Grouping)...")
            if config.DEDUPLICATION_CONFIG.get('enabled', True):
                deduplicated_df, group_mapping = self.deduplicator.deduplicate_and_group(cleaned_df)
                logger.info(f" ✅ Deduplicated: {len(cleaned_df)} → {len(deduplicated_df)} unique patterns")
                logger.info(f" ✅ Created {len(group_mapping)} groups")
            else:
                deduplicated_df = cleaned_df
                group_mapping   = {}
                logger.info(" ⚠️ Deduplication disabled in config")

            # Step 3: Feature extraction
            logger.info("🔍 Step 3/7: Extracting features...")
            featured_df = self.json_parser.extract_key_features(deduplicated_df)
            logger.info(f" ✅ Extracted features from {len(featured_df)} exceptions")

            # Step 4: Classification
            logger.info("🏷️ Step 4/7: Classifying exceptions...")
            featured_df['Classified_Type'] = featured_df.apply(
                lambda row: self._classify_exception(row),
                axis=1
            )
            logger.info(f" ✅ Classified {len(featured_df)} exceptions")

            # Step 5: AI Analysis
            logger.info("🤖 Step 5/7: AI Analysis with Enhanced Prompting...")
            results = []
            total   = len(featured_df)
            for idx, (_, row) in enumerate(featured_df.iterrows(), 1):
                logger.info(f" Analyzing {idx}/{total}: {row.get('Exception_ID', 'Unknown')}...")
                result = self._analyze_exception(row, module_name)
                results.append(result)
            logger.info(f" ✅ Analyzed all {total} patterns")

            # Step 6: Create output from analysis
            logger.info("📊 Step 6/7: Creating output dataframe...")
            output_df = self._create_output_dataframe(featured_df, results)
            logger.info(f" ✅ Created output with {len(output_df)} rows")

            # [2025-11-19] Step 7: SPLIT BACK if we had grouping - ensure all original records are present
            # Purpose: Display final results for ALL input records (all 8 exceptions)
            if group_mapping and config.DEDUPLICATION_CONFIG.get('split_after_processing', True):
                logger.info("🔀 Step 7/7: Splitting grouped errors back to individuals...")
                logger.info(f" Input had {len(cleaned_df)} original exceptions")
                output_df = self.deduplicator.split_after_processing(output_df, group_mapping)
                logger.info(f" ✅ Split to {len(output_df)} individual exceptions")
                
                # [2025-11-19] Validate that all original exceptions are present
                # Purpose: Ensure no records are lost during processing
                if len(output_df) != len(cleaned_df):
                    logger.warning(f" ⚠️ Record count mismatch: Input={len(cleaned_df)}, Output={len(output_df)}")
                else:
                    logger.info(f" ✅ All {len(output_df)} original exceptions accounted for")
            else:
                logger.info("✅ Step 7/7: No splitting needed")

            # Final statistics
            self._log_statistics(output_df)
            return output_df

        except Exception as e:
            logger.error(f"❌ Error processing exceptions: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def _classify_exception(self, row: pd.Series) -> str:
        """Enhanced classification"""
        try:
            features = row.get('Features', {})
            if isinstance(features, dict):
                features['severity']  = row.get('SEVERITY', 'Unknown')
                features['frequency'] = row.get('Occurrence_Count', 1)
                classification = self.llm_api.classify_exception(features)
                return classification if classification else row.get('Exception_Type', '')
        except Exception as e:
            logger.error(f"Error classifying: {str(e)}")
        return row.get('Exception_Type', '')

    def _analyze_exception(self, row: pd.Series, module_name: str) -> Dict[str, Any]:
        """
        Enhanced analysis with KB context and confidence boost
        """
        features = row.get('Features', {})
        exception_id = row.get('Exception_ID', 'Unknown')
        if not isinstance(features, dict):
            features = {'exception_id': exception_id}
        # Extract EVENT_INFORMATION details
        event_info = row.get("EVENT_INFORMATION", "")
        if event_info and not pd.isna(event_info):
            exception_details = self._extract_exception_from_event_info(event_info)
            features.update(exception_details)
        # 🔥 NEW: Cross-module KB search
        similar_cases, source_module = self.kb_manager.search_all_modules(
            exception_features=features,
            primary_module=module_name,
            top_k=5,
            min_similarity=0.70
        )
        if similar_cases:
            max_sim = max([case.get('similarity', 0) for case in similar_cases])
            if source_module != module_name:
                logger.info(f"      🌐 Cross-module match! Found in '{source_module}' (similarity: {max_sim:.1%})")
            else:
                logger.info(f"      ✅ KB Search: Found {len(similar_cases)} cases in primary module (max similarity: {max_sim:.1%})")
        else:
            logger.info(f"      ⚠️ KB Search: No similar cases found in any module")
        kb_context = self.kb_manager.get_kb_context_string(similar_cases)
        kb_confidence = self._calculate_kb_confidence(similar_cases)
            
        # Decide on analysis depth
        use_deep_analysis = kb_confidence < config.CONFIDENCE_HIGH_THRESHOLD
        
        if use_deep_analysis:
            logger.info(f"      Using DEEP analysis (KB confidence: {kb_confidence}%)")
        else:
            logger.info(f"      Using STANDARD analysis (KB confidence: {kb_confidence}%)")
        
        # [2025-12-03] CRITICAL FIX: Pass similar_cases to LLM API
        # Date: 2025-12-03 15:14 UTC-06:00
        # Reason: similar_cases was NOT being passed, causing KB resolution extraction to fail
        # Purpose: LLM needs similar_cases to extract KB resolution and apply overrides
        # Impact: This is THE ROOT CAUSE of UNDEFINED resolutions despite KB matches
        # Perform analysis
        analysis_result = self.llm_api.analyze_with_enhanced_prompt(
            features, 
            kb_context,
            use_deep_analysis=use_deep_analysis,
            similar_cases=similar_cases  # ✅ CRITICAL: Now passing similar_cases!
        )
        
        # Enhance confidence with multiple factors
        enhanced_confidence = self._calculate_enhanced_confidence(
            analysis_result.get('confidence_score', 50),
            kb_confidence,
            features,
            similar_cases
        )
        
        # Build complete result
        result = {
            'exception_id': exception_id,
            'module': module_name,
            'exception_type': features.get('exception_type', ''),
            'exception_message': features.get('message', ''),
            'original_error': self._build_full_error_message(features, row),
            'stack_trace': features.get('stack_trace', ''),
            'resolution': analysis_result.get('resolution', ''),
            'root_cause': analysis_result.get('root_cause', ''),
            'confidence_score': enhanced_confidence,
            'reasoning': analysis_result.get('reasoning', ''),
            'suggested_action': analysis_result.get('suggested_action', ''),
            'similar_cases_found': len(similar_cases),
            'kb_confidence': kb_confidence,
            'severity': features.get('severity', 'MEDIUM'),
            'machine_name': features.get('machine_name', 'Unknown'),
            'process_name': features.get('process_name', 'Unknown'),
            'timestamp': features.get('timestamp', ''),
            'analysis_type': analysis_result.get('analysis_type', 'constructive'),
            'requires_review': enhanced_confidence < config.CONFIDENCE_HIGH_THRESHOLD
        }
        
        logger.info(f"      → {result['resolution']} (Confidence: {enhanced_confidence}%)")
        
        return result
    
    def _calculate_kb_confidence(self, similar_cases: List[Dict[str, Any]]) -> int:
        """Calculate confidence from KB matches"""
        if not similar_cases:
            return None 
        
        # Get highest similarity
        max_similarity = max([case.get('similarity', 0) for case in similar_cases])
        
        # Convert to confidence
        if max_similarity > 0.95:
            return 95
        elif max_similarity > 0.90:
            return 88
        elif max_similarity > 0.85:
            return 78
        elif max_similarity > 0.80:
            return 68
        elif max_similarity > 0.75:
            return 58
        else:
            return int(max_similarity * 60)

    
    def _calculate_enhanced_confidence(self, llm_confidence: int, kb_confidence: int,
                                       features: Dict[str, Any],
                                       similar_cases: List[Dict[str, Any]]) -> int:
        """
        Calculate enhanced confidence using only weighted average of LLM and KB confidence.
        """
        if llm_confidence is None or kb_confidence is None:
            raise ValueError("Both LLM and KB confidence scores must be provided.")

        weights = config.CONFIDENCE_WEIGHTS_KB_PRESENT if similar_cases else config.CONFIDENCE_WEIGHTS_KB_ABSENT
        llm_weight = weights.get('llm', 0.5)
        kb_weight = weights.get('kb', 0.5)

        confidence = (llm_confidence * llm_weight) + (kb_confidence * kb_weight)
        return int(confidence)

    def _create_output_dataframe(self, input_df: pd.DataFrame, 
                                 results: List[Dict[str, Any]]) -> pd.DataFrame:
        """Create output dataframe"""
        output_data = []
        
        for idx, result in enumerate(results):
            try:
                # [2025-12-02] FIX: Preserve dedup metadata from input_df to match Dec 1 results
                # Date: 2025-12-02
                # Reason: Nov 19 backup had hardcoded None/1 values, losing dedup info
                # Purpose: Restore GROUP_0, GROUP_1, etc. and correct Dedup_Count
                row = input_df.iloc[idx]  # Get corresponding input row for dedup metadata
                
                output_row = {
                    'Exception_ID': result.get('exception_id', 'Unknown'),
                    'Selected_Module': result.get('module', 'Unknown'),
                    'Exception_Type': result.get('exception_type', ''),
                    'Exception_Message': result.get('exception_message', ''),
                    'Original_Error': result.get('original_error', ''),
                    'Stack_Trace': result.get('stack_trace', ''),
                    'Resolution': result.get('resolution', ''),
                    'Root_Cause': result.get('root_cause', ''),
                    'Confidence_Score': result.get('confidence_score', 50),
                    'Reasoning': result.get('reasoning', ''),
                    'Similar_Past_Cases': (f"{result.get('similar_cases_found', 0)} cases - "
                                          f"KB confidence: {result.get('kb_confidence', 0)}%"),
                    'Suggested_Action': result.get('suggested_action', ''),
                    'Severity': result.get('severity', 'MEDIUM'),
                    'Machine_Name': result.get('machine_name', 'Unknown'),
                    'Process_Name': result.get('process_name', 'Unknown'),
                    'Timestamp': result.get('timestamp', ''),
                    'Analysis_Type': result.get('analysis_type', 'constructive'),
                    'Requires_Review': result.get('requires_review', False),
                    # [2025-12-02] Preserve dedup metadata from representative rows
                    'Dedup_Group_ID': row.get('Dedup_Group_ID', None),
                    'Dedup_Count': row.get('Dedup_Count', 1),
                    'Original_Exception_IDs': row.get('Original_Exception_IDs', str(row.get('Exception_ID', 'Unknown')))
                }
                
                output_data.append(output_row)
            except Exception as e:
                logger.error(f"Error creating output row {idx}: {str(e)}")
                # [2025-12-04] FIX: Don't lose the record - add it with safe defaults
                # Reason: When resolution is UNDEFINED or other errors occur, records were being lost
                # Purpose: Ensure all input records appear in output, even if there's an error
                try:
                    row = input_df.iloc[idx]
                    safe_row = {
                        'Exception_ID': row.get('Exception_ID', f'EXC_{idx}'),
                        'Selected_Module': result.get('module', 'Unknown'),
                        'Exception_Type': result.get('exception_type', row.get('Exception_Type', 'Unknown')),
                        'Exception_Message': result.get('exception_message', row.get('Exception_Message', '')),
                        'Original_Error': result.get('original_error', ''),
                        'Stack_Trace': result.get('stack_trace', row.get('Stack_Trace', '')),
                        'Resolution': result.get('resolution', 'INVESTIGATE'),  # Safe default
                        'Root_Cause': result.get('root_cause', 'Error during analysis'),
                        'Confidence_Score': 0,  # Low confidence due to error
                        'Reasoning': f'Analysis error: {str(e)}',
                        'Similar_Past_Cases': '0 cases',
                        'Suggested_Action': 'Review manually',
                        'Severity': 'HIGH',  # Flag for review
                        'Machine_Name': row.get('MACHINE_NAME', 'Unknown'),
                        'Process_Name': row.get('PROCESS_NAME', 'Unknown'),
                        'Timestamp': row.get('Timestamp', ''),
                        'Analysis_Type': 'error',
                        'Requires_Review': True,  # Always require review
                        'Dedup_Group_ID': row.get('Dedup_Group_ID', None),
                        'Dedup_Count': row.get('Dedup_Count', 1),
                        'Original_Exception_IDs': row.get('Original_Exception_IDs', str(row.get('Exception_ID', f'EXC_{idx}')))
                    }
                    output_data.append(safe_row)
                    logger.warning(f"Added row {idx} with safe defaults due to error")
                except Exception as e2:
                    logger.error(f"Failed to add safe row {idx}: {str(e2)}")
        
        return pd.DataFrame(output_data)

    def _log_statistics(self, output_df: pd.DataFrame):
        """Log processing statistics"""
        total = len(output_df)
        review_count = output_df['Requires_Review'].sum()
        avg_confidence = output_df['Confidence_Score'].mean()
        
        purge = len(output_df[output_df['Resolution'] == 'PURGE'])
        reprocess = len(output_df[output_df['Resolution'] == 'REPROCESS'])
        investigate = len(output_df[output_df['Resolution'] == 'INVESTIGATE'])
        
        logger.info(f"\n{'=' * 80}")
        logger.info(f"✅ PROCESSING COMPLETE!")
        logger.info(f"{'=' * 80}")
        logger.info(f"Total Exceptions:     {total}")
        logger.info(f"Requires Review:      {review_count} ({review_count/total*100:.1f}%)")
        logger.info(f"Average Confidence:   {avg_confidence:.1f}%")
        logger.info(f"")
        logger.info(f"Resolutions:")
        logger.info(f"  ♻️  REPROCESS:        {reprocess} ({reprocess/total*100:.1f}%)")
        logger.info(f"  🗑️  PURGE:            {purge} ({purge/total*100:.1f}%)")
        logger.info(f"  ⚠️  INVESTIGATE:         {investigate} ({investigate/total*100:.1f}%)")
        logger.info(f"{'=' * 80}\n")


if __name__ == "__main__":
    processor = EnhancedExceptionProcessor()
    print(f"✅ Enhanced Exception Processor V5.0 initialized!")
    print(f"Model: {processor.model_config['name']}")
