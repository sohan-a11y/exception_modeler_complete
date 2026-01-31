<div align="center">

# 🤖 AI Exception Modeler V7.0

**Enterprise-Grade Exception Analysis System with AI-Powered Resolution**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20DB-orange.svg)](https://www.trychroma.com/)

*Transform your exception logs into actionable insights with AI-powered analysis*

[**Quick Start**](#-quick-start) • [**Features**](#-features) • [**Demo**](#-demo-mode) • [**Documentation**](#-documentation)

</div>

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ai-exception-modeler.git
cd ai-exception-modeler

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
streamlit run streamlit_app.py
```

Open your browser at `http://localhost:8501` 🎉

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI-Powered Analysis** | Leverages LLMs (Ollama, Groq, Together AI) for intelligent root cause analysis |
| 📚 **Knowledge Base** | ChromaDB-powered vector search for pattern matching with historical resolutions |
| 🔄 **Smart Deduplication** | 85% similarity threshold groups related exceptions automatically |
| 📋 **Review Queue** | Persistent queue for low-confidence items requiring manual review |
| 📊 **Analytics Dashboard** | Visual insights with resolution distribution, trends, and metrics |
| 💾 **Code Repository Integration** | Index your codebase for precise stack trace analysis |
| 🔐 **Demo Mode** | 24-hour expiring demo links for secure client presentations |

---

## 📸 Screenshots

### Main Dashboard
Process exceptions with AI-powered analysis and real-time progress tracking.

### Analytics View
Visualize resolution patterns, confidence distributions, and exception trends.

### Review Queue
Manage low-confidence items with editable resolutions and audit trails.

---

## 🎮 Demo Mode

Enable demo mode for client presentations with 24-hour access:

```bash
# Set environment variables
export DEMO_MODE=true
export DEMO_USERNAME=client
export DEMO_PASSWORD=your-password

# Run the app
streamlit run streamlit_app.py
```

Demo features:
- ✅ Time-limited access (24 hours)
- ✅ Simple login authentication
- ✅ Sample data included
- ✅ Works without external LLM servers

---

## 📁 Project Structure

```
ai-exception-modeler/
├── streamlit_app.py          # Main application
├── config.py                 # Configuration (demo mode, LLM settings)
├── exception_processor.py    # Processing engine
├── kb_manager.py             # Knowledge base (ChromaDB)
├── enhanced_llm_api.py       # LLM integration
├── demo_auth.py              # Demo authentication system
├── analytics_ai.py           # AI-powered analytics
│
├── demo_data/                # Sample data for demos
│   ├── sample_exceptions.csv
│   └── sample_kb.csv
│
├── static/
│   └── custom.css            # Modern UI theme
│
├── .streamlit/
│   └── config.toml           # Streamlit configuration
│
└── requirements.txt          # Python dependencies
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE` | `false` | Enable demo mode |
| `DEMO_EXPIRY_HOURS` | `24` | Demo session duration |
| `DEMO_USERNAME` | `client` | Demo login username |
| `DEMO_PASSWORD` | `demo2026` | Demo login password |
| `CODE_REPOSITORY_PATH` | - | Path to source code for analysis |

### LLM Options

| Model | Provider | Privacy | Speed |
|-------|----------|---------|-------|
| Llama 3.2 3B | Ollama (Local) | 100% Private | Fast |
| Mistral 7B | Ollama (Local) | 100% Private | Medium |
| Llama 3 70B | Groq API | Cloud | Ultra-fast |
| Mistral 7B | Together AI | Cloud | Fast |

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Processing Speed | 3-5 sec/exception |
| Deduplication | 100 → 10-15 unique patterns |
| Confidence Range | 60-95% (higher with KB) |
| File Size Support | Up to 500MB |

---

## 📖 Documentation

- [QUICK_START.md](./QUICK_START.md) - Get running in 15 minutes
- [SPECIFICATIONS.md](./SPECIFICATIONS.md) - Technical architecture
- [README_CODE_INTEGRATION.md](./README_CODE_INTEGRATION.md) - Code repository setup

---

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

<div align="center">
<p>Built with ❤️ using Streamlit, ChromaDB, and LLM Magic</p>
<p>⭐ Star this repo if you find it useful!</p>
</div>
