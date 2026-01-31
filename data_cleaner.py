"""
Data Cleaner Module - JSON Parser for Exception Data
Handles EVENT_INFORMATION JSON structure from log data
"""

import pandas as pd
import logging
import json
import re
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class JSONParser:
    """Enhanced exception data parser with JSON handling"""
    
    def __init__(self):
        self.processed_count = 0
        self.error_count = 0
    
    def parse_exception_file(self, file_path: str) -> pd.DataFrame:
        """Parse exception file (CSV, JSON, or TXT)"""
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith('.json'):
                df = pd.read_json(file_path)
            elif file_path.endswith('.txt'):
                df = self._parse_text_file(file_path)
            else:
                raise ValueError(f"Unsupported file format: {file_path}")
            
            # Clean and standardize
            df = self.clean_dataframe(df)
            return df
            
        except Exception as e:
            logger.error(f"Error parsing file: {str(e)}")
            raise Exception(f"Error parsing file: {str(e)}")
    
    def _parse_text_file(self, file_path: str) -> pd.DataFrame:
        """Parse text file with exception logs"""
        exceptions = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_exception = {}
        for line in lines:
            line = line.strip()
            if not line:
                if current_exception:
                    exceptions.append(current_exception)
                    current_exception = {}
                continue
            
            # Try to parse key-value pairs
            if ':' in line:
                key, value = line.split(':', 1)
                current_exception[key.strip()] = value.strip()
        
        if current_exception:
            exceptions.append(current_exception)
        
        return pd.DataFrame(exceptions)
    
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardize dataframe with new column structure"""
        logger.info(f"Cleaning dataframe with {len(df)} rows")
        
        # Remove duplicate rows
        df = df.drop_duplicates()
        
        # Standardize column names (keep original names)
        df.columns = [str(col).strip() for col in df.columns]

        # --- START OF FIX ---
        # Rename ProcessName to the standardized Process_Name if it exists
        if 'ProcessName' in df.columns:
            logger.info("Found 'ProcessName' column, standardizing to 'Process_Name'.")
            df.rename(columns={'ProcessName': 'Process_Name'}, inplace=True)
        # --- END OF FIX ---

        
        # Parse EVENT_INFORMATION JSON if present
        if 'EVENT_INFORMATION' in df.columns:
            logger.info("Parsing EVENT_INFORMATION JSON column...")
            df = self._parse_event_information(df)
        
        # Add exception ID if not present (use LOG_SEQ_NO if available)
        if 'Exception_ID' not in df.columns:
            if 'LOG_SEQ_NO' in df.columns:
                df['Exception_ID'] = df['LOG_SEQ_NO'].astype(str)
            else:
                df['Exception_ID'] = [self._generate_exception_id(row) 
                                       for _, row in df.iterrows()]
        
        # Standardize timestamp
        if 'Timestamp' not in df.columns:
            if 'LOGTIME' in df.columns:
                df['Timestamp'] = df['LOGTIME']
            else:
                df['Timestamp'] = datetime.now().isoformat()
        
        # Create Module column if not present
        if 'Module' not in df.columns:
            # Try to extract from PRCS_NAME or TITLE
            if 'TITLE' in df.columns:
                df['Module'] = df['TITLE'].apply(self._extract_module_name)
            elif 'PRCS_NAME' in df.columns:
                df['Module'] = df['PRCS_NAME'].apply(self._extract_module_from_process)
            else:
                df['Module'] = 'Unknown'
        
        logger.info(f"Cleaning complete: {len(df)} rows")
        return df
    
    def _parse_event_information(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse the EVENT_INFORMATION JSON column into structured fields"""
        
        exception_types = []
        exception_messages = []
        stack_traces = []
        inner_exceptions = []
        error_codes = []

        # --- START OF FIX: Only parse Process_Name if it doesn't already exist ---
        process_names = []
        parse_process_name = 'Process_Name' not in df.columns
        if parse_process_name:
            logger.info("'Process_Name' column not found. Will attempt to parse from JSON.")

        PROCESS_NAME_KEYS = ['Process Name', 'PRCS_NAME', 'process_name', 'ProcessName']
        # --- END OF FIX ---
        
        for _, row in df.iterrows():
            event_info = row.get('EVENT_INFORMATION', '')
            
            # Parse JSON
            parsed_data = self._parse_json_safely(event_info)
            
            if parsed_data and isinstance(parsed_data, dict):
                exception = parsed_data.get('Exception', {})
                
                # Extract exception type
                exc_type = exception.get('Exception Type', 'Unknown')
                exception_types.append(exc_type)
                
                # Extract message
                message = exception.get('Message', '')
                exception_messages.append(message)
                
                # Extract stack trace
                stack_trace = exception.get('StackTrace', '')
                stack_traces.append(stack_trace)

                 # --- START OF FIX: Conditional parsing of Process_Name ---
                if parse_process_name:
                    process_name = self._get_value_from_keys(parsed_data, PROCESS_NAME_KEYS)
                    process_names.append(process_name)
                # --- END OF FIX ---
                
                # Extract inner exception details
                inner_exc = exception.get('InnerException', {})
                if inner_exc:
                    inner_type = inner_exc.get('Exception Type', '')
                    inner_msg = inner_exc.get('Message', '')
                    inner_exceptions.append(f"{inner_type}: {inner_msg}")
                    
                    # Try to extract error codes from inner exception
                    error_code = inner_exc.get('Code', inner_exc.get('ErrorCode', ''))
                    error_codes.append(str(error_code))
                else:
                    inner_exceptions.append('')
                    error_codes.append('')
            else:
                # If parsing fails, use raw text
                exception_types.append('ParseError')
                exception_messages.append(str(event_info)[:500])
                stack_traces.append('')
                inner_exceptions.append('')
                error_codes.append('')
                if parse_process_name:
                    process_names.append('Unknown') # Default for failed parse
        
        # Add extracted fields to dataframe
        df['Exception_Type'] = exception_types
        df['Exception_Message'] = exception_messages
        df['Stack_Trace'] = stack_traces
        df['Inner_Exception'] = inner_exceptions
        df['Error_Code'] = error_codes

         # --- START OF FIX: Add the Process_Name column only if it was parsed ---
        if parse_process_name and process_names:
            df['Process_Name'] = process_names
        elif 'Process_Name' not in df.columns:
            # Fallback if it was never found or parsed
            df['Process_Name'] = 'Unknown'
        # --- END OF FIX ---
        
        return df
    
    def _parse_json_safely(self, json_str: str) -> Optional[Dict]:
        """Safely parse JSON string"""
        if not json_str or pd.isna(json_str):
            return None
        
        try:
            # Clean JSON string
            json_str = str(json_str).strip()
            
            # Try to parse
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try to fix common JSON issues
            try:
                # Remove BOM and clean
                json_str = json_str.replace('\ufeff', '')
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
                return json.loads(json_str)
            except:
                logger.warning(f"Failed to parse JSON: {str(e)[:100]}")
                return None
    
    def _get_value_from_keys(self, data: Dict, keys: List[str]) -> str:
        """
        Get value from dictionary using a list of possible keys.
        Returns the first matching key's value or 'Unknown' if none found.
        """
        if not data or not isinstance(data, dict):
            return 'Unknown'
        
        for key in keys:
            if key in data:
                value = data[key]
                if value and str(value).strip():
                    return str(value).strip()
        
        return 'Unknown'
    
    def _extract_module_name(self, title: str) -> str:
        """Extract module name from title"""
        if pd.isna(title):
            return 'Unknown'
        
        title = str(title).lower()
        
        # Common module patterns
        if 'claim' in title or 'billing' in title:
            return 'ClaimGeneration'
        elif 'auth' in title or 'authentication' in title:
            return 'Authentication'
        elif 'payment' in title:
            return 'Payment'
        elif 'database' in title or 'db' in title:
            return 'Database'
        elif 'api' in title or 'service' in title:
            return 'API'
        else:
            return 'General'
    
    def _extract_module_from_process(self, process_name: str) -> str:
        """Extract module name from process name"""
        if pd.isna(process_name):
            return 'Unknown'
        
        process_name = str(process_name).lower()
        
        # Extract from path
        if 'claimgeneration' in process_name:
            return 'ClaimGeneration'
        elif 'auth' in process_name:
            return 'Authentication'
        elif 'payment' in process_name:
            return 'Payment'
        elif 'billing' in process_name:
            return 'Billing'
        else:
            # Try to extract from path segments
            segments = process_name.split('\\')
            for segment in segments:
                if segment and len(segment) > 3 and 'windows' not in segment:
                    return segment.title()
        
        return 'General'
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if pd.isna(text):
            return ""
        
        text = str(text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove control characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # Trim
        text = text.strip()
        
        return text
    
    def _generate_exception_id(self, row: pd.Series) -> str:
        """Generate unique exception ID"""
        # Use LOG_SEQ_NO if available
        if 'LOG_SEQ_NO' in row and not pd.isna(row['LOG_SEQ_NO']):
            return f"EX_{row['LOG_SEQ_NO']}"
        
        # Otherwise create hash
        content = f"{row.get('Module', '')}{row.get('Exception_Type', '')}{row.get('Exception_Message', '')}"
        hash_obj = hashlib.md5(content.encode())
        return f"EX_{hash_obj.hexdigest()[:12]}"
    
    def deduplicate_exceptions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate exceptions based on similarity"""
        if df.empty:
            return df
        
        logger.info(f"Starting deduplication on {len(df)} exceptions...")
        
        # Group by module and exception type for efficient processing
        deduplicated = []
        
        for (module, exc_type), group in df.groupby(['Module', 'Exception_Type'], dropna=False):
            # Keep first occurrence of each unique message pattern
            unique_signatures = set()
            for _, row in group.iterrows():
                signature = self._create_message_signature(
                    row.get('Exception_Message', ''), 
                    row.get('Error_Code', '')
                )
                
                if signature not in unique_signatures:
                    unique_signatures.add(signature)
                    deduplicated.append(row)
        
        result_df = pd.DataFrame(deduplicated)
        
        logger.info(f"Deduplication complete: {len(df)} → {len(result_df)} exceptions "
                   f"({len(df) - len(result_df)} duplicates removed)")
        
        return result_df
    
    def _create_message_signature(self, message: str, error_code: str = '') -> str:
        """Create signature for message similarity"""
        if pd.isna(message):
            message = ''
        
        message = str(message).lower()
        
        # Normalize variable parts
        signature = re.sub(r'\d+', 'N', message)
        signature = re.sub(r'\b[0-9a-f]{8,}\b', 'ID', signature)
        signature = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', signature)
        signature = re.sub(r'\b\w+@\w+\.\w+\b', 'EMAIL', signature)
        
        # Add error code if present
        if error_code and not pd.isna(error_code) and str(error_code).strip():
            signature = f"{signature}|CODE:{error_code}"
        
        return signature.strip()
    
    def group_similar_exceptions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Group similar exceptions together"""
        if df.empty:
            return df
        
        logger.info(f"Grouping {len(df)} similar exceptions...")
        
        df['Exception_Group'] = None
        group_id = 0
        
        for (module, exc_type), group in df.groupby(['Module', 'Exception_Type'], dropna=False):
            signatures = {}
            
            for idx, row in group.iterrows():
                signature = self._create_message_signature(
                    row.get('Exception_Message', ''),
                    row.get('Error_Code', '')
                )
                
                if signature in signatures:
                    df.at[idx, 'Exception_Group'] = signatures[signature]
                else:
                    df.at[idx, 'Exception_Group'] = f"G{group_id}"
                    signatures[signature] = f"G{group_id}"
                    group_id += 1
        
        logger.info(f"Grouped into {group_id} unique patterns")
        return df
    
    def compress_exceptions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compress grouped exceptions to representative samples"""
        if 'Exception_Group' not in df.columns:
            return df
        
        logger.info(f"Compressing {len(df)} exceptions...")
        
        compressed = []
        
        for group_id, group in df.groupby('Exception_Group'):
            # Take first occurrence as representative
            representative = group.iloc[0].copy()
            
            # Add aggregated information
            representative['Occurrence_Count'] = len(group)
            representative['First_Seen'] = group['Timestamp'].min() if 'Timestamp' in group else None
            representative['Last_Seen'] = group['Timestamp'].max() if 'Timestamp' in group else None
            
            # Aggregate machine names if multiple
            if 'MACHINE_NAME' in group.columns:
                machines = group['MACHINE_NAME'].unique()
                representative['Affected_Machines'] = ', '.join([str(m) for m in machines[:5]])
            
            compressed.append(representative)
        
        result_df = pd.DataFrame(compressed)
        
        logger.info(f"Compression complete: {len(df)} → {len(result_df)} unique patterns "
                   f"({len(df) - len(result_df)} grouped)")
        
        return result_df
    
    def extract_key_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract key features from exceptions for LLM processing"""
        
        def extract_features(row):
            features = {
                'exception_id': row.get('Exception_ID', 'Unknown'),
                'module': row.get('Module', 'Unknown'),
                'exception_type': row.get('Exception_Type', 'Unknown'),
                'message': row.get('Exception_Message', ''),
                'severity': row.get('SEVERITY', row.get('Severity', 'MEDIUM')),
                'priority': row.get('PRIORITY', row.get('Priority', 5)),
                'frequency': row.get('Occurrence_Count', 1),
                'machine_name': row.get('MACHINE_NAME', 'Unknown'),
                'process_name': row.get('PRCS_NAME', 'Unknown'),
                'timestamp': row.get('Timestamp', ''),
                'error_code': row.get('Error_Code', ''),
                'stack_trace': row.get('Stack_Trace', ''),  # Truncate long traces
                'inner_exception': row.get('Inner_Exception', '')
            }
            
            # Extract additional error indicators
            message = str(row.get('Exception_Message', ''))
            
            # Extract error codes from message
            error_codes = re.findall(r'ORA-\d+|ERROR[:\s]*\d+|Code[:\s]*\d+', message, re.IGNORECASE)
            if error_codes:
                features['error_indicators'] = ', '.join(error_codes[:3])
            
            # Identify constraint violations
            if 'constraint' in message.lower() or 'violated' in message.lower():
                features['is_constraint_violation'] = True
            
            # Identify null/missing data issues
            if 'null' in message.lower() or 'no elements' in message.lower():
                features['is_null_issue'] = True
            
            return features
        
        logger.info("Extracting key features from exceptions...")
        df['Features'] = df.apply(extract_features, axis=1)
        
        return df
    
    def validate_input_format(self, df: pd.DataFrame, required_columns: List[str]) -> bool:
        """Validate if dataframe has required columns"""
        missing_columns = set(required_columns) - set(df.columns)
        
        if missing_columns:
            logger.warning(f"Missing columns: {missing_columns}")
            # Don't raise error, just log warning
            return False
        
        return True


if __name__ == "__main__":
    # Test the parser
    parser = JSONParser()
    logger.info("Enhanced JSON Parser module loaded successfully!")

#enhanced processor
"""
Enhanced Exception Processor - V5.0
Integrates: Enhanced LLMs + Advanced Deduplication + Better Confidence
"""



logger = logging.getLogger(__name__)


