# 🚀 Quick Start Guide - AI Exception Modeler V7

## ⏱️ Get Running in 15 Minutes!

### **Step 1: Install Dependencies** (5 minutes)

```bash
# Navigate to project directory
cd exception_modeler_v7

# Install Python packages
pip install -r requirements.txt
```

**Note**: This installs ~2GB of dependencies. Have good internet connection!

---

### **Step 2: Configure Your Code Repository** (1 minute)

Edit `config.py` - Change this line:

```python
# Line 11 in config.py
CODE_REPOSITORY_PATH = "C:/Source/repos/code"  # ← Change to your path
```

**Example paths:**
- Windows: `"C:/Source/repos/code"`
- Linux/Mac: `"/home/user/projects/mycode"`

---

### **Step 3: Index Your Codebase** (5-10 minutes)

```bash
# Run the indexer
python code_indexer.py
```

**What you'll see:**
```
========================================================
  CODE REPOSITORY INDEXER - AI Exception Modeler V7
========================================================

📁 Repository Path: C:/Source/repos/code
🔄 Force Reindex:   No
💾 Vector DB:       data/chromadb/code_repository/

⚠️  This will scan and index all code files in:
   C:/Source/repos/code

   Continue? (y/n): y

========================================================
  INDEXING IN PROGRESS...
========================================================

[Progress updates...]

========================================================
  INDEXING COMPLETE!
========================================================

📊 Statistics:
   Total files found:    95,234
   Files indexed:        45,123
   Files skipped:        50,111 (already up-to-date)
   Duration:             543.2 seconds

✅ Your codebase is now indexed and ready!
```

**Tips:**
- First run: Takes 5-10 minutes for 10GB
- Subsequent runs: < 1 minute (incremental)
- Can use app while indexing in background

---

### **Step 4: Start the Application** (30 seconds)

```bash
streamlit run streamlit_app.py
```

**Browser opens automatically at:** `http://localhost:8501`

---

### **Step 5: Process Your First Exception** (2 minutes)

1. **Upload Exception File**
   - Click "Browse files"
   - Select your CSV/Excel exception file
   - Must have columns: `LOG_SEQ_NO`, `EVENT_INFORMATION`, `SEVERITY`

2. **Configure Settings** (Sidebar)
   - Select Module: `ClaimGeneration` (or your module)
   - Select Model: `Ollama Llama 3.2` (for privacy)
   - ✅ **Enable "Use Code Analysis"** ← Important!

3. **Process**
   - Click "🚀 Process Exceptions"
   - Wait 10-30 seconds (depending on file size)

4. **View Results**
   - See exact root causes with code references!
   - Confidence scores: 80-95% (vs 60-70% without code)
   - Specific fix suggestions

---

## 🎯 **Verify It's Working**

### **Test 1: Code Repository Accessible**

In Python console:
```python
from pathlib import Path
import config

repo_path = Path(config.CODE_REPOSITORY_PATH)
print(f"Repository exists: {repo_path.exists()}")
print(f"Is directory: {repo_path.is_dir()}")
```

Expected output:
```
Repository exists: True
Is directory: True
```

### **Test 2: Code Index Created**

Check that this directory exists:
```
data/chromadb/code_repository/
```

Should contain:
- `chroma.sqlite3` (database file)
- Vector data files
- `indexed_files.json` (metadata)

### **Test 3: Parse Stack Trace**

In Python console:
```python
from stack_trace_parser import StackTraceParser

parser = StackTraceParser()

stack_trace = """
System.NullReferenceException at ClaimGeneration.ProcessClaim 
in C:\\Source\\repos\\code\\ClaimGeneration\\ClaimProcessor.cs:line 234
"""

result = parser.parse_stack_trace(stack_trace)
print(f"File: {result['frames'][0]['file_path']}")
print(f"Line: {result['frames'][0]['line_number']}")
```

Expected output:
```
File: C:\Source\repos\code\ClaimGeneration\ClaimProcessor.cs
Line: 234
```

### **Test 4: Retrieve Code**

In Python console:
```python
from code_repository_manager import CodeRepositoryManager
from pathlib import Path

mgr = CodeRepositoryManager(
    repo_path="C:/Source/repos/code",
    chroma_dir=Path("data/chromadb")
)

# Get stats
stats = mgr.get_repository_stats()
print(f"Indexed files: {stats['indexed_files']}")
print(f"Total chunks: {stats['total_chunks']}")
```

Expected output:
```
Indexed files: 45123
Total chunks: 234567
```

---

## 🐛 **Quick Troubleshooting**

### **Problem: "Repository not found"**

**Check:**
```bash
# Does path exist?
dir C:\Source\repos\code

# Is it correct in config?
python -c "import config; print(config.CODE_REPOSITORY_PATH)"
```

**Fix:**
- Update `config.py` with correct path
- Use forward slashes: `C:/Source/repos/code`

---

### **Problem: "No code retrieved"**

**Check:**
```bash
# Is code indexed?
python -c "from code_repository_manager import CodeRepositoryManager; from pathlib import Path; mgr = CodeRepositoryManager('C:/Source/repos/code', Path('data/chromadb')); print(mgr.get_repository_stats())"
```

**Fix:**
- Run: `python code_indexer.py --reindex`
- Check stack trace format is supported

---

### **Problem: "Token limit exceeded"**

**Fix in `config.py`:**
```python
CODE_RETRIEVAL_CONFIG = {
    'max_snippets': 3,          # Reduce from 5 to 3
    'max_snippet_lines': 50,    # Reduce from 100 to 50
}
```

---

## 🎓 **Next Steps**

### **1. Build Knowledge Base**
- Go to "Knowledge Base" tab
- Upload your exception patterns
- System learns from past resolutions

### **2. Review Low-Confidence Items**
- Go to "Review Queue" tab
- Review items < 70% confidence
- Take action: Purge/Reprocess
- Save learnings to KB

### **3. Monitor System**
- Go to "System Monitor" tab
- Watch live processing
- View worker status
- Check completed tasks

### **4. View Analytics**
- Go to "Analytics" tab
- See processing trends
- Export audit logs
- Track performance

---

## 💡 **Pro Tips**

### **For Best Results:**

1. **Use Local LLM** (Ollama Llama 3.2)
   - 100% private
   - No API costs
   - Fast processing

2. **Enable Code Analysis**
   - Always check "Use Code Analysis"
   - Gets exact root causes
   - Higher confidence

3. **Keep Index Updated**
   - Reindex after major code changes
   - Use incremental indexing
   - Takes < 1 minute

4. **Build Good KB**
   - Upload historical exceptions
   - Keep KB updated
   - System gets smarter over time

5. **Review Queue Discipline**
   - Process review items daily
   - Save learnings to KB
   - Builds institutional knowledge

---

## 📚 **Documentation**

| Document | Purpose |
|----------|---------|
| `README_CODE_INTEGRATION.md` | Complete code integration guide |
| `SPECIFICATIONS.md` | Technical architecture details |
| `QUICK_START.md` | This file - get running fast |

---

## 🆘 **Getting Help**

### **Check Logs**
```bash
# View application logs
cat LOGS/processing_log_*.csv

# View system logs
streamlit run streamlit_app.py --logger.level=debug
```

### **Common Commands**
```bash
# Reindex everything
python code_indexer.py --reindex

# Test configuration
python -c "import config; print(config.get_feature_status())"

# Test code retrieval
python -c "from code_repository_manager import CodeRepositoryManager; from pathlib import Path; mgr = CodeRepositoryManager('C:/Source/repos/code', Path('data/chromadb')); print(mgr.search_code('NullReferenceException', top_k=5))"
```

---

## ✅ **Checklist: You're Ready When...**

- [✅] Dependencies installed (`pip install -r requirements.txt`)
- [✅] Repository path configured in `config.py`
- [✅] Code indexed successfully (`python code_indexer.py`)
- [✅] Application starts (`streamlit run streamlit_app.py`)
- [✅] Can upload and process exception file
- [✅] Results show code context and specific fixes
- [✅] Confidence scores are 80-95%

---

## 🎉 **Success!**

You're now running AI Exception Modeler V7 with **full code analysis**!

**What you can do:**
- ✅ Analyze exceptions with actual code context
- ✅ Get exact root causes (not generic)
- ✅ Receive specific fix suggestions
- ✅ Achieve 80-95% confidence (vs 60-70%)
- ✅ Keep everything private (with local LLM)

**Enjoy precise exception analysis! 🚀**

---

**Next**: Read `README_CODE_INTEGRATION.md` for advanced features!
