"""
AI Exception Modeler V7.0 - Streamlit Application
Enterprise Exception Analysis System with Demo Mode
"""

import streamlit as st
import pandas as pd
import logging
import time
import json
import sys
import os
import plotly.express as px
import plotly.graph_objects as go
import config
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from task_queue_manager import get_task_manager
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime
from kb_manager import MultiModuleKBManager
from exception_processor import EnhancedExceptionProcessor
from data_cleaner import JSONParser
from analytics_ai import display_analytics_dashboard_ai, render_module_download_button, generate_ai_insights

# Demo mode imports
try:
    from demo_auth import check_demo_auth, render_demo_login, render_demo_banner
except ImportError:
    # Fallback if demo_auth not available
    def check_demo_auth(): return True
    def render_demo_login(): return True
    def render_demo_banner(): pass


# [2025-12-04] FIX: Increase message size limit for large datasets (180K+ records)
# Reason: Default 200MB limit causes "MessageSizeError" with bulk files
# Purpose: Allow displaying results for large exception files
st.set_page_config(
    page_title="AI Exception Modeler V7.0",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Increase max message size to 500MB for large datasets
if hasattr(st, '_config'):
    st._config.set_option('server.maxMessageSize', 500)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# REVIEW QUEUE PERSISTENCE CONFIGURATION
# ============================================================================
# Purpose: Save review queue to disk so it persists across sessions
# Location: data/review_queue_persistent.csv
# This file stores all review items permanently until they are cleared
# ============================================================================
REVIEW_QUEUE_FILE = Path("data/review_queue_persistent.csv")

# ============================================================================
# AUDIT LOG CONFIGURATION
# ============================================================================
# Purpose: Track all file processing activities for analytics and reporting
# Location: data/processing_audit_log.csv
# Stores: File name, date/time, record counts, confidence scores, resolution counts
# Use case: Analytics, usage tracking, compliance, performance monitoring
# ============================================================================
AUDIT_LOG_FILE = Path("data/processing_audit_log.csv")

# Ensure data directory exists
REVIEW_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# [2025-01-31] REMOVED: Duplicate st.set_page_config() and logging.basicConfig() calls
# These caused Streamlit startup errors - page config is now set once at the top


# ============================================================================
# HELPER FUNCTIONS FOR REVIEW QUEUE PERSISTENCE
# ============================================================================

def load_review_queue_from_disk() -> pd.DataFrame:
    """
    Load review queue from persistent storage on disk.
    
    Returns:
        pd.DataFrame: Loaded review queue, or empty DataFrame if file doesn't exist
    
    Purpose:
        - Restores review queue when user logs in or refreshes page
        - Ensures no data loss between sessions
        - Maintains all pending and completed items
    """
    try:
        if REVIEW_QUEUE_FILE.exists():
            logger.info(f"[PERSISTENCE] Loading review queue from {REVIEW_QUEUE_FILE}")
            df = pd.read_csv(REVIEW_QUEUE_FILE)
            logger.info(f"[PERSISTENCE] Loaded {len(df)} items from disk")
            return df
        else:
            logger.info("[PERSISTENCE] No existing review queue file found, starting fresh")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"[PERSISTENCE] Error loading review queue: {str(e)}")
        return pd.DataFrame()

def save_review_queue_to_disk(df: pd.DataFrame):
    """
    Save review queue to persistent storage on disk.
    
    Args:
        df: DataFrame containing review queue items
    
    Purpose:
        - Saves review queue after every change (add, update, delete)
        - Ensures data persists across browser refresh, logout, restart
        - Creates backup of all review items
    
    When called:
        - After adding new items to review queue
        - After marking items as completed (Purge/Reprocess)
        - After clearing completed items
        - After any user edits to User_Resolution or User_Suggested_Step
    """
    try:
        logger.info(f"[PERSISTENCE] Saving {len(df)} items to disk at {REVIEW_QUEUE_FILE}")
        df.to_csv(REVIEW_QUEUE_FILE, index=False)
        logger.info("[PERSISTENCE] Review queue saved successfully")
    except Exception as e:
        logger.error(f"[PERSISTENCE] Error saving review queue: {str(e)}")
        st.error(f"⚠️ Failed to save review queue: {str(e)}")

def load_audit_log_from_disk() -> pd.DataFrame:
    """
    Load processing audit log from disk.
    
    Returns:
        pd.DataFrame: Audit log with all processing activities
    
    Purpose:
        - Loads historical processing data for analytics
        - Shows what files were processed, when, and with what results
        - Enables usage tracking and performance monitoring
    """
    try:
        if AUDIT_LOG_FILE.exists():
            logger.info(f"[AUDIT] Loading audit log from {AUDIT_LOG_FILE}")
            df = pd.read_csv(AUDIT_LOG_FILE)
            # Convert timestamp to datetime
            if 'Upload_DateTime' in df.columns:
                df['Upload_DateTime'] = pd.to_datetime(df['Upload_DateTime'])
            logger.info(f"[AUDIT] Loaded {len(df)} audit entries from disk")
            return df
        else:
            logger.info("[AUDIT] No existing audit log found, creating new one")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"[AUDIT] Error loading audit log: {str(e)}")
        return pd.DataFrame()

def save_audit_entry(file_name: str, module_name: str, total_records: int, 
                     reprocess_count: int, purge_count: int, investigate_count: int,
                     review_count: int, avg_confidence: float, processing_time_seconds: float = 0):
    """
    Save a new audit entry for a file processing activity.
    
    Args:
        file_name: Name of the uploaded file
        module_name: Module being processed
        total_records: Total number of exceptions processed
        reprocess_count: Number of items marked for reprocess
        purge_count: Number of items marked for purge
        investigate_count: Number of items marked for investigation
        review_count: Number of items sent to review queue
        avg_confidence: Average confidence score of all processed items
        processing_time_seconds: Time taken to process the file in seconds
    
    Purpose:
        - Creates audit trail of all processing activities
        - Enables analytics and reporting
        - Tracks usage patterns over time
        - Provides compliance and accountability
    
    When called:
        - After successfully processing an exception file
        - Records all key metrics for later analysis
    """
    try:
        # Load existing audit log
        audit_df = load_audit_log_from_disk()
        
        # Create new entry
        new_entry = {
            'Upload_DateTime': datetime.now(),
            'File_Name': file_name,
            'Module': module_name,
            'Total_Records': total_records,
            'Reprocess_Count': reprocess_count,
            'Purge_Count': purge_count,
            'Investigate_Count': investigate_count,
            'Review_Count': review_count,
            'Avg_Confidence': round(avg_confidence, 2),
            'Processing_Time_Minutes': round(processing_time_seconds / 60, 2)
        }
        
        # Append to audit log
        new_entry_df = pd.DataFrame([new_entry])
        if audit_df.empty:
            audit_df = new_entry_df
        else:
            audit_df = pd.concat([audit_df, new_entry_df], ignore_index=True)
        
        # Save to disk
        logger.info(f"[AUDIT] Saving audit entry for file: {file_name}")
        audit_df.to_csv(AUDIT_LOG_FILE, index=False)
        logger.info("[AUDIT] Audit entry saved successfully")
        
    except Exception as e:
        logger.error(f"[AUDIT] Error saving audit entry: {str(e)}")
        # Don't show error to user - audit logging should be silent

# ============================================================================
# INITIALIZE SESSION STATE WITH PERSISTENT DATA
# ============================================================================
# Initialize session state variables
if 'review_queue' not in st.session_state:
    # [2025-12-01] CRITICAL: Load from disk on first access
    # This ensures review queue persists across sessions
    st.session_state.review_queue = load_review_queue_from_disk()
    logger.info(f"[INIT] Review queue initialized with {len(st.session_state.review_queue)} items from disk")
if 'kb_manager' not in st.session_state:
    st.session_state.kb_manager = MultiModuleKBManager(config.CHROMA_DIR)
if 'processed_results' not in st.session_state:
    st.session_state.processed_results = pd.DataFrame()
if 'show_review_notification' not in st.session_state:
    st.session_state.show_review_notification = False

def display_analytics_dashboard(df):
    """
    World-class Analytics Dashboard for Exception Processing
    """
    # Filter data
    review_df = df[df['Requires_Review'] == True].copy() if 'Requires_Review' in df.columns else pd.DataFrame()
    automated_df = df[df['Requires_Review'] == False].copy() if 'Requires_Review' in df.columns else df.copy()
    
    # Calculate metrics
    total_processed = len(df)
    review_required = len(review_df)
    auto_purged = len(automated_df[automated_df['Resolution'] == 'PURGE']) if 'Resolution' in automated_df.columns else 0
    investigate = len(automated_df[automated_df['Resolution'] == 'INVESTIGATE']) if 'Resolution' in automated_df.columns else 0
    avg_confidence = df['Confidence_Score'].mean() if 'Confidence_Score' in df.columns and len(df) > 0 else 0
    
    st.header("📊 Exception Processing Analytics")
    st.markdown("---")
    
    # Primary KPI + Secondary KPIs
    primary_col, secondary_col = st.columns([1, 3])
    
    with primary_col:
            st.markdown(f"""
    <div style="background: linear-gradient(135deg, #ff6b6b, #ee5a24); padding: 5px; border-radius: 1px; text-align: center; box-shadow: 0 2px 2px rgba(70, 20, 20, 0.2); margin-bottom: 2px; width: 50%; margin: auto;">
        <div style="color: white; font-size: 14px; font-weight: 500; margin-bottom: 2px;">REVIEW REQUIRED</div>
        <div style="color: white; font-size: 32px; font-weight: bold;">{review_required}</div>
    </div>
    """, unsafe_allow_html=True)
    
    with secondary_col:
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("🗑️ Auto-Purged", auto_purged)
        with kpi2:
            st.metric("🔍 Investigate", investigate)
        with kpi3:
            st.metric("📈 Total Processed", total_processed)
        with kpi4:
            st.metric("🎯 Avg. Confidence", f"{avg_confidence:.0f}%")
    
    st.markdown("---")
    st.subheader("📈 Visual Analytics")
    
    # Charts
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("#### Resolution Distribution")
        if 'Resolution' in df.columns and len(df) > 0:
            resolution_counts = df['Resolution'].value_counts()
            fig_donut = go.Figure(data=[go.Pie(
                labels=resolution_counts.index,
                values=resolution_counts.values,
                hole=0.4,
                textinfo='label+percent',
                marker=dict(colors=['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#feca57'])
            )])
            fig_donut.update_layout(height=350, showlegend=True)
            fig_donut.add_annotation(text=f"<b>{total_processed}</b><br>Total", x=0.5, y=0.5, font_size=16, showarrow=False)
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.info("No resolution data available")
    
    with chart_col2:
        st.markdown("#### Top Exception Types")
        if 'Exception_Type' in df.columns and len(df) > 0:
            exception_counts = df['Exception_Type'].value_counts().head(10)
            fig_bar = px.bar(x=exception_counts.values, y=exception_counts.index, orientation='h')
            fig_bar.update_layout(height=350, showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No exception type data available")
    
    # # Review items table
    # if len(review_df) > 0:
    #     st.subheader("🔍 Items Requiring Manual Review")
    #     display_review_df = review_df.copy()
    #     display_review_df['Reason_for_Review'] = display_review_df.apply(
    #         lambda row: "Low Confidence" if row.get('Confidence_Score', 100) < 70 else "Investigation Rule", axis=1
    #     )
        
    #     col1, col2, col3 = st.columns(3)
    #     with col1:
    #         st.metric("Low Confidence", len(display_review_df[display_review_df['Reason_for_Review'] == 'Low Confidence']))
    #     with col2:
    #         st.metric("Investigation Rule", len(display_review_df[display_review_df['Reason_for_Review'] == 'Investigation Rule']))
    #     with col3:
    #         st.metric("Total Review Items", len(display_review_df))
        
    #     st.dataframe(display_review_df, use_container_width=True, height=400)
    # else:
    #     st.success("🎉 Excellent! No items require manual review.")


# [2025-12-05] REMOVED: process_review_queue_actions function
# Reason: This function was never called and referenced the removed Final_Resolution column
# The actual review queue processing is now done inline in the Purge/Reprocess button handlers

def main():
    # Load custom CSS theme
    css_path = Path(__file__).parent / "static" / "custom.css"
    if css_path.exists():
        with open(css_path, 'r') as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    
    # Demo mode authentication check
    if config.DEMO_MODE:
        if not check_demo_auth():
            render_demo_login()
            return
        render_demo_banner()
    
    # Professional header
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
        <h1 style="color: white; margin: 0; font-size: 2rem;">🤖 AI Exception Modeler V7.0</h1>
        <p style="color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0; font-size: 1rem;">
            Enterprise Exception Analysis with AI-Powered Resolution • Review Queue • ChromaDB Knowledge Base
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show review queue notification if items were added
    if st.session_state.show_review_notification:
        st.info(f"📋 {len(st.session_state.review_queue[st.session_state.review_queue.get('Review_Status', 'Pending') == 'Pending'])} items added to Review Queue. Check the Review Queue tab to review them.")
        st.session_state.show_review_notification = False
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Model selection
        model_options = {
            key: f"{key} - {info['description']}" 
            for key, info in config.AVAILABLE_MODELS.items()
        }
        
        # Set default to ollama-llama-3.2 if available, otherwise first model
        default_index = 0
        if "ollama-llama-3.2" in model_options:
            default_index = list(model_options.keys()).index("ollama-llama-3.2")
        
        selected_model = st.selectbox(
            "Select LLM Model:",
            options=list(model_options.keys()),
            format_func=lambda x: model_options[x],
            index=default_index
        )
        
        st.info(f"**Selected**: {config.AVAILABLE_MODELS[selected_model]['name']}")
        
        # Module selection
        st.subheader("📦 Module Selection")
        
        # Define standard modules
        standard_modules = [
            "ClaimGeneration",
            "ClaimPricing"
        ]
        
        # Get loaded modules from KB manager
        loaded_modules = []
        if st.session_state.kb_manager:
            loaded_modules = st.session_state.kb_manager.get_loaded_modules()
        
        # Combine standard modules with loaded modules (remove duplicates)
        all_modules = sorted(list(set(standard_modules + loaded_modules)))
        
        # Add "Other (Custom)" option
        all_modules.append("Other (Custom)")
        
        # Module dropdown
        module_selection = st.selectbox(
            "Select Module:",
            options=all_modules,
            index=0 if "ClaimGeneration" in all_modules else 0,
            help="Select the module for exception processing"
        )
        
        # If "Other (Custom)" is selected, show text input
        if module_selection == "Other (Custom)":
            module_name = st.text_input(
                "Enter Custom Module Name:",
                value="",
                placeholder="e.g., MyCustomModule",
                help="Enter a custom module name"
            )
            if not module_name:
                st.warning("⚠️ Please enter a custom module name")
        else:
            module_name = module_selection
        
        # Deduplication settings
        st.subheader("🔄 Deduplication")
        enable_dedup = st.checkbox("Enable Enhanced Deduplication", value=True)
        
        if enable_dedup:
            similarity_threshold = st.slider(
                "Similarity Threshold", 
                0.70, 0.95, 0.85, 0.05,
                help="Higher = stricter grouping"
            )
            config.DEDUPLICATION_CONFIG['similarity_threshold'] = similarity_threshold
        
        # Review threshold setting
        st.subheader("🔍 Review Settings")
        confidence_threshold = st.slider(
            "Review Threshold (%)",
            min_value=50, max_value=90, value=70, step=5,
            help="Items below this confidence score will be added to review queue"
        )
        
        # Knowledge Base settings
        st.subheader("📚 Knowledge Base Status")
        kb_append_mode = st.checkbox("Append to existing KB", value=True,
                                    help="If checked, new KB data will be added to existing module KB")
        
        # Show loaded modules and review queue status
        if st.session_state.kb_manager:
            loaded_modules = st.session_state.kb_manager.get_loaded_modules()
            if loaded_modules:
                st.success(f"✅ Loaded KBs: {', '.join(loaded_modules)}")
            else:
                st.warning("⚠️ No KB loaded yet. Upload in KB tab.")
        
        # Review queue status
        if not st.session_state.review_queue.empty:
            pending_count = len(st.session_state.review_queue[st.session_state.review_queue.get('Review_Status', 'Pending') == 'Pending'])
            if pending_count > 0:
                st.warning(f"📋 {pending_count} items pending review")
    
    # Main area with tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📤 Process Exceptions", 
        "📚 Knowledge Base", 
        "📋 Review Queue",
        "📊 Analytics",
        "🖥️ System Monitor",
        "ℹ️ Help"
    ])
    
    # Tab 1: Process Exceptions
    with tab1:
        st.header("Process Exceptions")
        
        # Info about KB status for current module
        if module_name not in st.session_state.kb_manager.get_loaded_modules():
            st.warning(f"⚠️ No Knowledge Base loaded for module: {module_name}. System will work but with lower confidence. Upload KB in the Knowledge Base tab.")
        
        # File uploader - Streamlit native
        uploaded_file = st.file_uploader(
            "📁 Upload Exception CSV/Excel",
            type=['csv', 'xlsx'],
            help="Must contain LOG_SEQ_NO, EVENT_INFORMATION, SEVERITY columns"
        )
        
        if uploaded_file:
            try:
                # Read the file based on extension
                if uploaded_file.name.endswith('.csv'):
                    input_df = pd.read_csv(uploaded_file)
                else:
                    input_df = pd.read_excel(uploaded_file)
                
                st.success(f"✅ Loaded {len(input_df)} exceptions from {uploaded_file.name}")
                
                with st.expander("Preview Input Data"):
                    st.dataframe(input_df.head(10))
                
                # [2025-12-01] Process button - threshold moved to sidebar
                process_btn = st.button("🚀 Process Exceptions", type="primary", use_container_width=True)
                
                if process_btn:
                    # 🔥 NEW: Submit to task queue for parallel processing
                    task_manager = get_task_manager()
                    task_id = task_manager.submit_task(
                        module_name=module_name,
                        input_df=input_df,
                        model_key=selected_model,
                        user_id="streamlit_user"
                    )
                    
                    # Store task ID in session state
                    st.session_state.current_task_id = task_id
                    st.session_state.processing_start_time = time.time()
                    
                    st.success(f"✅ Task submitted! Processing {len(input_df)} exceptions...")
                    st.info("🔄 Results will appear below as they're ready. Check the System Monitor tab to see live progress.")
                    
                    # Show progress monitoring
                    progress_placeholder = st.empty()
                    status_placeholder = st.empty()
                    
                    # Poll for updates
                    output_df = None
                    while True:
                        status = task_manager.get_task_status(task_id)
                        
                        if not status:
                            st.error("❌ Task not found")
                            break
                        
                        # Update progress
                        with progress_placeholder.container():
                            st.progress(
                                status['progress_percentage'] / 100,
                                text=f"Processing: {status['processed_records']}/{status['total_records']} exceptions ({status['progress_percentage']:.1f}%)"
                            )
                        
                        # Update status
                        with status_placeholder.container():
                            if status['processed_records'] > 0:
                                st.info(f"✅ {status['processed_records']} exceptions processed so far...")
                        
                        # Check if completed
                        if status['status'] == 'completed':
                            # Get final results
                            results = task_manager.get_task_results(task_id)
                            if results:
                                output_df = pd.concat(results, ignore_index=True)
                            
                            processing_time_seconds = time.time() - st.session_state.processing_start_time
                            break
                        elif status['status'] == 'failed':
                            st.error(f"❌ Processing failed: {status['error']}")
                            break
                        
                        # Wait before next poll
                        time.sleep(2)
                    
                    # 🔥 If we got results, continue with EXISTING processing logic
                    if output_df is not None:
                        # Calculate processing time
                        processing_time_seconds = time.time() - st.session_state.processing_start_time
                        
                        # [2025-11-25] Save processing log to LOGS folder with InputFilename_Date_Timestamp format
                        # Purpose: Restore log saving functionality that was working previously
                        try:
                            import os
                            logs_dir = os.path.join(os.path.dirname(__file__), 'LOGS')
                            os.makedirs(logs_dir, exist_ok=True)
                            
                            # Extract input filename without extension
                            input_filename = os.path.splitext(uploaded_file.name)[0]
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            log_filename = f"{input_filename}_{timestamp}.csv"
                            log_filepath = os.path.join(logs_dir, log_filename)
                            
                            # Save processing results
                            output_df.to_csv(log_filepath, index=False)
                            logger.info(f"[LOG SAVED] Processing results saved to: {log_filepath}")
                        except Exception as log_error:
                            logger.warning(f"[LOG SAVE FAILED] Could not save processing log: {log_error}")
                        
                        # Store results in session state
                        st.session_state.processed_results = output_df
                        st.session_state.processing_complete = True
                        st.session_state.confidence_threshold = confidence_threshold
                        
                        # [2025-11-24] Enhanced review queue logic to include INVESTIGATE, UNDEFINED, and low-confidence items
                        # Purpose: Add items requiring human review to review queue
                        # Ensure review queue data matches processed_results exactly
                        # [2025-11-25] Always add items to review queue (checkbox removed)
                        review_added_count = 0
                        # Collect items for review queue - use Exception_ID as unique identifier
                        review_exception_ids = set()
                        review_items = pd.DataFrame()
                        
                        # Add low-confidence items (below threshold)
                        if 'Confidence_Score' in output_df.columns:
                            low_confidence = output_df[output_df['Confidence_Score'] <= confidence_threshold].copy()
                            if not low_confidence.empty:
                                low_confidence['Review_Reason'] = 'Low Confidence'
                                review_items = pd.concat([review_items, low_confidence], ignore_index=True)
                                if 'Exception_ID' in low_confidence.columns:
                                    review_exception_ids.update(low_confidence['Exception_ID'].values)
                        
                        # Add INVESTIGATE items (requires manual review)
                        if 'Resolution' in output_df.columns:
                            investigate_items = output_df[output_df['Resolution'] == 'INVESTIGATE'].copy()
                            if not investigate_items.empty:
                                investigate_items['Review_Reason'] = 'Investigate'
                                # Avoid duplicates: only add investigate items not already added
                                if 'Exception_ID' in investigate_items.columns:
                                    investigate_items = investigate_items[~investigate_items['Exception_ID'].isin(review_exception_ids)]
                                if not investigate_items.empty:
                                    review_items = pd.concat([review_items, investigate_items], ignore_index=True)
                                    review_exception_ids.update(investigate_items['Exception_ID'].values)
                        
                        # Add UNDEFINED resolution items (parsing errors or LLM failures)
                        if 'Resolution' in output_df.columns:
                            undefined_items = output_df[output_df['Resolution'] == 'UNDEFINED'].copy()
                            if not undefined_items.empty:
                                undefined_items['Review_Reason'] = 'Undefined Resolution'
                                # Avoid duplicates: only add undefined items not already added
                                if 'Exception_ID' in undefined_items.columns:
                                    undefined_items = undefined_items[~undefined_items['Exception_ID'].isin(review_exception_ids)]
                                if not undefined_items.empty:
                                    review_items = pd.concat([review_items, undefined_items], ignore_index=True)
                                    review_exception_ids.update(undefined_items['Exception_ID'].values)
                        
                        # Add metadata to review items
                        if not review_items.empty:
                            review_items['Review_Status'] = 'Pending'
                            review_items['Module'] = module_name
                            review_items['Added_To_Review'] = datetime.now().isoformat()
                            
                            # [2025-11-24] CRITICAL FIX: Preserve index when adding to review queue
                            # Reset index to ensure unique integer indices for proper tracking
                            if not st.session_state.review_queue.empty:
                                # Get the max index from existing queue
                                max_idx = st.session_state.review_queue.index.max()
                                # Reset review_items index to start after max_idx
                                review_items = review_items.reset_index(drop=True)
                                review_items.index = review_items.index + max_idx + 1
                                
                                st.session_state.review_queue = pd.concat([
                                    st.session_state.review_queue, 
                                    review_items
                                ], ignore_index=False)  # Keep indices
                            else:
                                review_items = review_items.reset_index(drop=True)
                                st.session_state.review_queue = review_items
                            
                            review_added_count = len(review_items)
                            logger.info(f"[REVIEW QUEUE] Added {review_added_count} items to review queue")
                            
                            # [2025-12-01] PERSISTENCE: Save to disk after adding new items
                            # This ensures new review items persist across sessions
                            save_review_queue_to_disk(st.session_state.review_queue)
                            
                            st.session_state.show_review_notification = True
                        
                        # [2025-12-01] AUDIT LOG: Record processing activity
                        # Calculate metrics for audit trail
                        reprocess_count = len(output_df[output_df['Resolution'] == 'REPROCESS']) if 'Resolution' in output_df.columns else 0
                        purge_count = len(output_df[output_df['Resolution'] == 'PURGE']) if 'Resolution' in output_df.columns else 0
                        investigate_count = len(output_df[output_df['Resolution'] == 'INVESTIGATE']) if 'Resolution' in output_df.columns else 0
                        avg_confidence = output_df['Confidence_Score'].mean() if 'Confidence_Score' in output_df.columns else 0.0
                        
                        # Save audit entry for this processing activity
                        save_audit_entry(
                            file_name=uploaded_file.name,
                            module_name=module_name,
                            total_records=len(output_df),
                            reprocess_count=reprocess_count,
                            purge_count=purge_count,
                            investigate_count=investigate_count,
                            review_count=review_added_count,
                            avg_confidence=avg_confidence,
                            processing_time_seconds=processing_time_seconds
                        )
                        
                        # Show results
                        st.success(f"✅ Processing Complete! Analyzed {len(output_df)} exceptions")
                        
                        if review_added_count > 0:
                            st.warning(f"📋 {review_added_count} items added to Review Queue (low-confidence + investigate). Go to Review Queue tab to review them.")
                
                # [2025-11-24] Display results from session state (outside button handler)
                # Purpose: Keep results visible when users interact with filters
                if 'processed_results' in st.session_state and st.session_state.get('processing_complete', False):
                    output_df = st.session_state.processed_results
                    confidence_threshold = st.session_state.get('confidence_threshold', 70)
                    
                    st.markdown("---")
                    
                    # [2025-11-21] Enhanced statistics with Review Required metric
                    # Purpose: Display comprehensive metrics including items needing review
                    col1, col2, col3, col4, col5 = st.columns(5)
                    
                    with col1:
                        st.metric("Total Processed", len(output_df))
                    with col2:
                        reprocess = len(output_df[output_df['Resolution'] == 'REPROCESS'])
                        st.metric("♻️ Reprocess", reprocess)
                    with col3:
                        purge = len(output_df[output_df['Resolution'] == 'PURGE'])
                        st.metric("🗑️ Purge", purge)
                    with col4:
                        investigate = len(output_df[output_df['Resolution'] == 'INVESTIGATE'])
                        st.metric("🔍 Investigate", investigate)
                    with col5:
                        # Calculate Review Required
                        review_required_ids = set()
                        if 'Exception_ID' in output_df.columns:
                            investigate_ids = output_df[output_df['Resolution'] == 'INVESTIGATE']['Exception_ID'].unique()
                            review_required_ids.update(investigate_ids)
                            if 'Confidence_Score' in output_df.columns:
                                low_conf_ids = output_df[output_df['Confidence_Score'] <= confidence_threshold]['Exception_ID'].unique()
                                review_required_ids.update(low_conf_ids)
                        needs_review_count = len(review_required_ids)
                        st.metric("📋 Review Required", needs_review_count,
                                help="Unique exceptions requiring review (investigate + low confidence)")
                    
                    # Show confidence metrics
                    if 'Confidence_Score' in output_df.columns:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            avg_conf = output_df['Confidence_Score'].mean()
                            st.metric("Avg Confidence", f"{avg_conf:.0f}%")
                        with col2:
                            high_conf = len(output_df[output_df['Confidence_Score'] >= 80])
                            st.metric("High Confidence", high_conf)
                        with col3:
                            low_conf = len(output_df[output_df['Confidence_Score'] <= confidence_threshold])
                            st.metric("Low Confidence", low_conf)
                    
                    # Show output
                    st.subheader("📊 Processing Results")
                    st.info("📝 All processed exceptions are shown below. Items in the Review Queue are also included here with their complete analysis.")
                            
                    # [2025-11-24] Add search/filter functionality for Processing Results
                    # Purpose: Help users find specific exceptions in large result sets
                    # Initialize session state for filters
                    if 'proc_search_id' not in st.session_state:
                        st.session_state.proc_search_id = ''
                    if 'proc_resolution_filter' not in st.session_state:
                        st.session_state.proc_resolution_filter = 'All'
                    if 'proc_type_filter' not in st.session_state:
                        st.session_state.proc_type_filter = 'All'
                    if 'proc_show_low_conf' not in st.session_state:
                        st.session_state.proc_show_low_conf = False
                    
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                            
                    with col1:
                        search_id = st.text_input(
                            "🔍 Search by Exception ID",
                            placeholder="Enter Exception ID (e.g., 2092898863)",
                            value=st.session_state.proc_search_id,
                            key="search_exception_id"
                        )
                        st.session_state.proc_search_id = search_id
                            
                    with col2:
                        resolution_filter = st.selectbox(
                            "Filter by Resolution",
                            options=['All', 'REPROCESS', 'PURGE', 'INVESTIGATE', 'UNDEFINED'],
                            index=['All', 'REPROCESS', 'PURGE', 'INVESTIGATE', 'UNDEFINED'].index(st.session_state.proc_resolution_filter),
                            key="result_resolution_filter"
                        )
                        st.session_state.proc_resolution_filter = resolution_filter
                            
                    with col3:
                        if 'Exception_Type' in output_df.columns:
                            unique_types = ['All'] + sorted(output_df['Exception_Type'].unique().tolist())
                            try:
                                type_idx = unique_types.index(st.session_state.proc_type_filter)
                            except ValueError:
                                type_idx = 0
                            type_filter = st.selectbox(
                                "Filter by Type",
                                options=unique_types,
                                index=type_idx,
                                key="result_type_filter"
                            )
                            st.session_state.proc_type_filter = type_filter
                        else:
                            type_filter = 'All'
                            
                    with col4:
                        show_low_conf = st.checkbox(
                            "Low Confidence Only",
                            value=st.session_state.proc_show_low_conf,
                            key="show_low_conf"
                        )
                        st.session_state.proc_show_low_conf = show_low_conf
                    
                    # Apply filters to output_df
                    filtered_output = output_df.copy()
                    
                    if search_id:
                        if 'Exception_ID' in filtered_output.columns:
                            filtered_output = filtered_output[filtered_output['Exception_ID'].str.contains(search_id, case=False, na=False)]
                    
                    if resolution_filter != 'All':
                        if 'Resolution' in filtered_output.columns:
                            filtered_output = filtered_output[filtered_output['Resolution'] == resolution_filter]
                    
                    if type_filter != 'All':
                        if 'Exception_Type' in filtered_output.columns:
                            filtered_output = filtered_output[filtered_output['Exception_Type'] == type_filter]
                    
                    if show_low_conf:
                        if 'Confidence_Score' in filtered_output.columns:
                            filtered_output = filtered_output[filtered_output['Confidence_Score'] <= confidence_threshold]
                    
                    # Show filtered count
                    if len(filtered_output) < len(output_df):
                        st.info(f"📊 Showing {len(filtered_output)} of {len(output_df)} records (filtered)")
                    
                    # [2025-11-25] Check if filtered results are empty and show appropriate message
                    # Purpose: Prevent showing empty table when no records match filters
                    if len(filtered_output) == 0:
                        st.warning("⚠️ No records match the selected filters.")
                    else:
                        # Display columns that exist
                        display_columns = [col for col in filtered_output.columns if col in filtered_output.columns]
                        
                        # Add sequential row numbers for easy reference
                        filtered_display = filtered_output[display_columns].copy()
                        _ = filtered_display.insert(0, 'Row #', range(1, len(filtered_display) + 1))
                        
                        # [2025-11-25] Convert Requires_Review boolean to YES/NO text
                        # Purpose: Fix checkbox display issue - show YES or NO instead of checkboxes
                        if 'Requires_Review' in filtered_display.columns:
                            filtered_display['Requires_Review'] = filtered_display['Requires_Review'].apply(
                                lambda x: 'YES' if x else 'NO'
                            )
                        
                        # Configure column display for better readability
                        column_config = {
                            "Row #": st.column_config.NumberColumn(
                                "Row #",
                                help="Record number",
                                width="small"
                            ),
                            "Exception_ID": st.column_config.TextColumn(
                                "Exception_ID",
                                width="medium"
                            ),
                            "Module": st.column_config.TextColumn(
                                "Module",
                                width="small"
                            ),
                            "Exception_Type": st.column_config.TextColumn(
                                "Exception_Type",
                                width="medium"
                            ),
                            "Exception_Message": st.column_config.TextColumn(
                                "Exception_Message",
                                width="large"
                            ),
                            "Root_Cause": st.column_config.TextColumn(
                                "Root_Cause",
                                width="large"
                            ),
                            "Resolution": st.column_config.TextColumn(
                                "Resolution",
                                width="small"
                            ),
                            "Confidence_Score": st.column_config.NumberColumn(
                                "Confidence_Score",
                                width="small",
                                format="%d%%"
                            ),
                            "Requires_Review": st.column_config.TextColumn(
                                "Requires_Review",
                                width="small"
                            )
                        }
                        
                        # Display table with improved formatting
                        # [2025-11-25] Set dynamic height based on actual row count to avoid empty rows
                        # Purpose: Remove extra empty rows when there are few records
                        row_height = 35  # pixels per row
                        header_height = 38  # header row height
                        num_rows = len(filtered_display)
                        # Calculate height: header + (rows * row_height), min 150, max 600
                        table_height = min(max(header_height + (num_rows * row_height), 150), 600)
                        
                        st.dataframe(
                            filtered_display,
                            column_config=column_config,
                            use_container_width=True,
                            hide_index=True,
                            height=table_height
                        )
                    
                    # Download options
                    st.markdown("---")
                    col1, col2 = st.columns(2)
                    with col1:
                        csv = output_df.to_csv(index=False)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        output_filename = f"{module_name}_Result_{timestamp}.csv"
                        st.download_button(
                            "📅 Download Full Results (CSV)",
                            csv,
                            output_filename,
                            "text/csv",
                            key="download_csv_results"
                        )
                    
                    with col2:
                        # Summary report
                        summary = {
                            'Module': module_name,
                            'Processing_Date': datetime.now().isoformat(),
                            'Total_Exceptions': len(output_df),
                            'Reprocess_Count': reprocess,
                            'Purge_Count': purge,
                            'Investigate_Count': investigate,
                            'Needs_Review_Count': needs_review_count,
                            'Avg_Confidence': f"{avg_conf:.1f}%" if 'Confidence_Score' in output_df.columns else 'N/A'
                        }
                        summary_json = json.dumps(summary, indent=2)
                        st.download_button(
                            "📄 Download Summary (JSON)",
                            summary_json,
                            f"{module_name}_Summary_{timestamp}.json",
                            "application/json",
                            key="download_json_summary"
                        )   
                        
            except Exception as e:
                st.error(f"❌ Error loading file: {str(e)}")
                logger.error(f"File loading error: {str(e)}", exc_info=True)

    
    # Tab 2: Knowledge Base Management
    with tab2:
        st.header(f"📚 Knowledge Base Management - Module: {module_name}")
        
        # Instructions
        st.info("""
        Upload a CSV/Excel file with the following columns:
        - **Exception_Type**: Type of exception (e.g., AuthorizationError)
        - **Exception_Message**: Pattern or message
        - **Resolution**: REPROCESS/PURGE/INVESTIGATE
        - **Root_Cause**: Why the error occurred
        - **Action**: Recommended action to take
        """)
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            kb_file = st.file_uploader(
                "Upload Knowledge Base File", 
                type=['csv', 'xlsx'], 
                key='kb_upload'
            )
        
        with col2:
            # Show current KB stats
            if module_name in st.session_state.kb_manager.get_loaded_modules():
                stats = st.session_state.kb_manager.get_module_stats(module_name)
                if stats:
                    entries_count = stats.get('entries_count', 0)
                    unique_patterns = stats.get('unique_signatures', 0)
                    
                    # [2025-11-24] Fix: If unique_patterns is 0 but we have entries, get actual count from signatures
                    if unique_patterns == 0 and entries_count > 0:
                        # Get actual signature count from module_signatures
                        if module_name in st.session_state.kb_manager.module_signatures:
                            unique_patterns = len(st.session_state.kb_manager.module_signatures[module_name])
                            logger.info(f"[KB STATS] Recalculated unique patterns from signatures: {unique_patterns}")
                    
                    st.metric("KB Entries", entries_count)
                    st.metric("Unique Patterns", unique_patterns)
                    st.success("✅ KB Active")
            else:
                st.metric("KB Entries", 0)
                st.warning("⚠️ No KB for this module")
        
        if kb_file:
            try:
                # Read the file
                if kb_file.name.endswith('.csv'):
                    kb_df = pd.read_csv(kb_file)
                else:
                    kb_df = pd.read_excel(kb_file)
                
                st.success(f"✅ Loaded {len(kb_df)} KB entries from {kb_file.name}")
                
                with st.expander("Preview KB Data"):
                    st.dataframe(kb_df)
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # [2025-11-19] Updated to use 'width' instead of deprecated 'use_container_width'
                    add_kb_btn = st.button(
                        "📚 Add to Knowledge Base", 
                        type="primary",
                        width="stretch"
                    )
                
                with col2:
                    replace_kb_btn = st.button(
                        "🔄 Replace Existing KB",
                        type="secondary",
                        width="stretch"
                    )
                
                with col3:
                    clear_kb_btn = st.button(
                        "🗑️ Clear Module KB",
                        type="secondary",
                        width="stretch"
                    )
                
                if add_kb_btn:
                    with st.spinner(f"Adding to {module_name} knowledge base..."):
                        result = st.session_state.kb_manager.load_or_append_knowledge_base(
                            kb_df, module_name, append_mode=True
                        )
                        
                        if result['status'] == 'success':
                            st.success(f"✅ Added {result['entries']} entries to {module_name} KB")
                            if result.get('duplicates_removed', 0) > 0:
                                st.info(f"Removed {result['duplicates_removed']} duplicate entries")
                            if result.get('new_entries', 0) > 0:
                                st.info(f"Added {result['new_entries']} new unique patterns")
                        else:
                            st.error(f"Error: {result.get('message', 'Unknown error')}")
                
                if replace_kb_btn:
                    with st.spinner(f"Replacing {module_name} knowledge base..."):
                        result = st.session_state.kb_manager.load_or_append_knowledge_base(
                            kb_df, module_name, append_mode=False
                        )
                        
                        if result['status'] == 'success':
                            st.success(f"✅ Replaced {module_name} KB with {result['entries']} entries")
                            if result.get('duplicates_removed', 0) > 0:
                                st.info(f"Removed {result['duplicates_removed']} duplicate entries")
                        else:
                            st.error(f"Error: {result.get('message', 'Unknown error')}")
                
                if clear_kb_btn:
                    if st.session_state.kb_manager.clear_module_kb(module_name):
                        st.success(f"✅ Cleared knowledge base for {module_name}")
                    else:
                        st.warning(f"No knowledge base found for {module_name}")
                        
            except Exception as e:
                st.error(f"❌ Error processing KB file: {str(e)}")
                logger.error(f"KB processing error: {str(e)}", exc_info=True)
        
        # Show all loaded modules
        st.subheader("📂 All Loaded Knowledge Bases")
        loaded_modules = st.session_state.kb_manager.get_loaded_modules()
        
        if loaded_modules:
            kb_stats_data = []
            for mod in loaded_modules:
                stats = st.session_state.kb_manager.get_module_stats(mod)
                if stats:
                    entries_count = stats.get('entries_count', 0)
                    unique_patterns = stats.get('unique_signatures', 0)
                    
                    # [2025-11-24] Fix: Recalculate unique patterns if 0 but entries exist
                    if unique_patterns == 0 and entries_count > 0:
                        if mod in st.session_state.kb_manager.module_signatures:
                            unique_patterns = len(st.session_state.kb_manager.module_signatures[mod])
                    
                    kb_stats_data.append({
                        'Module': mod,
                        'Entries': entries_count,
                        'Unique Patterns': unique_patterns,
                        'Last Updated': stats.get('last_updated', 'Unknown')[:19]  # Trim to date/time
                    })
            
            if kb_stats_data:
                kb_stats_df = pd.DataFrame(kb_stats_data)
                st.dataframe(kb_stats_df, width="stretch")
                
                # [2025-12-01] KB DOWNLOAD FUNCTIONALITY
                # Allow users to download KB data for any loaded module
                st.markdown("---")
                st.subheader("📥 Download Knowledge Base")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    # Dropdown to select module
                    download_module = st.selectbox(
                        "Select Module to Download",
                        options=loaded_modules,
                        key="kb_download_module_select"
                    )
                
                with col2:
                    # Download button
                    if download_module and download_module in st.session_state.kb_manager.module_collections:
                        try:
                            # Get the collection for this module
                            collection = st.session_state.kb_manager.module_collections[download_module]
                            
                            # Get all data from the collection
                            results = collection.get(include=['documents', 'metadatas'])
                            
                            if results and results['documents']:
                                # Convert to DataFrame
                                kb_records = []
                                for i, doc in enumerate(results['documents']):
                                    metadata = results['metadatas'][i] if i < len(results['metadatas']) else {}
                                    
                                    # Extract exception message from document if not in metadata
                                    exception_message = metadata.get('exception_message', '')
                                    if not exception_message:
                                        # Try to extract from document text
                                        # Document format: "Exception: [type] | Message: [message] | ..."
                                        if 'Message:' in doc:
                                            parts = doc.split('Message:')
                                            if len(parts) > 1:
                                                msg_part = parts[1].split('|')[0].strip()
                                                exception_message = msg_part
                                    
                                    kb_records.append({
                                        'Exception_Type': metadata.get('exception_type', ''),
                                        'Exception_Message': exception_message,
                                        'Resolution': metadata.get('resolution', ''),
                                        'Root_Cause': metadata.get('root_cause', ''),
                                        'Action': metadata.get('action', ''),
                                        'Document': doc
                                    })
                                
                                kb_df = pd.DataFrame(kb_records)
                                csv_data = kb_df.to_csv(index=False)
                                
                                st.download_button(
                                    "📥 Download KB (CSV)",
                                    csv_data,
                                    f"KB_{download_module}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    "text/csv",
                                    use_container_width=True
                                )
                            else:
                                st.warning("No data available for this module")
                        except Exception as e:
                            st.error(f"Error retrieving KB data: {str(e)}")
                    else:
                        st.info("Select a module to download")
        else:
            st.info("No knowledge bases loaded yet. Upload KB files to get started.")
    
    # Tab 3: Review Queue - THIS IS THE KEY TAB THAT WAS MISSING
    with tab3:
        st.header("📋 Review Queue")
        
        # [2025-12-05] Add explanation of column purposes
        st.info("""
        **📊 Column Guide:**
        - **AI Resolution & AI Suggested Action**: Generated by AI during processing - these are recommendations       
        **💡 Workflow:** Review AI suggestions →  Select items and add the User Resolution & User Suggested Action→ Click Purge or Reprocess
        """)
        
        # [2025-11-24] Initialize session state for checkbox selections
        # [2025-11-24] Changed save_to_kb default from False to True
        # Reason: User requested checkbox to be checked by default for better UX
        if 'selected_items' not in st.session_state:
            st.session_state.selected_items = set()
        if 'save_to_kb' not in st.session_state:
            st.session_state.save_to_kb = True  # Default to checked
        if 'kb_fields' not in st.session_state:
            st.session_state.kb_fields = {}
        
        if not st.session_state.review_queue.empty:
            # [2025-11-24] Debug: Log review queue contents
            logger.info(f"[REVIEW QUEUE] Total records in queue: {len(st.session_state.review_queue)}")
            logger.info(f"[REVIEW QUEUE] Queue columns: {list(st.session_state.review_queue.columns)}")
            #logger.info(f"[REVIEW QUEUE] Queue index: {list(st.session_state.review_queue.index)}")
            
            # Ensure Review_Status column exists
            if 'Review_Status' not in st.session_state.review_queue.columns:
                st.session_state.review_queue['Review_Status'] = 'Pending'
            
            pending_items = st.session_state.review_queue[
                st.session_state.review_queue['Review_Status'].fillna('Pending') == 'Pending'
            ]
            completed_items = st.session_state.review_queue[
                st.session_state.review_queue['Review_Status'].fillna('Pending') == 'Completed'
            ]
            
            logger.info(f"[REVIEW QUEUE] Pending: {len(pending_items)}, Completed: {len(completed_items)}")
            
            st.info(f"📊 Total: {len(st.session_state.review_queue)} | ⏳ Pending: {len(pending_items)} | ✅ Completed: {len(completed_items)}")
            
            # Initialize session state for filters
            if 'review_search_id' not in st.session_state:
                st.session_state.review_search_id = ''
            if 'review_resolution_filter' not in st.session_state:
                st.session_state.review_resolution_filter = 'All'
            if 'review_type_filter' not in st.session_state:
                st.session_state.review_type_filter = 'All'
            if 'review_module_filter' not in st.session_state:
                st.session_state.review_module_filter = 'All'
            if 'review_status_filter' not in st.session_state:
                st.session_state.review_status_filter = 'Pending'  # Default to Pending only
            
            # [2025-12-01] Show filter widgets FIRST to capture user input
            # Then apply filters based on updated session state
            st.subheader("Review Items")
            
            # [2025-12-01] Filter options - render BEFORE applying filters
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
            
            with col1:
                search_id = st.text_input(
                    "🔍 Search by Exception ID",
                    placeholder="Enter Exception ID (e.g., 2092898863)",
                    value=st.session_state.review_search_id,
                    key="review_search_exception_id",
                    on_change=lambda: setattr(st.session_state, 'review_search_id', st.session_state.review_search_exception_id)
                )
            
            with col2:
                resolution_options = ['All', 'REPROCESS', 'PURGE', 'INVESTIGATE', 'UNDEFINED']
                try:
                    resolution_idx = resolution_options.index(st.session_state.review_resolution_filter)
                except ValueError:
                    resolution_idx = 0
                filter_resolution = st.selectbox(
                    "Filter by Resolution",
                    options=resolution_options,
                    index=resolution_idx,
                    key="review_resolution_filter_select",
                    on_change=lambda: setattr(st.session_state, 'review_resolution_filter', st.session_state.review_resolution_filter_select)
                )
            
            with col3:
                if 'Exception_Type' in st.session_state.review_queue.columns:
                    unique_types = ['All'] + sorted(st.session_state.review_queue['Exception_Type'].unique().tolist())
                    try:
                        type_idx = unique_types.index(st.session_state.review_type_filter)
                    except ValueError:
                        type_idx = 0
                    filter_type = st.selectbox(
                        "Filter by Type",
                        options=unique_types,
                        index=type_idx,
                        key="review_type_filter_select",
                        on_change=lambda: setattr(st.session_state, 'review_type_filter', st.session_state.review_type_filter_select)
                    )
            
            with col4:
                unique_modules = ['All'] + sorted(st.session_state.review_queue['Module'].unique().tolist())
                try:
                    module_idx = unique_modules.index(st.session_state.review_module_filter)
                except ValueError:
                    module_idx = 0
                filter_module = st.selectbox(
                    "Filter by Module",
                    options=unique_modules,
                    index=module_idx,
                    key="review_module_filter_select",
                    on_change=lambda: setattr(st.session_state, 'review_module_filter', st.session_state.review_module_filter_select)
                )
            
            with col5:
                status_options = ['Pending', 'Completed', 'All']
                # Use the widget's value directly as the filter
                filter_status = st.selectbox(
                    "Filter by Status",
                    options=status_options,
                    index=status_options.index(st.session_state.review_status_filter) if st.session_state.review_status_filter in status_options else 0,
                    key="review_status_filter_select",
                    on_change=lambda: setattr(st.session_state, 'review_status_filter', st.session_state.review_status_filter_select)
                )
            
            # Apply filters NOW after widgets have updated session state
            filtered_queue = st.session_state.review_queue.copy()
            
            # Apply search by Exception ID
            if st.session_state.review_search_id:
                if 'Exception_ID' in filtered_queue.columns:
                    filtered_queue = filtered_queue[filtered_queue['Exception_ID'].str.contains(st.session_state.review_search_id, case=False, na=False)]
            
            # Apply resolution filter
            if st.session_state.review_resolution_filter != 'All':
                if 'Resolution' in filtered_queue.columns:
                    filtered_queue = filtered_queue[filtered_queue['Resolution'] == st.session_state.review_resolution_filter]
            
            # Apply type filter
            if st.session_state.review_type_filter != 'All':
                if 'Exception_Type' in filtered_queue.columns:
                    filtered_queue = filtered_queue[filtered_queue['Exception_Type'] == st.session_state.review_type_filter]
            
            # Apply module filter
            if st.session_state.review_module_filter != 'All':
                if 'Module' in filtered_queue.columns:
                    filtered_queue = filtered_queue[filtered_queue['Module'] == st.session_state.review_module_filter]
            
            # Apply status filter (Pending/Completed/All)
            if st.session_state.review_status_filter != 'All':
                # Ensure Review_Status column exists, fill missing values with 'Pending'
                if 'Review_Status' not in filtered_queue.columns:
                    filtered_queue['Review_Status'] = 'Pending'
                
                logger.info(f"[REVIEW QUEUE] Applying status filter: {st.session_state.review_status_filter}")
                logger.info(f"[REVIEW QUEUE] Review_Status values before filter: {filtered_queue['Review_Status'].value_counts().to_dict()}")
                
                filtered_queue = filtered_queue[
                    filtered_queue['Review_Status'].fillna('Pending') == st.session_state.review_status_filter
                ]
                
                logger.info(f"[REVIEW QUEUE] Records after status filter: {len(filtered_queue)}")
            
            # Show filtered count
            if len(filtered_queue) < len(st.session_state.review_queue):
                st.info(f"🔍 Filtered: {len(filtered_queue)} of {len(st.session_state.review_queue)} items")
            
            # [2025-12-01] Check if filtered queue is empty
            if filtered_queue.empty:
                st.warning("⚠️ No items match the selected filters. Please adjust your filter criteria.")
            else:
                    # Display columns configuration
                    # [2025-12-05] Removed Final_Resolution - it's redundant with Review_Status and Review_Action
                    display_cols = [
                        'Module',
                        'Exception_ID',
                        'Process_Name',  # [2025-12-01] Added Process Name column
                        'Exception_Type',
                        'Exception_Message',
                        'Root_Cause',
                        'Resolution',
                        'Suggested_Action',  # [2025-12-05] AI-generated suggested action from processing
                        'Confidence_Score',
                        # Extra columns for Review Queue (at the end)
                        'Review_Reason',
                        'User_Resolution',  # User's override resolution choice
                        'User_Suggested_Step',  # User's override suggested action
                        'Review_Status'  # Last column - shows Pending or Completed
                    ]
                    
                    # Only keep columns that exist in the dataframe
                    display_cols = [col for col in display_cols if col in filtered_queue.columns]
                    
                    # [2025-12-01] Pagination setup - 20 items per page
                    items_per_page = 20
                    total_items = len(filtered_queue)
                    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
                    
                    # Initialize page number in session state
                    if 'review_page' not in st.session_state:
                        st.session_state.review_page = 0
                    
                    # Ensure page is within bounds
                    if st.session_state.review_page >= total_pages:
                        st.session_state.review_page = max(0, total_pages - 1)
                    
                    # Pagination controls
                    st.write(f"**Page {st.session_state.review_page + 1} of {total_pages}** ({total_items} total items)")
                    
                    pcol1, pcol2, pcol3, pcol4 = st.columns(4)
                    with pcol1:
                        if st.button("⏮️ First", use_container_width=True, disabled=st.session_state.review_page == 0):
                            st.session_state.review_page = 0
                    with pcol2:
                        if st.button("◀️ Previous", use_container_width=True, disabled=st.session_state.review_page == 0):
                            st.session_state.review_page = max(0, st.session_state.review_page - 1)
                    with pcol3:
                        if st.button("Next ▶️", use_container_width=True, disabled=st.session_state.review_page >= total_pages - 1):
                            st.session_state.review_page = min(total_pages - 1, st.session_state.review_page + 1)
                    with pcol4:
                        if st.button("Last ⏭️", use_container_width=True, disabled=st.session_state.review_page >= total_pages - 1):
                            st.session_state.review_page = total_pages - 1
                    
                    # Calculate page slice
                    start_idx = st.session_state.review_page * items_per_page
                    end_idx = min(start_idx + items_per_page, total_items)
                    page_data = filtered_queue.iloc[start_idx:end_idx].copy()
                    
                    # [2025-12-01] Ensure User columns exist in review_queue (wrapped in loop to avoid None output)
                    for col in ['User_Resolution', 'User_Suggested_Step']:
                        if col not in st.session_state.review_queue.columns:
                            st.session_state.review_queue[col] = ''
                    
                    # [2025-12-01] Prepare display dataframe with Select and User columns
                    # Wrap in function to prevent None output
                    def create_editable_display():
                        df = page_data[display_cols].copy()
                        
                        # Add Select column
                        select_col = []
                        for idx in df.index:
                            is_completed = (st.session_state.review_queue.at[idx, 'Review_Status'] == 'Completed' 
                                           if 'Review_Status' in st.session_state.review_queue.columns else False)
                            if is_completed:
                                select_col.append(False)
                            else:
                                select_col.append(bool(idx in st.session_state.selected_items))
                        
                        # Add User columns
                        user_res_col = []
                        user_step_col = []
                        for idx in df.index:
                            # Get from kb_fields (pending edits) or review_queue (saved data)
                            if idx in st.session_state.kb_fields:
                                user_res = st.session_state.kb_fields[idx].get('Resolution', '')
                                user_step = st.session_state.kb_fields[idx].get('Suggested_Step', '')
                            else:
                                user_res = st.session_state.review_queue.at[idx, 'User_Resolution'] if 'User_Resolution' in st.session_state.review_queue.columns else ''
                                user_step = st.session_state.review_queue.at[idx, 'User_Suggested_Step'] if 'User_Suggested_Step' in st.session_state.review_queue.columns else ''
                            
                            # Clean None values
                            user_res = '' if (pd.isna(user_res) or user_res == 'None') else str(user_res)
                            user_step = '' if (pd.isna(user_step) or user_step == 'None') else str(user_step)
                            
                            user_res_col.append(user_res)
                            user_step_col.append(user_step)
                        
                        # Insert columns at specific positions
                        result = df.copy()
                        result.insert(0, 'Select', select_col)
                        result['User_Resolution'] = user_res_col
                        result['User_Suggested_Step'] = user_step_col
                        
                        return result
                    
                    display_df = create_editable_display()
                    
                    # Configure columns for data_editor
                    column_config = {
                        "Select": st.column_config.CheckboxColumn(
                            "Select",
                            help="Select items for bulk actions",
                            default=False,
                        ),
                        "Resolution": st.column_config.TextColumn(
                            "AI Resolution",
                            help="AI-generated resolution from processing",
                            width="small"
                        ),
                        "Suggested_Action": st.column_config.TextColumn(
                            "AI Suggested Action",
                            help="AI-generated suggested action from processing",
                            width="large"
                        ),
                        "User_Resolution": st.column_config.SelectboxColumn(
                            "User Resolution",
                            help="Your override resolution (optional - fill if you modify)",
                            width="medium",
                            options=['PURGE', 'REPROCESS', 'INVESTIGATE'],
                        ),
                        "User_Suggested_Step": st.column_config.TextColumn(
                            "User Suggested Action",
                            help="Your override suggested action (optional - fill if you modify)",
                            width="large"
                        ),
                        "Review_Reason": st.column_config.TextColumn(
                            "Review Reason",
                            help="Why this item was added to review queue",
                            width="medium"
                        ),
                        "Review_Status": st.column_config.TextColumn(
                            "Status",
                            help="Pending = Not reviewed yet | Completed = Purged or Reprocessed",
                            width="small"
                        ),
                    }
                    
                    # [2025-12-05] Build disabled columns list
                    # - Disable Select for completed records only
                    # - Allow editing only User_Resolution and User_Suggested_Step
                    # - All other columns (including AI Resolution and Suggested_Action) are read-only
                    disabled_cols = []
                    for col in display_df.columns:
                        if col == 'Select':
                            # Disable Select checkbox for completed records only
                            for idx in display_df.index:
                                is_completed = (st.session_state.review_queue.at[idx, 'Review_Status'] == 'Completed' 
                                               if 'Review_Status' in st.session_state.review_queue.columns else False)
                                if is_completed:
                                    disabled_cols.append(col)
                                    break
                        elif col not in ['User_Resolution', 'User_Suggested_Step']:
                            # All other columns except User input columns are disabled (read-only)
                            disabled_cols.append(col)
                    
                    # Display editable table with on_change callback to prevent auto-rerun
                    edited_df = st.data_editor(
                        display_df,
                        column_config=column_config,
                        disabled=disabled_cols,
                        hide_index=True,
                        use_container_width=True,
                        key=f"review_table_{st.session_state.review_page}"
                    )
                    
                    # [2025-12-01] CRITICAL FIX: Use on_change callback to prevent constant reruns
                    # Store edited data in a temporary session state key
                    if f'review_table_{st.session_state.review_page}' in st.session_state:
                        edited_data = st.session_state[f'review_table_{st.session_state.review_page}']
                        if edited_data is not None and 'edited_rows' in edited_data:
                            for row_idx, changes in edited_data['edited_rows'].items():
                                idx = page_data.index[row_idx]
                                
                                # Update selection if changed
                                if 'Select' in changes:
                                    if changes['Select']:
                                        st.session_state.selected_items.add(idx)
                                    else:
                                        st.session_state.selected_items.discard(idx)
                                
                                # [2025-12-05] CRITICAL FIX: Update user inputs WITHOUT saving to disk
                                # Reason: Saving to disk on every keystroke causes table reload and data loss
                                # Solution: Store edits in memory (kb_fields), save to disk only when Purge/Reprocess clicked
                                if 'User_Resolution' in changes or 'User_Suggested_Step' in changes:
                                    # Get existing values from kb_fields or review_queue
                                    existing_res = st.session_state.kb_fields.get(idx, {}).get('Resolution', '')
                                    existing_step = st.session_state.kb_fields.get(idx, {}).get('Suggested_Step', '')
                                    
                                    if not existing_res and idx in st.session_state.review_queue.index:
                                        existing_res = st.session_state.review_queue.at[idx, 'User_Resolution'] if 'User_Resolution' in st.session_state.review_queue.columns else ''
                                    if not existing_step and idx in st.session_state.review_queue.index:
                                        existing_step = st.session_state.review_queue.at[idx, 'User_Suggested_Step'] if 'User_Suggested_Step' in st.session_state.review_queue.columns else ''
                                    
                                    # Get new values from changes
                                    user_res = str(changes.get('User_Resolution', existing_res) or '').strip()
                                    user_step = str(changes.get('User_Suggested_Step', existing_step) or '').strip()
                                    
                                    # Store in memory only (no disk save yet)
                                    if user_res or user_step:
                                        st.session_state.kb_fields[idx] = {
                                            'Resolution': user_res,
                                            'Suggested_Step': user_step,
                                        }
                                        # Note: Data will be saved to disk when Purge/Reprocess button is clicked
                                    elif idx in st.session_state.kb_fields:
                                        del st.session_state.kb_fields[idx]
                    
                    # [2025-11-25] Select All and Clear All buttons BELOW the table
                    # Reason: User requested buttons to appear after the review results table
                    # [2025-12-01] Select All and Clear All buttons
                    col_select_all, col_clear_all, col_spacer = st.columns([1, 1, 4])
                    with col_select_all:
                        if st.button("✅ Select All on Page", use_container_width=True, key=f"select_all_{st.session_state.review_page}"):
                            st.session_state.selected_items.update(page_data.index.tolist())
                    
                    with col_clear_all:
                        if st.button("❌ Clear All Selections", use_container_width=True, key=f"clear_all_{st.session_state.review_page}"):
                            st.session_state.selected_items = set()
                    
                    # [2025-11-25] Moved "Save to Knowledge Base" checkbox BELOW the table
                    # Reason: User requested checkbox to appear after the review results table
                    # Get current value from session state
                    current_save_to_kb = st.session_state.get('save_to_kb', True)
                    
                    # Display checkbox and capture its value directly
                    save_to_kb = st.checkbox(
                        "💾 Save selected items to Knowledge Base",
                        value=current_save_to_kb,
                        key="save_to_kb_checkbox_display",
                        help="Check this to save selected items to KB when you click Purge or Reprocess. Make sure to fill User Resolution and User Suggested Step columns in the table above."
                    )
                
                    # Update session state only if changed
                    if save_to_kb != current_save_to_kb:
                        st.session_state.save_to_kb = save_to_kb
                
                    # [2025-11-24] Display success/info messages if they exist in session state
                    if 'review_success_msg' in st.session_state and st.session_state.review_success_msg:
                        st.success(st.session_state.review_success_msg)
                        st.session_state.review_success_msg = None  # Clear after displaying
                
                    if 'review_error_msg' in st.session_state and st.session_state.review_error_msg:
                        st.error(st.session_state.review_error_msg)
                        st.session_state.review_error_msg = None  # Clear after displaying
                
                    # Action section
                    st.subheader("Review Actions")
                
                    selected_count = len(st.session_state.selected_items)
                    if selected_count > 0:
                        st.info(f"✅ {selected_count} item(s) selected")
                    
                        # Mutually exclusive action buttons
                        col1, col2, col3 = st.columns([1, 1, 2])
                    
                        # [2025-11-24] Fixed deprecation warnings: use_container_width -> width
                        with col1:
                            purge_btn = st.button("🗑️ Purge Selected", type="primary", width="stretch")
                    
                        with col2:
                            reprocess_btn = st.button("♻️ Reprocess Selected", type="primary", width="stretch")
                    
                        with col3:
                            clear_selection = st.button("🔄 Clear Selection", width="stretch", key="clear_selection_btn")
                    
                        if clear_selection:
                            st.session_state.selected_items = set()
                    
                        # [2025-11-24] REMOVED duplicate "Save to Knowledge Base" section from here
                        # Reason: Moved above the table as per user request
                        # The checkbox now appears before the review results table
                    
                        # Process actions
                        if purge_btn:
                            # [2025-11-24] CRITICAL FIX: Only save to KB if checkbox is selected
                            saved_count = 0
                            if save_to_kb:
                                # [2025-11-24] Validate KB fields before saving
                                # Reason: Ensure user has provided both Resolution and Suggested_Step for all selected records
                                all_valid = True
                                for idx in st.session_state.selected_items:
                                    if idx not in st.session_state.kb_fields:
                                        all_valid = False
                                        st.session_state.review_error_msg = "❌ Please provide Resolution and Suggested Step for all selected records in the table"
                                        break
                                    fields = st.session_state.kb_fields[idx]
                                    if not fields['Resolution'] or not fields['Suggested_Step']:
                                        all_valid = False
                                        exception_id = st.session_state.review_queue.at[idx, 'Exception_ID']
                                        st.session_state.review_error_msg = f"❌ Please fill Resolution and Suggested Step for Exception ID: {exception_id}"
                                        break
                            
                                if not all_valid:
                                    pass  # Don't rerun, let Streamlit handle it naturally
                            
                                # [2025-11-24] Log KB count BEFORE saving
                                module_name = filtered_queue.loc[list(st.session_state.selected_items)[0]].get('Module', 'Unknown')
                                module_stats = st.session_state.kb_manager.get_module_stats(module_name)
                                kb_before = module_stats.get('total_entries', 0) if module_stats else 0
                                logger.info(f"[PURGE] KB count BEFORE save for module '{module_name}': {kb_before}")
                            
                                # [2025-11-24] Save to KB - Create NEW records with user inputs (PURGE action)
                                # Reason: User requested to save as new KB entries without replacing original data
                                # Each record gets user-provided Resolution and Suggested_Step
                                # Original Root_Cause is preserved from the exception record
                                for idx in st.session_state.selected_items:
                                    try:
                                        row_data = filtered_queue.loc[idx].copy()
                                        kb_data = st.session_state.kb_fields[idx]
                                    
                                        logger.info(f"[PURGE] Saving record {idx} to KB - Module: {row_data.get('Module', 'Unknown')}, Resolution: {kb_data['Resolution']}, Suggested_Step: {kb_data['Suggested_Step']}")
                                    
                                        # [2025-11-24] Get or create EVENT_INFORMATION with valid JSON structure
                                        event_info = row_data.get('EVENT_INFORMATION', '')
                                        if not event_info or pd.isna(event_info):
                                            # Create minimal valid EVENT_INFORMATION JSON structure
                                            event_info = json.dumps({
                                                "Exception": {
                                                    "Exception Type": row_data.get('Exception_Type', 'Unknown'),
                                                    "Message": row_data.get('Exception_Message', ''),
                                                    "StackTrace": row_data.get('Stack_Trace', '')
                                                }
                                            })
                                    
                                        # [2025-11-25] Prepare KB entry - User_Resolution overwrites Resolution column
                                        # User_Suggested_Step overwrites Suggested Step column (no new columns added)
                                        kb_entry = pd.DataFrame([{
                                            'Exception_ID': row_data.get('Exception_ID', ''),
                                            'Exception_Type': row_data.get('Exception_Type', ''),
                                            'Exception_Message': row_data.get('Exception_Message', ''),
                                            'Stack_Trace': row_data.get('Stack_Trace', ''),
                                            'Resolution': kb_data['Resolution'],  # User's resolution overwrites original
                                            'Root_Cause': row_data.get('Root_Cause', ''),  # Keep original root cause
                                            'Suggested Step': kb_data['Suggested_Step'],  # User's suggested step overwrites original
                                            'Confidence_Score': row_data.get('Confidence_Score', 0),
                                            'Module': row_data.get('Module', ''),
                                            'EVENT_INFORMATION': event_info,  # Valid JSON structure required by KB manager
                                            'Reviewed_By': 'User',  # Track that this was user-reviewed
                                            'Review_Date': datetime.now().isoformat()  # Track when it was reviewed
                                        }])
                                    
                                        # [2025-11-25] Log complete KB entry structure before saving
                                        logger.info(f"[PURGE] KB Entry for record {idx}:")
                                        logger.info(f"  Exception_ID: {kb_entry['Exception_ID'].iloc[0]}")
                                        logger.info(f"  Module: {kb_entry['Module'].iloc[0]}")
                                        logger.info(f"  Exception_Type: {kb_entry['Exception_Type'].iloc[0]}")
                                        logger.info(f"  Resolution (USER INPUT): {kb_entry['Resolution'].iloc[0]}")
                                        logger.info(f"  Suggested Step (USER INPUT): {kb_entry['Suggested Step'].iloc[0]}")
                                        logger.info(f"  Root_Cause: {kb_entry['Root_Cause'].iloc[0][:100]}...")
                                        logger.info(f"  Confidence_Score: {kb_entry['Confidence_Score'].iloc[0]}")
                                        logger.info(f"  Reviewed_By: {kb_entry['Reviewed_By'].iloc[0]}")
                                        logger.info(f"  Review_Date: {kb_entry['Review_Date'].iloc[0]}")
                                        logger.info(f"  All KB Entry Columns: {list(kb_entry.columns)}")
                                    
                                        # [2025-11-24] Fixed: Use correct method name load_or_append_knowledge_base
                                        # Reason: append_to_kb method doesn't exist, causing KB save to fail
                                        module_name = row_data.get('Module', 'Unknown')
                                        result = st.session_state.kb_manager.load_or_append_knowledge_base(
                                            kb_entry, module_name, append_mode=True
                                        )
                                        if result.get('status') == 'success':
                                            saved_count += 1
                                            logger.info(f"[PURGE] ✅ Successfully saved record {idx} to KB")
                                        else:
                                            logger.error(f"[PURGE] ❌ Failed to save record {idx}: {result.get('message', 'Unknown error')}")
                                    
                                    except Exception as e:
                                        logger.error(f"[PURGE] ❌ KB save error for record {idx}: {str(e)}", exc_info=True)
                            
                                # [2025-11-24] Log KB count AFTER saving
                                module_stats = st.session_state.kb_manager.get_module_stats(module_name)
                                kb_after = module_stats.get('total_entries', 0) if module_stats else 0
                                logger.info(f"[PURGE] KB count AFTER save for module '{module_name}': {kb_after} (Added: {kb_after - kb_before})")
                            
                                # Store success message in session state to display after rerun
                                st.session_state.review_success_msg = f"✅ Saved {saved_count} NEW records to Knowledge Base | 🗑️ Marked {selected_count} item(s) as PURGED"
                            else:
                                # No KB save, just mark as purged
                                st.session_state.review_success_msg = f"🗑️ Marked {selected_count} item(s) as PURGED (not saved to KB)"
                        
                            # [2025-12-05] Mark items as Completed and save user edits to disk
                            # Reason: Provides audit trail and persists user input data
                            # Note: Final_Resolution removed - Review_Action already indicates PURGE vs REPROCESS
                            for idx in st.session_state.selected_items:
                                if idx in st.session_state.review_queue.index:
                                    st.session_state.review_queue.at[idx, 'Review_Status'] = 'Completed'
                                    st.session_state.review_queue.at[idx, 'Review_Action'] = 'Purged by user'
                                    st.session_state.review_queue.at[idx, 'Review_Timestamp'] = datetime.now().isoformat()
                                    # Save user input fields to review_queue
                                    if idx in st.session_state.kb_fields:
                                        st.session_state.review_queue.at[idx, 'User_Resolution'] = st.session_state.kb_fields[idx].get('Resolution', '')
                                        st.session_state.review_queue.at[idx, 'User_Suggested_Step'] = st.session_state.kb_fields[idx].get('Suggested_Step', '')
                        
                            # [2025-12-01] PERSISTENCE: Save to disk after marking items as completed (PURGE)
                            # This ensures completion status persists across sessions
                            save_review_queue_to_disk(st.session_state.review_queue)
                        
                            st.session_state.selected_items = set()
                            st.session_state.kb_fields = {}
                    
                        if reprocess_btn:
                            # [2025-11-24] CRITICAL FIX: Only save to KB if checkbox is selected
                            saved_count = 0
                            if save_to_kb:
                                # [2025-11-24] Validate KB fields before saving with debug logging
                                logger.info(f"[REPROCESS] Starting validation for {len(st.session_state.selected_items)} selected items")
                                logger.info(f"[REPROCESS] KB fields keys: {list(st.session_state.kb_fields.keys())}")
                            
                                all_valid = True
                                for idx in st.session_state.selected_items:
                                    if idx not in st.session_state.kb_fields:
                                        all_valid = False
                                        logger.error(f"[REPROCESS] Record {idx} NOT in kb_fields!")
                                        st.session_state.review_error_msg = "❌ Please provide Resolution and Suggested Step for all selected records in the table"
                                        break
                                
                                    fields = st.session_state.kb_fields[idx]
                                    logger.info(f"[REPROCESS] Record {idx}: Resolution='{fields.get('Resolution', '')}', Suggested_Step='{fields.get('Suggested_Step', '')}'")
                                
                                    if not fields.get('Resolution') or not fields.get('Suggested_Step'):
                                        all_valid = False
                                        exception_id = st.session_state.review_queue.at[idx, 'Exception_ID']
                                        logger.error(f"[REPROCESS] Record {exception_id} has empty fields!")
                                        st.session_state.review_error_msg = f"❌ Please fill Resolution and Suggested Step for Exception ID: {exception_id}"
                                        break
                            
                                if not all_valid:
                                    logger.error("[REPROCESS] Validation FAILED - stopping")
                                    pass  # Don't rerun, let Streamlit handle it naturally
                            
                                logger.info("[REPROCESS] Validation PASSED - proceeding to save")
                            
                                # [2025-11-24] Log KB count BEFORE saving
                                module_name = filtered_queue.loc[list(st.session_state.selected_items)[0]].get('Module', 'Unknown')
                                module_stats = st.session_state.kb_manager.get_module_stats(module_name)
                                kb_before = module_stats.get('total_entries', 0) if module_stats else 0
                                logger.info(f"[REPROCESS] KB count BEFORE save for module '{module_name}': {kb_before}")
                            
                                # [2025-11-24] Save to KB - Create NEW records with user inputs (REPROCESS action)
                                # Reason: User requested to save as new KB entries without replacing original data
                                # Each record gets user-provided Resolution and Suggested_Step
                                # Original Root_Cause is preserved from the exception record
                                for idx in st.session_state.selected_items:
                                    try:
                                        row_data = filtered_queue.loc[idx].copy()
                                        kb_data = st.session_state.kb_fields[idx]
                                    
                                        logger.info(f"[REPROCESS] Saving record {idx} to KB - Module: {row_data.get('Module', 'Unknown')}, Resolution: {kb_data['Resolution']}, Suggested_Step: {kb_data['Suggested_Step']}")
                                    
                                        # [2025-11-24] Get or create EVENT_INFORMATION with valid JSON structure
                                        event_info = row_data.get('EVENT_INFORMATION', '')
                                        if not event_info or pd.isna(event_info):
                                            # Create minimal valid EVENT_INFORMATION JSON structure
                                            event_info = json.dumps({
                                                "Exception": {
                                                    "Exception Type": row_data.get('Exception_Type', 'Unknown'),
                                                    "Message": row_data.get('Exception_Message', ''),
                                                    "StackTrace": row_data.get('Stack_Trace', '')
                                                }
                                            })
                                    
                                        # [2025-11-25] Prepare KB entry - User_Resolution overwrites Resolution column
                                        # User_Suggested_Step overwrites Suggested Step column (no new columns added)
                                        kb_entry = pd.DataFrame([{
                                            'Exception_ID': row_data.get('Exception_ID', ''),
                                            'Exception_Type': row_data.get('Exception_Type', ''),
                                            'Exception_Message': row_data.get('Exception_Message', ''),
                                            'Stack_Trace': row_data.get('Stack_Trace', ''),
                                            'Resolution': kb_data['Resolution'],  # User's resolution overwrites original
                                            'Root_Cause': row_data.get('Root_Cause', ''),  # Keep original root cause
                                            'Suggested Step': kb_data['Suggested_Step'],  # User's suggested step overwrites original
                                            'Confidence_Score': row_data.get('Confidence_Score', 0),
                                            'Module': row_data.get('Module', ''),
                                            'EVENT_INFORMATION': event_info,  # Valid JSON structure required by KB manager
                                            'Reviewed_By': 'User',  # Track that this was user-reviewed
                                            'Review_Date': datetime.now().isoformat()  # Track when it was reviewed
                                        }])
                                    
                                        # [2025-11-25] Log complete KB entry structure before saving
                                        logger.info(f"[REPROCESS] KB Entry for record {idx}:")
                                        logger.info(f"  Exception_ID: {kb_entry['Exception_ID'].iloc[0]}")
                                        logger.info(f"  Module: {kb_entry['Module'].iloc[0]}")
                                        logger.info(f"  Exception_Type: {kb_entry['Exception_Type'].iloc[0]}")
                                        logger.info(f"  Resolution (USER INPUT): {kb_entry['Resolution'].iloc[0]}")
                                        logger.info(f"  Suggested Step (USER INPUT): {kb_entry['Suggested Step'].iloc[0]}")
                                        logger.info(f"  Root_Cause: {kb_entry['Root_Cause'].iloc[0][:100]}...")
                                        logger.info(f"  Confidence_Score: {kb_entry['Confidence_Score'].iloc[0]}")
                                        logger.info(f"  Reviewed_By: {kb_entry['Reviewed_By'].iloc[0]}")
                                        logger.info(f"  Review_Date: {kb_entry['Review_Date'].iloc[0]}")
                                        logger.info(f"  All KB Entry Columns: {list(kb_entry.columns)}")
                                    
                                        # [2025-11-24] Fixed: Use correct method name load_or_append_knowledge_base
                                        # Reason: append_to_kb method doesn't exist, causing KB save to fail
                                        module_name = row_data.get('Module', 'Unknown')
                                        result = st.session_state.kb_manager.load_or_append_knowledge_base(
                                            kb_entry, module_name, append_mode=True
                                        )
                                        if result.get('status') == 'success':
                                            saved_count += 1
                                            logger.info(f"[REPROCESS] ✅ Successfully saved record {idx} to KB")
                                        else:
                                            logger.error(f"[REPROCESS] ❌ Failed to save record {idx}: {result.get('message', 'Unknown error')}")
                                    
                                    except Exception as e:
                                        logger.error(f"[REPROCESS] ❌ KB save error for record {idx}: {str(e)}", exc_info=True)
                            
                                # [2025-11-24] Log KB count AFTER saving
                                module_stats = st.session_state.kb_manager.get_module_stats(module_name)
                                kb_after = module_stats.get('total_entries', 0) if module_stats else 0
                                logger.info(f"[REPROCESS] KB count AFTER save for module '{module_name}': {kb_after} (Added: {kb_after - kb_before})")
                            
                                # Store success message in session state to display after rerun
                                st.session_state.review_success_msg = f"✅ Saved {saved_count} NEW records to Knowledge Base | ♻️ Marked {selected_count} item(s) for REPROCESS"
                            else:
                                # No KB save, just mark for reprocess
                                st.session_state.review_success_msg = f"♻️ Marked {selected_count} item(s) for REPROCESS (not saved to KB)"
                        
                            # [2025-12-05] Mark items as Completed and save user edits to disk
                            # Reason: Provides audit trail and persists user input data
                            # Note: Final_Resolution removed - Review_Action already indicates PURGE vs REPROCESS
                            for idx in st.session_state.selected_items:
                                if idx in st.session_state.review_queue.index:
                                    st.session_state.review_queue.at[idx, 'Review_Status'] = 'Completed'
                                    st.session_state.review_queue.at[idx, 'Review_Action'] = 'Marked for reprocessing'
                                    st.session_state.review_queue.at[idx, 'Review_Timestamp'] = datetime.now().isoformat()
                                    # Save user input fields to review_queue
                                    if idx in st.session_state.kb_fields:
                                        st.session_state.review_queue.at[idx, 'User_Resolution'] = st.session_state.kb_fields[idx].get('Resolution', '')
                                        st.session_state.review_queue.at[idx, 'User_Suggested_Step'] = st.session_state.kb_fields[idx].get('Suggested_Step', '')
                        
                            # [2025-12-01] PERSISTENCE: Save to disk after marking items as completed (REPROCESS)
                            # This ensures completion status persists across sessions
                            save_review_queue_to_disk(st.session_state.review_queue)
                        
                            st.session_state.selected_items = set()
                            st.session_state.kb_fields = {}
                
                        else:
                            st.warning("⚠️ Please select at least one item using the checkboxes above")
                
                    # [2025-11-25] Clear Completed Items - Two-step workflow
                    # Show completed items count and allow clearing them
                    st.markdown("---")
                    st.subheader("🗑️ Clear Completed Items")
                
                    # Ensure Review_Status column exists
                    if 'Review_Status' not in st.session_state.review_queue.columns:
                        st.session_state.review_queue['Review_Status'] = 'Pending'
                
                    completed_count = len(st.session_state.review_queue[
                        st.session_state.review_queue['Review_Status'].fillna('Pending') == 'Completed'
                    ])
                
                    if completed_count > 0:
                        st.info(f"📋 You have **{completed_count}** completed item(s) in the queue. These items have been reviewed and marked as Purged or Reprocessed.")
                    
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            clear_completed = st.button("🗑️ Clear Completed Items", type="secondary", use_container_width=True)
                    
                        if clear_completed:
                            pending_only = st.session_state.review_queue[
                                st.session_state.review_queue['Review_Status'].fillna('Pending') != 'Completed'
                            ]
                            cleared_count = len(st.session_state.review_queue) - len(pending_only)
                            st.session_state.review_queue = pending_only
                            
                            # [2025-12-01] PERSISTENCE: Save to disk after clearing completed items
                            # This ensures cleared items don't reappear on next login
                            save_review_queue_to_disk(st.session_state.review_queue)
                            
                            st.success(f"✅ Cleared {cleared_count} completed items from review queue")
                    else:
                        st.success("✅ No completed items to clear. All items in the queue are pending review.")
                
                    # Export options
                    st.subheader("Export Review Queue")
                
                    col1, col2 = st.columns(2)
                
                    with col1:
                        csv = st.session_state.review_queue.to_csv(index=False)
                        st.download_button(
                            "📥 Download Review Queue (CSV)",
                            csv,
                            f"review_queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            "text/csv",
                            width="stretch"
                        )
                
                    with col2:
                        # Create detailed report
                        report = {
                            'timestamp': datetime.now().isoformat(),
                            'total_items': len(st.session_state.review_queue),
                            'pending': len(pending_items),
                            'completed': len(completed_items),
                            'modules': st.session_state.review_queue['Module'].value_counts().to_dict() if 'Module' in st.session_state.review_queue.columns else {},
                            'resolutions': st.session_state.review_queue['Resolution'].value_counts().to_dict() if 'Resolution' in st.session_state.review_queue.columns else {}
                        }
                        report_json = json.dumps(report, indent=2)
                        st.download_button(
                            "📄 Download Review Report (JSON)",
                            report_json,
                            f"review_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            "application/json",
                            width="stretch"
                        )
    
    # Tab 4: Analytics - Clean and Efficient Dashboard
    with tab4:
        st.header("📊 Analytics Dashboard")
        
        # [2025-12-01] AUDIT LOG SECTION - Processing Activity History
        # Moved from Review Queue tab for better organization
        st.subheader("📊 Processing Activity Audit Log")
        st.info("📝 Track all file uploads and processing activities. Use this for analytics, compliance, and usage monitoring.")
        
        # Load audit log from disk
        audit_df = load_audit_log_from_disk()
        
        if not audit_df.empty:
            # Add filters for audit log
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                # Date range filter
                if 'Upload_DateTime' in audit_df.columns:
                    st.write("**Filter by Date Range:**")
                    date_options = ["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"]
                    date_filter = st.selectbox("Select Period", date_options, key="audit_date_filter")
                    
                    # Apply date filter
                    if date_filter != "All Time":
                        days_map = {"Last 7 Days": 7, "Last 30 Days": 30, "Last 90 Days": 90}
                        days = days_map[date_filter]
                        cutoff_date = datetime.now() - pd.Timedelta(days=days)
                        audit_df = audit_df[audit_df['Upload_DateTime'] >= cutoff_date]
            
            with col2:
                # Module filter
                if 'Module' in audit_df.columns:
                    modules = ['All'] + sorted(audit_df['Module'].unique().tolist())
                    module_filter = st.selectbox("Filter by Module", modules, key="audit_module_filter")
                    if module_filter != 'All':
                        audit_df = audit_df[audit_df['Module'] == module_filter]
            
            with col3:
                # Sort options
                sort_by = st.selectbox("Sort by", ["Newest First", "Oldest First", "Most Records"], key="audit_sort")
                if sort_by == "Newest First":
                    audit_df = audit_df.sort_values('Upload_DateTime', ascending=False)
                elif sort_by == "Oldest First":
                    audit_df = audit_df.sort_values('Upload_DateTime', ascending=True)
                else:  # Most Records
                    audit_df = audit_df.sort_values('Total_Records', ascending=False)
            
            # Display summary metrics
            st.markdown("### 📈 Summary Statistics")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Total Uploads", len(audit_df))
            with col2:
                total_records = audit_df['Total_Records'].sum() if 'Total_Records' in audit_df.columns else 0
                st.metric("Total Records", f"{total_records:,}")
            with col3:
                avg_conf = audit_df['Avg_Confidence'].mean() if 'Avg_Confidence' in audit_df.columns else 0
                st.metric("Avg Confidence", f"{avg_conf:.1f}%")
            with col4:
                total_review = audit_df['Review_Count'].sum() if 'Review_Count' in audit_df.columns else 0
                st.metric("Total Reviewed", total_review)
            with col5:
                total_reprocess = audit_df['Reprocess_Count'].sum() if 'Reprocess_Count' in audit_df.columns else 0
                st.metric("Total Reprocess", total_reprocess)
            
            # Display audit log table
            st.markdown("### 📋 Activity Log")
            
            # Format the display
            display_audit = audit_df.copy()
            if 'Upload_DateTime' in display_audit.columns:
                display_audit['Upload_DateTime'] = display_audit['Upload_DateTime'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Format processing time as MM:SS
            if 'Processing_Time_Minutes' in display_audit.columns:
                display_audit['Processing_Time_Formatted'] = display_audit['Processing_Time_Minutes'].apply(
                    lambda x: f"{int(x)}:{int((x % 1) * 60):02d}" if pd.notna(x) else "0:00"
                )
            
            # Rename columns for better display
            column_rename = {
                'Upload_DateTime': 'Date & Time',
                'File_Name': 'File Name',
                'Module': 'Module',
                'Processing_Time_Formatted': 'Time (MM:SS)',
                'Total_Records': 'Total Records',
                'Reprocess_Count': 'Reprocess',
                'Purge_Count': 'Purge',
                'Investigate_Count': 'Investigate',
                'Review_Count': 'Review Queue',
                'Avg_Confidence': 'Avg Confidence %',
            }
            display_audit = display_audit.rename(columns=column_rename)
            
            # Drop the original Processing_Time_Minutes column if it exists
            if 'Processing_Time_Minutes' in display_audit.columns:
                display_audit = display_audit.drop(columns=['Processing_Time_Minutes'])
            
            # Display with formatting
            st.dataframe(
                display_audit,
                use_container_width=True,
                height=400,
                column_config={
                    "Date & Time": st.column_config.TextColumn("Date & Time", width="medium"),
                    "File Name": st.column_config.TextColumn("File Name", width="large"),
                    "Module": st.column_config.TextColumn("Module", width="small"),
                    "Total Records": st.column_config.NumberColumn("Total Records", format="%d"),
                    "Reprocess": st.column_config.NumberColumn("Reprocess", format="%d"),
                    "Purge": st.column_config.NumberColumn("Purge", format="%d"),
                    "Investigate": st.column_config.NumberColumn("Investigate", format="%d"),
                    "Review Queue": st.column_config.NumberColumn("Review Queue", format="%d"),
                    "Avg Confidence %": st.column_config.NumberColumn("Avg Confidence %", format="%.1f%%"),
                    "Time (MM:SS)": st.column_config.TextColumn("Time (MM:SS)", width="small")
                }
            )
            
            # [2025-12-01] TREND CHARTS - Clean and Efficient
            st.markdown("---")
            st.markdown("### 📈 Trend Analysis")
            
            # Chart 1: Module vs Resolution Counts (Grouped Bars)
            st.markdown("#### Module vs Resolution Counts (Purge, Reprocess, Investigate)")
            if 'Module' in audit_df.columns:
                # Aggregate all resolution counts by module
                module_data = audit_df.groupby('Module').agg({
                    'Purge_Count': 'sum',
                    'Reprocess_Count': 'sum',
                    'Investigate_Count': 'sum'
                }).reset_index()
                
                # Create grouped bar chart
                fig1 = go.Figure()
                
                fig1.add_trace(go.Bar(
                    name='Purge',
                    x=module_data['Module'],
                    y=module_data['Purge_Count'],
                    marker_color='#e74c3c',
                    text=module_data['Purge_Count'],
                    textposition='auto'
                ))
                
                fig1.add_trace(go.Bar(
                    name='Reprocess',
                    x=module_data['Module'],
                    y=module_data['Reprocess_Count'],
                    marker_color='#3498db',
                    text=module_data['Reprocess_Count'],
                    textposition='auto'
                ))
                
                fig1.add_trace(go.Bar(
                    name='Investigate',
                    x=module_data['Module'],
                    y=module_data['Investigate_Count'],
                    marker_color='#f39c12',
                    text=module_data['Investigate_Count'],
                    textposition='auto'
                ))
                
                fig1.update_layout(
                    barmode='group',
                    xaxis_title="Module",
                    yaxis_title="Count",
                    height=400,
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            # Chart 2: Exception Type vs Count Trend (Last 7 Days from Audit Log)
            st.markdown("#### Exception Type vs Count Trend (Last 7 Days)")
            
            # Filter audit data for last 7 days
            if 'Upload_DateTime' in audit_df.columns:
                last_7_days = datetime.now() - pd.Timedelta(days=7)
                recent_audit = audit_df[audit_df['Upload_DateTime'] >= last_7_days]
                
                if not recent_audit.empty:
                    # Get exception type data from processed_results if available
                    if not st.session_state.processed_results.empty and 'Exception_Type' in st.session_state.processed_results.columns:
                        exception_type_counts = st.session_state.processed_results['Exception_Type'].value_counts().head(10)
                        
                        # Extract last word from exception types for cleaner display
                        # e.g., "System.NullReferenceException" -> "NullReferenceException"
                        short_labels = []
                        for exc_type in exception_type_counts.index:
                            if pd.notna(exc_type) and exc_type:
                                # Split by dot and take last part, or split by space and take last word
                                if '.' in str(exc_type):
                                    short_label = str(exc_type).split('.')[-1]
                                else:
                                    short_label = str(exc_type).split()[-1]
                                short_labels.append(short_label)
                            else:
                                short_labels.append('Unknown')
                        
                        fig2 = go.Figure(data=[
                            go.Bar(
                                x=short_labels,
                                y=exception_type_counts.values,
                                marker_color='#2ecc71',
                                text=exception_type_counts.values,
                                textposition='auto',
                                hovertext=exception_type_counts.index,  # Show full name on hover
                                hovertemplate='%{hovertext}<br>Count: %{y}<extra></extra>'
                            )
                        ])
                        fig2.update_layout(
                            xaxis_title="Exception Type",
                            yaxis_title="Count",
                            height=400,
                            showlegend=False,
                            xaxis={'tickangle': 0}  # Horizontal text (0 degrees)
                        )
                        st.plotly_chart(fig2, use_container_width=True)
                    else:
                        st.info("📊 Process exception files to see exception type distribution")
                else:
                    st.info("📊 No data available for the last 7 days. Process more files to see trends.")
            else:
                st.info("📊 Process exception files to see exception type distribution")
            
            
            # Export audit log
            st.markdown("---")
            st.markdown("### 📥 Export Audit Log")
            col1, col2 = st.columns(2)
            with col1:
                csv_audit = display_audit.to_csv(index=False)
                st.download_button(
                    "📥 Download Audit Log (CSV)",
                    csv_audit,
                    f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv",
                    use_container_width=True
                )
        else:
            st.info("📭 No processing activities recorded yet. Upload and process files to see audit history and analytics.")
    
    
    # Tab 5: Monitor
    with tab5:
        st.header("🖥️ Live System Monitor")
        st.markdown("Real-time monitoring of parallel processing, workers, and task queue")
        
        # Initialize task manager
        task_manager = get_task_manager()
        
        # Auto-refresh toggle
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            auto_refresh = st.checkbox("Auto-refresh", value=True)
        with col2:
            if st.button("🔄 Refresh Now", use_container_width=True):
                st.rerun()
        
        # Get system stats
        stats = task_manager.get_system_stats()
        
        # ============================================================================
        # SECTION 1: SYSTEM OVERVIEW - Top KPI Cards
        # ============================================================================
        st.subheader("📊 System Overview")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric(
                "Active Workers",
                f"{stats['active_workers']}/{stats['total_workers']}",
                delta="Healthy" if stats['active_workers'] == stats['total_workers'] else "⚠️ Warning"
            )
        
        with col2:
            st.metric(
                "Queue Size",
                stats['queue_size'],
                delta="Empty" if stats['queue_size'] == 0 else f"{stats['queue_size']} waiting"
            )
        
        with col3:
            st.metric(
                "Processing",
                stats['processing'],
                delta="Active" if stats['processing'] > 0 else "Idle"
            )
        
        with col4:
            st.metric(
                "Pending Tasks",
                stats['pending'],
                delta=None
            )
        
        with col5:
            st.metric(
                "Total Processed",
                stats['total_records_processed'],
                delta=f"{stats['completed']} tasks completed"
            )
        
        st.markdown("---")
        
        # ============================================================================
        # SECTION 2: WORKER STATUS - Visual Worker Grid
        # ============================================================================
        st.subheader("👷 Worker Status")
        
        workers = task_manager.get_worker_status()
        
        worker_cols = st.columns(len(workers))
        
        for idx, worker in enumerate(workers):
            with worker_cols[idx]:
                status_color = "🟢" if worker['alive'] else "🔴"
                status_text = "Active" if worker['alive'] else "Inactive"
                
                st.markdown(f"""
                <div style="
                    padding: 15px;
                    border-radius: 10px;
                    background: linear-gradient(135deg, {'#2ecc71' if worker['alive'] else '#e74c3c'}, {'#27ae60' if worker['alive'] else '#c0392b'});
                    color: white;
                    text-align: center;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    <div style="font-size: 24px;">{status_color}</div>
                    <div style="font-size: 16px; font-weight: bold;">{worker['name']}</div>
                    <div style="font-size: 12px; margin-top: 5px;">{status_text}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ============================================================================
        # SECTION 3: ACTIVE PROCESSING - Real-time Batch Progress
        # ============================================================================
        st.subheader("⚡ Active Processing (Live)")
        
        active_tasks = task_manager.get_active_tasks()
        
        if active_tasks:
            for task in active_tasks:
                # Task header with module badge
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.markdown(f"**🔄 Module:** `{task['module_name']}`")
                with col2:
                    elapsed = int(task['elapsed_seconds'])
                    st.markdown(f"**⏱️ Elapsed:** {elapsed // 60}m {elapsed % 60}s")
                with col3:
                    st.markdown(f"**📊 Progress:** {task['progress']:.1f}%")
                
                # Progress bar
                progress_value = task['progress'] / 100
                st.progress(
                    progress_value,
                    text=f"Processing: {task['processed_records']}/{task['total_records']} exceptions"
                )
                
                # Batch details
                current_batch = (task['processed_records'] // 2) + 1  # Assuming batch size of 2
                total_batches = (task['total_records'] + 1) // 2
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Current Batch", f"{current_batch}/{total_batches}")
                with col2:
                    records_remaining = task['total_records'] - task['processed_records']
                    st.metric("Remaining", records_remaining)
                with col3:
                    est_time_remaining = (records_remaining / 2) * 3  # Assuming 3 sec per batch
                    st.metric("Est. Time Left", f"{int(est_time_remaining)}s")
                
                st.markdown("---")
        else:
            st.info("🟢 No active processing tasks. System is idle.")
        
        # ============================================================================
        # SECTION 4: PENDING QUEUE - Tasks Waiting to Process
        # ============================================================================
        st.subheader("⏳ Pending Queue")
        
        pending_tasks = task_manager.get_pending_tasks()
        
        if pending_tasks:
            for idx, task in enumerate(pending_tasks, 1):
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    st.markdown(f"**#{idx}**")
                with col2:
                    st.markdown(f"**Module:** `{task['module_name']}` | **Records:** {task['total_records']}")
                with col3:
                    st.markdown(f"**Task ID:** `{task['task_id'][:8]}...`")
        else:
            st.success("✅ Queue is empty - all tasks are being processed or completed!")
        
        st.markdown("---")
        
        # ============================================================================
        # SECTION 5: COMPLETED TASKS - Recent History
        # ============================================================================
        st.subheader("✅ Completed Tasks (Recent)")
        
        completed_tasks = task_manager.get_completed_tasks()
        
        if completed_tasks:
            # Sort by completion time (most recent first)
            completed_tasks = sorted(
                completed_tasks, 
                key=lambda x: x['completed_at'] if x['completed_at'] else '', 
                reverse=True
            )[:10]  # Show last 10
            
            completed_df = pd.DataFrame([
                {
                    'Module': task['module_name'],
                    'Status': '✅ Success' if task['status'] == 'completed' else '❌ Failed',
                    'Records': task['total_records'],
                    'Processing Time': f"{int(task['processing_time'])}s",
                    'Completed At': task['completed_at'][:19] if task['completed_at'] else 'N/A',
                    'Task ID': task['task_id'][:12]
                }
                for task in completed_tasks
            ])
            
            st.dataframe(
                completed_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'Module': st.column_config.TextColumn('Module', width='medium'),
                    'Status': st.column_config.TextColumn('Status', width='small'),
                    'Records': st.column_config.NumberColumn('Records', width='small'),
                    'Processing Time': st.column_config.TextColumn('Time', width='small'),
                    'Completed At': st.column_config.TextColumn('Completed', width='medium'),
                    'Task ID': st.column_config.TextColumn('Task ID', width='small')
                }
            )
        else:
            st.info("📭 No completed tasks yet.")
        
        st.markdown("---")
        
        # ============================================================================
        # SECTION 6: ERROR LOG - Failed Tasks and Exceptions
        # ============================================================================
        st.subheader("⚠️ Error Log")
        
        failed_tasks = [t for t in completed_tasks if t.get('status') == 'failed']
        
        if failed_tasks:
            st.error(f"🚨 {len(failed_tasks)} failed task(s) detected!")
            
            for task in failed_tasks:
                with st.expander(f"❌ {task['module_name']} - Task {task['task_id'][:12]} (Failed at {task['completed_at'][:19]})"):
                    st.code(task.get('error', 'No error details available'), language='text')
        else:
            st.success("✅ No errors! All tasks completed successfully.")
        
        st.markdown("---")
        
        # ============================================================================
        # SECTION 7: SYSTEM ACTIONS - Control Panel
        # ============================================================================
        st.subheader("🎛️ System Controls")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Clear Completed Tasks", use_container_width=True):
                # Add method to clear completed tasks from memory
                st.info("Feature coming soon: Clear completed task history")
        
        with col2:
            if st.button("📊 Export Task Log", use_container_width=True):
                # Export all task data as CSV
                all_tasks = task_manager.get_all_tasks()
                if all_tasks:
                    tasks_df = pd.DataFrame(all_tasks)
                    csv = tasks_df.to_csv(index=False)
                    st.download_button(
                        "Download Task Log CSV",
                        csv,
                        f"task_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv"
                    )
        
        with col3:
            if st.button("⚠️ Emergency Stop", use_container_width=True, type="secondary"):
                st.warning("⚠️ This will stop all processing! Are you sure?")
                # Add confirmation logic here
        
        # Auto-refresh logic
        if auto_refresh:
            time.sleep(2)
            st.rerun()

    
    # Tab 6: Help
    with tab6:
        st.header("Help & Documentation")
        
        st.markdown("""
        ## 🚀 Quick Start Guide
        
        ### Step 1: Build Knowledge Base (Recommended)
        1. Go to the **Knowledge Base** tab
        2. Enter your module name (e.g., "ClaimGeneration")
        3. Upload a CSV with exception patterns and resolutions
        4. Click "Add to Knowledge Base"
        
        ### Step 2: Process Exceptions
        1. Go to **Process Exceptions** tab
        2. Select your LLM model (Llama 3.2b recommended)
        3. Upload your exception CSV/Excel file
        4. Enable "Add low-confidence to review queue"
        5. Click "Process Exceptions"
        
        ### Step 3: Review Low-Confidence Items
        1. Go to **Review Queue** tab
        2. Review the items in the table
        3. Select items for PURGE or REPROCESS
        4. Click "Submit Review"
        
        ## ⚠️ Common Issues & Solutions
        
        ### "No KB loaded for module" Warning
        - **This is normal** if you haven't uploaded a knowledge base yet
        - The system will still work but with lower confidence
        - To fix: Upload a KB file in the Knowledge Base tab
        
        ### Review Queue Not Showing Items
        - Make sure "Add low-confidence to review queue" is checked
        - Lower the confidence threshold (try 80% instead of 70%)
        - Check that your processed exceptions have confidence scores
        
        ### Knowledge Base Not Persisting
        - Make sure to click "Add to Knowledge Base" after uploading
        - Check that the success message appears
        - Verify in the sidebar that the KB is listed
        
        ## 📊 Understanding Resolutions
        
        - **REPROCESS**: Transient error, safe to retry
        - **PURGE**: Duplicate or non-actionable, can be removed
        - **INVESTIGATE**: Requires developer attention
        
        ## 💡 Best Practices
        
        1. **Always build a KB first** for better accuracy
        2. **Review low-confidence items** regularly
        3. **Add resolved cases back to KB** to improve over time
        4. **Use module names consistently** (case-sensitive)
        
        ## 📋 Required CSV Formats
        
        ### Exception File:
        - LOG_SEQ_NO
        - EVENT_INFORMATION
        - SEVERITY
        
        ### Knowledge Base File:
        - Exception_Type
        - Exception_Message
        - Resolution (REPROCESS/PURGE/INVESTIGATE)
        - Root_Cause
        - Action
        """)

if __name__ == "__main__":
    main()

# ============================================================================
# JSON PARSER MODULE (Embedded)
# ============================================================================
# JSON Parser Module - Enhanced Version
# Advanced parsing, cleaning, and preprocessing of exception data
# Handles EVENT_INFORMATION JSON structure from actual log data
# ============================================================================

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


