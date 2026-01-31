"""
Configuration Module - V7.0 with Demo Mode and Deployment Support
Central configuration for Exception Modeler with Code Analysis
"""

from pathlib import Path
import os

# ============================================================================
# DEMO MODE CONFIGURATION (NEW)
# ============================================================================
# Enable demo mode for client presentations
DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true'

# Demo authentication settings
DEMO_CONFIG = {
    'enabled': DEMO_MODE,
    'expiry_hours': int(os.environ.get('DEMO_EXPIRY_HOURS', '24')),
    'demo_password': os.environ.get('DEMO_PASSWORD', 'demo2026'),
    'demo_username': os.environ.get('DEMO_USERNAME', 'client'),
}

# ============================================================================
# CODE REPOSITORY CONFIGURATION
# ============================================================================
# Path to your source code repository (configurable via environment variable)
CODE_REPOSITORY_PATH = os.environ.get('CODE_REPOSITORY_PATH', 'C:/Source/repos/code')

# Enable/disable code analysis feature
CODE_ANALYSIS_ENABLED = not DEMO_MODE  # Disabled in demo mode

# Code indexing settings
CODE_INDEXING_CONFIG = {
    'auto_index_on_startup': False,  # Set to True to auto-index on app start
    'index_batch_size': 100,          # Files to process per batch
    'max_chunk_size': 100,            # Max lines per code chunk
    'reindex_on_changes': True,       # Re-index files that changed
}

# Code retrieval settings
CODE_RETRIEVAL_CONFIG = {
    'max_snippets': 5,                # Max code snippets to retrieve per exception
    'min_similarity': 0.5,            # Minimum similarity for semantic search
    'max_snippet_lines': 100,         # Max lines to include per snippet
    'prefer_direct_match': True,      # Prefer stack trace matches over semantic
}

# Token management
CODE_ANALYSIS_TOKEN_LIMITS = {
    'max_prompt_tokens': 120000,      # Max tokens for entire prompt (leave room for response)
    'max_code_tokens': 80000,         # Max tokens allocated for code snippets
    'max_kb_tokens': 20000,           # Max tokens for KB context
    'estimated_tokens_per_word': 4,   # Rough conversion factor
}

# ============================================================================
# EXISTING CONFIGURATION (from original config.py)
# ============================================================================

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ChromaDB configuration
CHROMA_DIR = Path("data/chromadb")
CHROMA_COLLECTION_PREFIX = "exception_kb_"

# Embedding model for vectorization
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Fast and accurate

# ============================================================================
# LLM MODELS CONFIGURATION
# ============================================================================

AVAILABLE_MODELS = {
    # Local Ollama Models (Recommended for Privacy)
    "ollama-llama-3.2": {
        "name": "llama3:latest",
        "type": "api",
        "provider": "ollama",
        "description": "Fast, efficient, runs locally",
        "max_length": 4096,
    },
    "ollama-mistral": {
        "name": "Mistral 7B (Ollama)",
        "type": "api",
        "provider": "ollama",
        "description": "Powerful local model",
        "max_length": 8192,
    },
    
    # API Models (Requires API Keys)
    "groq-llama3-70b": {
        "name": "Llama 3 70B (Groq)",
        "type": "api",
        "provider": "groq",
        "description": "Ultra-fast cloud API",
        "max_length": 8192,
    },
    "together-mistral-7b": {
        "name": "Mistral 7B (Together AI)",
        "type": "api",
        "provider": "together",
        "description": "Cost-effective cloud API",
        "max_length": 8192,
    },
    
    # Local Transformer Models
    "t5-base": {
        "name": "T5 Base",
        "type": "local",
        "provider": "local",
        "description": "Text-to-text transformer, 220M params",
        "max_length": 512,
    },
    "flan-t5-large": {
        "name": "FLAN-T5 Large",
        "type": "local",
        "provider": "local",
        "description": "Instruction-tuned, 780M params",
        "max_length": 512,
    },
}

# Default model
DEFAULT_MODEL = "ollama-llama-3.2"

# ============================================================================
# DEDUPLICATION CONFIGURATION
# ============================================================================

DEDUPLICATION_CONFIG = {
    'enabled': True,
    'similarity_threshold': 0.85,      # 85% similarity to group
    'semantic_threshold': 0.90,        # 90% for KB deduplication
    'remove_machine_names': True,
    'normalize_timestamps': True,
    'split_after_processing': True,    # Split groups back to individuals
}

# ============================================================================
# SELF-HEALING CONFIGURATION
# ============================================================================

SELF_HEALING_CONFIG = {
    'enabled': False,  # Disabled by default
    'auto_add_to_kb': False,
    'confidence_threshold': 90,
    'require_manual_review': True,
}

# ============================================================================
# CONFIDENCE SCORING CONFIGURATION
# ============================================================================

# Confidence thresholds
CONFIDENCE_HIGH_THRESHOLD = 80
CONFIDENCE_MEDIUM_THRESHOLD = 70
CONFIDENCE_LOW_THRESHOLD = 60

# Confidence weights when KB is present
CONFIDENCE_WEIGHTS_KB_PRESENT = {
    'llm': 0.4,
    'kb': 0.6,
}

# Confidence weights when KB is absent
CONFIDENCE_WEIGHTS_KB_ABSENT = {
    'llm': 0.8,
    'kb': 0.2,
}

# Code analysis confidence boost
CONFIDENCE_WEIGHTS_WITH_CODE = {
    'llm': 0.3,
    'kb': 0.4,
    'code': 0.3,  # NEW: Additional weight for code analysis
}

# ============================================================================
# KNOWLEDGE BASE COLUMN MAPPINGS
# ============================================================================

KB_COLUMNS = {
    # Excel/CSV column name -> Internal column name
    'Exception Type': 'Exception_Type',
    'ExceptionType': 'Exception_Type',
    'exception_type': 'Exception_Type',
    
    'Message': 'Exception_Message',
    'ExceptionTemplate': 'Exception_Message',
    'Exception_Message': 'Exception_Message',
    
    'Resolution': 'Resolution',
    'resolution': 'Resolution',
    
    'Root Cause': 'Root_Cause',
    'RootCause_text': 'Root_Cause',
    'Summary': 'Root_Cause',
    'Explanation': 'Root_Cause',
    'Root_Cause': 'Root_Cause',
    
    'Action': 'Action',
    'Suggested Step': 'Action',
    'Suggested_Action': 'Action',
    'suggested_step': 'Action',
    
    'EVENT_INFORMATION': 'EVENT_INFORMATION',
    'Event_Information': 'EVENT_INFORMATION',
    
    'Stack_Trace': 'Stack_Trace',
    'StackTrace': 'Stack_Trace',
}

# ============================================================================
# FILE PROCESSING CONFIGURATION
# ============================================================================

# Maximum file size for processing (in MB)
MAX_FILE_SIZE_MB = 500

# Supported file types
SUPPORTED_FILE_TYPES = ['csv', 'xlsx', 'xls']

# Required columns in exception files
REQUIRED_EXCEPTION_COLUMNS = ['LOG_SEQ_NO', 'EVENT_INFORMATION', 'SEVERITY']

# Required columns in KB files
REQUIRED_KB_COLUMNS = ['Exception_Type', 'Resolution', 'EVENT_INFORMATION']

# ============================================================================
# UI CONFIGURATION
# ============================================================================

# Page size for review queue pagination
REVIEW_QUEUE_PAGE_SIZE = 20

# Default confidence threshold for review queue
DEFAULT_REVIEW_THRESHOLD = 70

# Auto-refresh interval for system monitor (seconds)
MONITOR_REFRESH_INTERVAL = 2

# ============================================================================
# PARALLEL PROCESSING CONFIGURATION
# ============================================================================

# Number of worker threads
DEFAULT_WORKERS = 2
MIN_WORKERS = 1
MAX_WORKERS = 8

# Batch size for processing
PROCESSING_BATCH_SIZE = 2

# ============================================================================
# PERSISTENCE CONFIGURATION
# ============================================================================

# Review queue persistence
REVIEW_QUEUE_FILE = Path("data/review_queue_persistent.csv")

# Audit log persistence
AUDIT_LOG_FILE = Path("data/processing_audit_log.csv")

# Processing logs directory
LOGS_DIR = Path("LOGS")

# ============================================================================
# FEATURE FLAGS
# ============================================================================

FEATURES = {
    'code_analysis': CODE_ANALYSIS_ENABLED,
    'cross_module_kb_search': True,
    'review_queue_persistence': True,
    'audit_logging': True,
    'analytics_dashboard': True,
    'system_monitor': True,
    'parallel_processing': True,
    'deduplication': True,
    'self_healing': False,  # Disabled by default
}

# ============================================================================
# EXPORT CONFIGURATION
# ============================================================================

# Export file formats
EXPORT_FORMATS = ['csv', 'json', 'xlsx']

# Timestamp format for exported files
EXPORT_TIMESTAMP_FORMAT = '%Y%m%d_%H%M%S'

# ============================================================================
# VALIDATION RULES
# ============================================================================

# Valid resolution types
VALID_RESOLUTIONS = ['PURGE', 'REPROCESS', 'INVESTIGATE', 'UNDEFINED']

# Valid severity levels
VALID_SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

# ============================================================================
# ERROR MESSAGES
# ============================================================================

ERROR_MESSAGES = {
    'file_not_found': 'File not found: {}',
    'invalid_format': 'Invalid file format. Supported formats: {}',
    'missing_columns': 'Missing required columns: {}',
    'processing_error': 'Error processing file: {}',
    'kb_error': 'Error loading knowledge base: {}',
    'code_repo_not_found': 'Code repository not found at: {}',
    'code_indexing_error': 'Error indexing code repository: {}',
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_code_repository_path() -> bool:
    """Validate that code repository path exists"""
    repo_path = Path(CODE_REPOSITORY_PATH)
    return repo_path.exists() and repo_path.is_dir()

def get_feature_status() -> dict:
    """Get current feature flags status"""
    return FEATURES.copy()

def is_code_analysis_enabled() -> bool:
    """Check if code analysis is enabled and repository is accessible"""
    return FEATURES['code_analysis'] and validate_code_repository_path()


if __name__ == "__main__":
    print("✅ Configuration loaded successfully!")
    print(f"\nCode Repository Path: {CODE_REPOSITORY_PATH}")
    print(f"Code Analysis Enabled: {CODE_ANALYSIS_ENABLED}")
    print(f"Repository Accessible: {validate_code_repository_path()}")
    print(f"\nAvailable LLM Models: {len(AVAILABLE_MODELS)}")
    print(f"Default Model: {DEFAULT_MODEL}")
    print(f"\nFeatures Enabled:")
    for feature, enabled in FEATURES.items():
        print(f"  - {feature}: {'✅' if enabled else '❌'}")
