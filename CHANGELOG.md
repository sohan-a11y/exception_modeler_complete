# Changelog

All notable changes to AI Exception Modeler are documented here.

## [7.0.0] - 2026-01-31

### Added
- 🔐 **Demo Mode**: 24-hour expiring demo links for secure client presentations
- 🎨 **Modern UI Theme**: Professional CSS with glassmorphism, animations, dark mode
- 📊 **AI Analytics**: Implemented full analytics dashboard with insights
- 📁 **Sample Data**: Demo exception and KB files for presentations
- ⚙️ **Environment Config**: Support for deployment via environment variables
- 📄 **Documentation**: Professional README, CHANGELOG, LICENSE

### Changed
- Unified version naming to V7.0 throughout application
- Made code repository path configurable via environment variable
- Improved error handling and fallbacks

### Fixed
- Duplicate `st.set_page_config()` calls causing startup errors
- Duplicate `logging.basicConfig()` calls
- Placeholder `analytics_ai.py` now has full implementation

## [6.0.0] - 2024-12

### Added
- Parallel processing with 2-8 workers
- Persistent review queue
- Audit logging

## [5.0.0] - 2024-11

### Added
- Multi-module Knowledge Base
- Enhanced deduplication
- Cross-module KB search

## [4.0.0] - 2024-10

### Added
- LLM integration (Ollama, Groq, Together AI)
- Confidence scoring

## [3.0.0] - 2024-09

### Added
- ChromaDB vector search
- Semantic similarity matching
