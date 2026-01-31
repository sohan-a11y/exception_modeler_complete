"""
Code Indexer - Standalone Script
Run this once to index your codebase for exception analysis

Usage:
    python code_indexer.py                    # Index default path from config
    python code_indexer.py C:/custom/path     # Index custom path
    python code_indexer.py --reindex          # Force reindex all files
"""

import sys
import logging
from pathlib import Path
from code_repository_manager import CodeRepositoryManager
import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print welcome banner"""
    print("=" * 80)
    print("  CODE REPOSITORY INDEXER - AI Exception Modeler V7")
    print("=" * 80)
    print()


def print_stats(stats: dict):
    """Print indexing statistics"""
    print("\n" + "=" * 80)
    print("  INDEXING COMPLETE!")
    print("=" * 80)
    print(f"\n📊 Statistics:")
    print(f"   Total files found:    {stats['total_files_found']}")
    print(f"   Files indexed:        {stats['files_indexed']}")
    print(f"   Files skipped:        {stats['files_skipped']} (already up-to-date)")
    print(f"   Files updated:        {stats['files_updated']}")
    print(f"   Errors:               {stats['errors']}")
    print(f"   Duration:             {stats['duration_seconds']:.1f} seconds")
    print()
    
    if stats['files_indexed'] > 0:
        print("✅ Your codebase is now indexed and ready for exception analysis!")
        print("   Run: streamlit run streamlit_app.py")
    else:
        print("ℹ️  No new files to index. Everything is up-to-date.")
    
    print("=" * 80)


def main():
    """Main indexing function"""
    print_banner()
    
    # Parse command line arguments
    force_reindex = '--reindex' in sys.argv or '-r' in sys.argv
    custom_path = None
    
    for arg in sys.argv[1:]:
        if not arg.startswith('-') and Path(arg).exists():
            custom_path = arg
            break
    
    # Determine repository path
    repo_path = custom_path if custom_path else config.CODE_REPOSITORY_PATH
    
    print(f"📁 Repository Path: {repo_path}")
    print(f"🔄 Force Reindex:   {'Yes' if force_reindex else 'No'}")
    print(f"💾 Vector DB:       data/chromadb/code_repository/")
    print()
    
    # Validate path
    if not Path(repo_path).exists():
        print(f"❌ ERROR: Repository path does not exist!")
        print(f"   Path: {repo_path}")
        print()
        print("💡 To fix:")
        print("   1. Edit config.py and set CODE_REPOSITORY_PATH")
        print("   2. Or run: python code_indexer.py C:/your/code/path")
        sys.exit(1)
    
    # Confirm with user
    print(f"⚠️  This will scan and index all code files in:")
    print(f"   {repo_path}")
    print()
    
    if not force_reindex:
        print("   Note: Already-indexed files will be skipped (incremental indexing)")
        print("   Use --reindex flag to force reindex all files")
    else:
        print("   ⚠️  FORCE REINDEX MODE: All files will be reindexed")
    
    print()
    response = input("   Continue? (y/n): ").strip().lower()
    
    if response != 'y':
        print("\n❌ Indexing cancelled by user")
        sys.exit(0)
    
    print()
    print("=" * 80)
    print("  INDEXING IN PROGRESS...")
    print("=" * 80)
    print()
    
    try:
        # Initialize repository manager
        logger.info("Initializing Code Repository Manager...")
        repo_manager = CodeRepositoryManager(
            repo_path=repo_path,
            chroma_dir=Path("data/chromadb")
        )
        
        # Run indexing
        logger.info("Starting indexing process...")
        stats = repo_manager.index_repository(force_reindex=force_reindex)
        
        # Print results
        print_stats(stats)
        
        # Get repository stats
        repo_stats = repo_manager.get_repository_stats()
        print("\n📈 Repository Statistics:")
        print(f"   Indexed files:     {repo_stats['indexed_files']}")
        print(f"   Code chunks:       {repo_stats['total_chunks']}")
        print(f"   Supported types:   {', '.join(list(repo_stats['supported_extensions'])[:5])}...")
        print()
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("  ❌ INDEXING FAILED!")
        print("=" * 80)
        print(f"\nError: {str(e)}")
        print()
        print("💡 Troubleshooting:")
        print("   1. Check that the repository path is correct")
        print("   2. Ensure you have read permissions")
        print("   3. Check disk space (needs ~5% of codebase size)")
        print("   4. Review logs for detailed error information")
        print()
        logger.error(f"Indexing failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
