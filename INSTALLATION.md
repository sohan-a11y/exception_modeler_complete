# Installation Guide

Complete guide to install and run AI Exception Modeler V7.0.

## Prerequisites

- **Python**: 3.9 or higher
- **RAM**: Minimum 8GB (16GB recommended)
- **Disk**: 2GB for application + space for ChromaDB vectors
- **OS**: Windows, macOS, or Linux

## Quick Installation

```bash
# Clone repository
git clone https://github.com/your-org/ai-exception-modeler.git
cd ai-exception-modeler

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run streamlit_app.py
```

## LLM Setup Options

### Option 1: Ollama (Recommended - 100% Private)

```bash
# Install Ollama from https://ollama.ai
# Download a model
ollama pull llama3.2

# Ollama runs automatically on localhost:11434
```

### Option 2: Cloud APIs

Set environment variables for cloud LLM providers:

```bash
# Groq
export GROQ_API_KEY=your-api-key

# Together AI
export TOGETHER_API_KEY=your-api-key

# OpenAI
export OPENAI_API_KEY=your-api-key
```

## Demo Mode Setup

For client presentations:

```bash
# Set environment variables
export DEMO_MODE=true
export DEMO_USERNAME=client
export DEMO_PASSWORD=your-secure-password
export DEMO_EXPIRY_HOURS=24

# Run in demo mode
streamlit run streamlit_app.py
```

## Deployment Options

### Streamlit Community Cloud (Free)

1. Push to GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Add secrets in Streamlit Cloud dashboard

### Docker

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py"]
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Module not found | Run `pip install -r requirements.txt` |
| Port already in use | Use `streamlit run streamlit_app.py --server.port 8502` |
| Ollama connection error | Ensure Ollama is running: `ollama serve` |
| ChromaDB error | Delete `data/chromadb/` folder and restart |

## Next Steps

1. Upload a Knowledge Base file in the KB tab
2. Upload exception data in Process Exceptions tab
3. Configure confidence thresholds in sidebar
4. Process and analyze exceptions!
