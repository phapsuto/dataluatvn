from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import json
import uuid

# Import the new store instead of the memory one
from app.utils.document_store import (
    search_notebook_docs,
    add_source_text,
    create_notebook,
    get_notebook,
    list_notebooks,
    delete_notebook,
    update_notebook,
    list_sources,
    delete_source,
    add_notebook_message,
    get_source_text,
    UPLOADS_DIR,
    create_processing_source,
    add_source_chunks,
    update_source_progress,
    create_mindmap,
    get_mindmaps,
    get_mindmap,
    update_mindmap,
    delete_mindmap,
    NOTEBOOK_DB
)
import sqlite3
from app.utils.llm_gateway import LLMGateway
from app.utils.file_parsers import parse_file

router = APIRouter(prefix="/doc-assistant", tags=["NoteBook AI"])

# --- Notebook CRUD ---

class NotebookCreate(BaseModel):
    title: str
    description: str = None
    case_number: str = None
    user_id: str = "default"

@router.post("/notebooks")
async def api_create_notebook(req: NotebookCreate):
    notebook_id = f"nb_{uuid.uuid4().hex[:12]}"
    nb = create_notebook(notebook_id, req.title, req.description, req.case_number, req.user_id)
    return {"status": "success", "notebook": nb}

@router.get("/notebooks")
async def api_list_notebooks(user_id: str = "default"):
    nbs = list_notebooks(user_id)
    return {"status": "success", "notebooks": nbs}

@router.get("/notebooks/{notebook_id}")
async def api_get_notebook(notebook_id: str):
    nb = get_notebook(notebook_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"status": "success", "notebook": nb}

class NotebookUpdate(BaseModel):
    title: str = None
    description: str = None
    case_number: str = None
    isPublic: bool = None

@router.put("/notebooks/{notebook_id}")
async def api_update_notebook(notebook_id: str, req: NotebookUpdate):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if not updates:
        return {"status": "success", "notebook": get_notebook(notebook_id)}
    nb = update_notebook(notebook_id, updates)
    return {"status": "success", "notebook": nb}

@router.delete("/notebooks/{notebook_id}")
async def api_delete_notebook(notebook_id: str):
    success = delete_notebook(notebook_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"status": "success"}

# --- Sources CRUD & Upload ---

@router.post("/upload")
async def upload_document(request: Request):
    """Backward compatible endpoint for text upload"""
    req = await request.json()
    notebook_id = req.get("notebook_id")
    source_id = req.get("source_id", f"src_{uuid.uuid4().hex[:8]}")
    text = req.get("text")
    if not notebook_id or not text:
        raise HTTPException(status_code=400, detail="Missing notebook_id or text")
    
    res = add_source_text(notebook_id, source_id, text)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

def process_file_background(notebook_id: str, source_id: str, filename: str, file_bytes: bytes):
    try:
        def progress_callback(processed, total):
            update_source_progress(source_id, "processing", processed, total)
            
        text = parse_file(filename, file_bytes, progress_callback)
        add_source_chunks(notebook_id, source_id, text)
    except Exception as e:
        update_source_progress(source_id, "error")
        print(f"[Background Task Error] {e}")

@router.post("/upload-file")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    notebook_id: str = Form(...),
):
    """Upload a real file (PDF, DOCX, TXT)"""
    file_bytes = await file.read()
    
    # 50MB limit
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max size is 50MB.")
        
    source_id = f"src_{uuid.uuid4().hex[:8]}"
    
    # Save the physical file so user can download/view later
    import os
    save_dir = os.path.join(UPLOADS_DIR, notebook_id)
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, f"{source_id}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    create_processing_source(notebook_id, source_id, file.filename, file.content_type, len(file_bytes))
    
    background_tasks.add_task(process_file_background, notebook_id, source_id, file.filename, file_bytes)
        
    return {"status": "processing", "source_id": source_id, "message": "File is being processed in the background."}

@router.get("/sources/{notebook_id}/{source_id}/text")
async def api_get_source_text(notebook_id: str, source_id: str):
    text = get_source_text(source_id)
    if not text:
        raise HTTPException(status_code=404, detail="Source text not found")
    return {"status": "success", "text": text}

@router.get("/sources/{notebook_id}/{source_id}/download")
async def api_download_source(notebook_id: str, source_id: str):
    import os
    sources = list_sources(notebook_id)
    target_src = next((s for s in sources if s['id'] == source_id), None)
    if not target_src:
        raise HTTPException(status_code=404, detail="Source not found")
        
    file_path = os.path.join(UPLOADS_DIR, notebook_id, f"{source_id}_{target_src['filename']}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical file not found")
        
    return FileResponse(file_path, filename=target_src['filename'])

@router.get("/sources/{notebook_id}")
async def api_list_sources(notebook_id: str):
    sources = list_sources(notebook_id)
    return {"status": "success", "sources": sources}

@router.delete("/sources/{notebook_id}/{source_id}")
async def api_delete_source(notebook_id: str, source_id: str):
    success = delete_source(notebook_id, source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"status": "success"}


# --- Chat Stream ---

@router.post("/chat-stream")
async def doc_chat_stream(request: Request):
    req = await request.json()
    notebook_id = req.get("notebook_id")
    prompt_text = req.get("prompt")
    selected_source_ids = req.get("selected_source_ids", None)
    
    # 1. Fetch chat history
    conn = sqlite3.connect(NOTEBOOK_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT role, content FROM notebook_messages WHERE notebook_id = ? ORDER BY created_at ASC", (notebook_id,))
    rows = c.fetchall()
    conn.close()
    
    messages = []
    # limit to last 20 messages (10 turns) to fit context window
    for r in rows[-20:]:
        messages.append({"role": r["role"], "content": r["content"]})
        
    search_query = prompt_text
    
    # 2. Query Rewrite (Tái cấu trúc câu hỏi nếu có lịch sử)
    if len(messages) > 0:
        rewrite_sys_prompt = (
            "Bạn là một chuyên gia phân tích ngữ nghĩa. Nhiệm vụ của bạn là đọc lịch sử trò chuyện và câu hỏi mới nhất của người dùng, "
            "sau đó VIẾT LẠI câu hỏi đó thành một câu hỏi độc lập (Standalone Query) chứa đầy đủ chủ ngữ và ngữ cảnh để máy học (FAISS) có thể tìm kiếm chính xác.\n"
            "Quy tắc:\n"
            "1. CHỈ TRẢ VỀ ĐÚNG CÂU HỎI ĐÃ VIẾT LẠI.\n"
            "2. KHÔNG giải thích, KHÔNG thêm từ thừa thãi như 'Câu hỏi độc lập là:', 'Đây là câu hỏi:'.\n"
            "3. Nếu câu hỏi gốc đã rõ ràng và đủ nghĩa (không chứa từ nhân xưng mập mờ như 'nó', 'đó', 'thế nào'), HÃY GIỮ NGUYÊN câu hỏi gốc."
        )
        rewrite_user_prompt = f"Câu hỏi mới nhất: {prompt_text}"
        
        try:
            standalone_query = await LLMGateway.call_async(
                messages=messages + [{"role": "user", "content": rewrite_user_prompt}],
                system_prompt=rewrite_sys_prompt,
                temperature=0.0
            )
            if standalone_query and len(standalone_query) > 2:
                search_query = standalone_query.strip()
                print(f"[Query Rewrite] Original: '{prompt_text}' -> Standalone: '{search_query}'")
        except Exception as e:
            print("Lỗi khi Query Rewrite:", e)
            
            
    # 3. Tra cứu FAISS tài liệu với Standalone Query
    docs = search_notebook_docs(notebook_id, search_query, top_k=20)
    
    if selected_source_ids is not None:
        docs = [d for d in docs if d['source_id'] in selected_source_ids]
    
    # 3.1. FPT Cloud Rerank (bge-reranker-v2-m3) — riêng cho Notebook, không ảnh hưởng module Luật
    if docs and len(docs) > 1:
        try:
            from app.config import FPT_CLOUD_API_KEY
            if FPT_CLOUD_API_KEY:
                import httpx
                rerank_passages = [d['text'][:2000] for d in docs[:20]]
                rerank_payload = {
                    "model": "bge-reranker-v2-m3",
                    "query": search_query,
                    "documents": rerank_passages,
                    "top_n": min(8, len(rerank_passages))
                }
                async with httpx.AsyncClient() as client:
                    rerank_res = await client.post(
                        "https://mkp-api.fptcloud.com/v1/rerank",
                        json=rerank_payload,
                        headers={"Authorization": f"Bearer {FPT_CLOUD_API_KEY}", "Content-Type": "application/json"},
                        timeout=8.0
                    )
                    if rerank_res.status_code == 200:
                        rerank_data = rerank_res.json()
                        rerank_results = rerank_data.get("results") or []
                        reranked_docs = []
                        for item in rerank_results:
                            idx = item["index"]
                            relevance = item["relevance_score"]
                            original = docs[idx].copy()
                            original["score"] = float(relevance)
                            reranked_docs.append(original)
                        docs = reranked_docs
                        print(f"[Notebook Rerank] {len(rerank_passages)} → {len(docs)} docs reranked")
                    else:
                        print(f"[Notebook Rerank] API error {rerank_res.status_code}, using FAISS order")
        except Exception as e:
            print(f"[Notebook Rerank] Skipped: {e}")
    
    # 3.2. Score threshold — loại bỏ chunks hoàn toàn không liên quan
    # FAISS IP scores cho Vietnamese Embedding thường nằm trong khoảng 0.05 - 0.5
    # Reranker scores nằm trong khoảng 0.0 - 1.0
    SCORE_THRESHOLD = 0.01
    docs = [d for d in docs if d.get('score', 0) >= SCORE_THRESHOLD]
    
    docs = docs[:5]  # Chỉ lấy 5 đoạn trích phù hợp nhất sau khi lọc + rerank
    
    has_relevant_docs = len(docs) > 0
    doc_context = "\n\n".join([f"--- Đoạn trích {i+1} (Từ file: {d.get('filename', 'Unknown')}, Đoạn {d.get('chunk_index', 0) + 1}) ---\n{d['text']}" for i, d in enumerate(docs)])
    
    # 4. Sinh prompt cho LLM
    system_prompt = "Bạn là Trợ lý AI Viện Kiểm sát (NoteBook AI). Dựa vào các đoạn trích từ hồ sơ vụ án do Kiểm sát viên cung cấp dưới đây, hãy trả lời câu hỏi một cách chính xác, ngắn gọn và khách quan. CHỈ SỬ DỤNG thông tin từ hồ sơ được cung cấp. Nếu bạn sử dụng thông tin từ đoạn trích nào, BẮT BUỘC phải trích dẫn nguồn ở cuối câu bằng cấu trúc [Tên file] (ví dụ: [Đề-cương.pdf]). TUYỆT ĐỐI KHÔNG LẶP LẠI CÂU TRẢ LỜI."
    if has_relevant_docs:
        system_prompt += f"\n\n[HỒ SƠ VỤ ÁN TỪ NOTEBOOK]\n{doc_context}"
    else:
        system_prompt += "\n\n[LƯU Ý] Không tìm thấy đoạn tài liệu nào đủ liên quan đến câu hỏi trong NoteBook này. Hãy trả lời rằng bạn không tìm thấy thông tin phù hợp trong tài liệu đã tải lên. KHÔNG ĐƯỢC BỊA thông tin."
        
    messages.append({"role": "user", "content": prompt_text})
    
    citations_dict = {}
    for d in docs:
        sid = d['source_id']
        if sid not in citations_dict:
            citations_dict[sid] = {
                "id": sid, 
                "title": d.get('filename', f"Tài liệu {sid}"),
                "filename": d.get('filename', 'Unknown'),
                "snippets": []
            }
        
        chunk_idx = d.get('chunk_index', 0) + 1
        snippet_text = f"[Đoạn {chunk_idx}] {d['text']}"
        citations_dict[sid]["snippets"].append(snippet_text)
        
    citations = list(citations_dict.values())
    
    # Save user message
    user_msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    add_notebook_message(notebook_id, user_msg_id, "user", prompt_text)
    
    # 3. Stream
    async def event_generator():
        full_response = ""
        try:
            async for chunk in LLMGateway.call_stream(messages=messages, system_prompt=system_prompt):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'citations': citations}, ensure_ascii=False)}\n\n"
        except Exception as e:
            err_msg = f"\\n\\n[Lỗi AI]: {str(e)}"
            full_response += err_msg
            yield f"data: {json.dumps({'text': err_msg})}\n\n"
            
        # Save assistant message
        if full_response:
            ai_msg_id = f"msg_{uuid.uuid4().hex[:12]}"
            add_notebook_message(notebook_id, ai_msg_id, "assistant", full_response, citations=citations)
        
        yield "data: [DONE]\n\n"
        
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Mind Map Generation ---

MINDMAP_SYSTEM_PROMPT = """Bạn là trợ lý pháp lý chuyên phân tích hồ sơ pháp luật tại Việt Nam.
Nhiệm vụ: Đọc tài liệu và tạo bản đồ tư duy (mind map) dạng JSON.

BƯỚC 1: Nhận diện loại tài liệu (hình sự, dân sự, hôn nhân gia đình, hành chính, kinh doanh thương mại, khác).

BƯỚC 2: Tạo các nhánh chính PHÙ HỢP với loại tài liệu:

[Nếu HÌNH SỰ]:
- "info": Thông tin chung (số vụ án, tội danh, thời gian/địa điểm)
- "parties": Các bên (bị can/bị cáo, bị hại, người liên quan)
- "crime": Cấu thành tội phạm (khách thể, chủ thể, mặt khách quan/chủ quan)
- "evidence": Chứng cứ (vật chứng, lời khai, giám định)
- "procedure": Quy trình tố tụng (khởi tố, điều tra, truy tố, xét xử)
- "legal": Căn cứ pháp lý (điều luật, tình tiết tăng nặng/giảm nhẹ)

[Nếu DÂN SỰ / HÔN NHÂN GIA ĐÌNH]:
- "info": Thông tin chung (số vụ, loại tranh chấp, thời gian)
- "parties": Các bên (nguyên đơn, bị đơn, người liên quan)
- "evidence": Tài sản / Chứng cứ (bất động sản, động sản, giấy tờ, lời khai)
- "legal": Căn cứ pháp lý (điều luật áp dụng)
- "procedure": Quá trình giải quyết (hòa giải, sơ thẩm, phúc thẩm)

[Nếu HÀNH CHÍNH]:
- "info": Thông tin chung (quyết định bị khiếu kiện, cơ quan ban hành)
- "parties": Các bên (người khiếu kiện, cơ quan bị kiện)
- "evidence": Căn cứ khiếu kiện (tài liệu, vi phạm thủ tục)
- "legal": Căn cứ pháp lý
- "procedure": Quá trình giải quyết

[Nếu VĂN BẢN QUY PHẠM / TÀI LIỆU KHÁC]:
- "info": Thông tin chung
- Các nhánh theo nội dung chính của tài liệu

BƯỚC 3: Tạo JSON theo format:
{
  "root": {
    "id": "root",
    "label": "Tên vụ án / Tên tài liệu",
    "type": "root",
    "children": [
      {
        "id": "info",
        "label": "Thông tin chung",
        "type": "info",
        "children": [
          { "id": "info_1", "label": "Nội dung cụ thể", "type": "detail", "description": "Chi tiết...", "sourceRef": "src_123" }
        ]
      }
    ]
  }
}

Quy tắc:
- Mỗi node phải có id duy nhất, label ngắn gọn (< 50 ký tự), type đúng
- Chỉ trích xuất thông tin CÓ trong tài liệu, KHÔNG bịa
- Nhánh nào không có thông tin thì bỏ qua
- description là tóm tắt chi tiết (có thể dài hơn label)
- TRỌNG TÂM: Mỗi node chi tiết (tầng 3+) PHẢI có trường "sourceRef" = chính xác ID tài liệu chứa thông tin (vd: "src_123")
- Trả về CHỈ JSON, không markdown, không giải thích
- Tạo NHIỀU node chi tiết — bản đồ tư duy phải ĐẦY ĐỦ và TOÀN DIỆN"""

@router.post("/mindmap-generate")
async def generate_mindmap(request: Request):
    """
    Generate a mind map JSON from notebook documents using AI.
    
    Uses a 2-phase Map-Reduce approach for large documents:
    - Phase 1 (Map): Summarize batches of chunks in parallel
    - Phase 2 (Reduce): Generate mind map from all summaries
    """
    import re
    import asyncio
    import sqlite3 as _sqlite3
    from app.utils.document_store import NOTEBOOK_DB

    req = await request.json()
    notebook_id = req.get("notebook_id")
    selected_source_ids = req.get("selected_source_ids")
    case_title = req.get("case_title", "Vụ án")

    if not notebook_id:
        raise HTTPException(status_code=400, detail="Missing notebook_id")

    # 1. Fetch ALL chunks from SQLite (no limit)
    conn = _sqlite3.connect(NOTEBOOK_DB)
    c = conn.cursor()

    if selected_source_ids:
        placeholders = ",".join(["?"] * len(selected_source_ids))
        c.execute(
            f"SELECT source_id, text FROM notebook_chunks WHERE notebook_id = ? AND source_id IN ({placeholders}) ORDER BY chunk_index",
            [notebook_id] + selected_source_ids
        )
    else:
        c.execute(
            "SELECT source_id, text FROM notebook_chunks WHERE notebook_id = ? ORDER BY chunk_index",
            (notebook_id,)
        )

    rows = c.fetchall()
    conn.close()

    total_chunks = len(rows)
    print(f"[MindMap] Notebook {notebook_id}: {total_chunks} chunks")

    if not rows:
        return {
            "root": {
                "id": "root",
                "label": case_title,
                "type": "root",
                "children": []
            }
        }

    all_chunks = [{"source_id": r[0], "text": r[1]} for r in rows if r[1]]
    
    # ═══ DECIDE STRATEGY ═══
    # Small doc (≤ 40 chunks, ~30 pages): Direct generation
    # Large doc (> 40 chunks): 2-phase Map-Reduce
    
    DIRECT_THRESHOLD = 40  # chunks
    BATCH_SIZE = 20        # chunks per batch in Phase 1

    if total_chunks <= DIRECT_THRESHOLD:
        # ──── DIRECT: Single-pass generation ────
        combined_text = "\n\n---\n\n".join([f"[Tài liệu ID: {c['source_id']}]\n{c['text']}" for c in all_chunks])[:30000]
        
        messages = [
            {"role": "user", "content": f"Tiêu đề: {case_title}\n\nNội dung tài liệu:\n{combined_text}\n\nHãy tạo bản đồ tư duy JSON cho tài liệu này. Nhớ chú thích sourceRef cho từng thông tin."}
        ]
        
        print(f"[MindMap] Direct mode: {total_chunks} chunks, {len(combined_text)} chars")

    else:
        # ──── 2-PHASE MAP-REDUCE ────
        
        # Phase 1: Summarize batches in parallel
        batches = []
        for i in range(0, len(all_chunks), BATCH_SIZE):
            batch_chunks = all_chunks[i:i + BATCH_SIZE]
            batch_text = "\n\n---\n\n".join([f"[Tài liệu ID: {c['source_id']}]\n{c['text']}" for c in batch_chunks])
            batches.append(batch_text)
        
        print(f"[MindMap] Map-Reduce mode: {total_chunks} chunks → {len(batches)} batches")

        SUMMARY_PROMPT = """Bạn là trợ lý pháp lý. Hãy đọc đoạn tài liệu dưới đây và trích xuất TÓM TẮT ngắn gọn gồm:
1. Nhân vật/tổ chức được đề cập (tên, vai trò)
2. Sự kiện, hành vi quan trọng (thời gian, địa điểm)  
3. Chứng cứ, tài liệu
4. Điều luật, quy định pháp lý
5. Quyết định tố tụng

Trả lời ngắn gọn dạng bullet points, tối đa 300 từ. TUYỆT ĐỐI GHI RÕ [Nguồn: ID tài liệu] ở mỗi ý. CHỈ trích xuất thông tin CÓ trong đoạn, KHÔNG bịa."""

        async def summarize_batch(batch_idx: int, text: str) -> str:
            try:
                result = await LLMGateway.call_async(
                    messages=[{"role": "user", "content": f"Đoạn {batch_idx + 1}:\n{text[:8000]}"}],
                    system_prompt=SUMMARY_PROMPT,
                    temperature=0.1,
                    max_tokens=800
                )
                # Strip thinking tags
                result = re.sub(r"<think>[\s\S]*?</think>", "", result, flags=re.IGNORECASE).strip()
                return f"[Phần {batch_idx + 1}]\n{result}"
            except Exception as e:
                print(f"[MindMap] Batch {batch_idx} summarization failed: {e}")
                return f"[Phần {batch_idx + 1}] (Lỗi tóm tắt)"

        # Run batches concurrently (max 5 parallel)
        semaphore = asyncio.Semaphore(5)
        
        async def limited_summarize(idx: int, text: str) -> str:
            async with semaphore:
                return await summarize_batch(idx, text)

        tasks = [limited_summarize(i, b) for i, b in enumerate(batches)]
        summaries = await asyncio.gather(*tasks)
        
        combined_summaries = "\n\n".join(summaries)
        print(f"[MindMap] Phase 1 done: {len(summaries)} summaries, {len(combined_summaries)} chars total")
        
        # Phase 2: Generate mind map from summaries
        messages = [
            {"role": "user", "content": f"Tiêu đề: {case_title}\n\nDưới đây là TÓM TẮT từ {len(summaries)} phần của tài liệu ({total_chunks} đoạn trích, ước tính {total_chunks * 800 // 250} trang):\n\n{combined_summaries}\n\nHãy tạo bản đồ tư duy JSON TỔNG HỢP cho tài liệu này."}
        ]

    # ═══ CALL LLM (shared for both strategies) ═══
    try:
        content = await LLMGateway.call_async(
            messages=messages,
            system_prompt=MINDMAP_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=8192
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    # Strip thinking tags & extract JSON
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()

    json_match = re.search(r"\{[\s\S]*\}", content)
    if not json_match:
        raise HTTPException(status_code=500, detail="AI did not return valid JSON")

    try:
        parsed = json.loads(json_match.group())
        return parsed
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in AI response")

# --- Mindmaps CRUD ---

class MindmapCreate(BaseModel):
    title: str
    data: str = "{}"

@router.post("/notebooks/{notebook_id}/mindmaps")
async def api_create_mindmap(notebook_id: str, req: MindmapCreate):
    mindmap_id = f"mm_{uuid.uuid4().hex[:12]}"
    mm = create_mindmap(mindmap_id, notebook_id, req.title, req.data)
    return {"status": "success", "mindmap": mm}

@router.get("/notebooks/{notebook_id}/mindmaps")
async def api_get_mindmaps(notebook_id: str):
    mms = get_mindmaps(notebook_id)
    return {"status": "success", "mindmaps": mms}

@router.get("/mindmaps/{mindmap_id}")
async def api_get_mindmap(mindmap_id: str):
    mm = get_mindmap(mindmap_id)
    if not mm:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    return {"status": "success", "mindmap": mm}

class MindmapUpdate(BaseModel):
    title: str = None
    data: str = None

@router.put("/mindmaps/{mindmap_id}")
async def api_update_mindmap(mindmap_id: str, req: MindmapUpdate):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if not updates:
        return {"status": "success", "mindmap": get_mindmap(mindmap_id)}
    mm = update_mindmap(mindmap_id, updates)
    return {"status": "success", "mindmap": mm}

@router.delete("/mindmaps/{mindmap_id}")
async def api_delete_mindmap(mindmap_id: str):
    success = delete_mindmap(mindmap_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    return {"status": "success"}
