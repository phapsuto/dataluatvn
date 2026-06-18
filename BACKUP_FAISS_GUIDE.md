# 📖 Fallback Guide: Restoring FAISS & Legacy SQLite Vector Store

This document explains how to revert the RAG search backend from **Alibaba Zvec** back to the legacy **FAISS + SQLite** system in case of production instability.

---

## 🎛️ Step 1: Update the Environment Configuration

Open the `.env` file in the project root (`/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/.env`) and update the `USE_ZVEC_BACKEND` feature flag to `false`:

```ini
# Change this from true to false
USE_ZVEC_BACKEND=false
```

---

## 📦 Step 2: Restore the FAISS Index & SQLite Vector Database Files

During the Zvec migration, the legacy FAISS index and SQLite vector database files were backed up in the `backup_faiss/` directory to save disk space and prevent index contamination.

To restore these files, move them from `backup_faiss/` back into the project root:

```bash
# Move the files back to the project root
mv backup_faiss/chunks_faiss_sq8.index ./
mv backup_faiss/vector_store.db ./
mv backup_faiss/chunks_faiss.index.disabled ./
```

---

## 🔄 Step 3: Restart the Backend Server & Telegram Bot

To apply the changes and reload the FAISS index into memory, restart the backend components:

### A. Restart FastAPI Server
1. Find and kill the running `server.py` process:
   ```bash
   kill $(pgrep -f "server.py")
   ```
2. Restart the server in the background:
   ```bash
   python3 server.py
   ```

### B. Restart Telegram Bot
1. Find and kill the running `telegram_bot.py` process:
   ```bash
   kill $(pgrep -f "telegram_bot.py")
   ```
2. Restart the bot in the background:
   ```bash
   python3 -u telegram_bot.py
   ```

---

## 🧪 Step 4: Verification

1. Check the server log (`logs/server.log`) to confirm the FAISS index has been loaded:
   ```text
   ✅ Loaded FAISS index from chunks_faiss_sq8.index
   ```
2. Run the unit test suite to verify the search functions:
   ```bash
   pytest
   ```
   All tests should pass.
