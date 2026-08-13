from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import json
import uuid
import threading

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
    update_source_summary,
    create_mindmap,
    get_mindmaps,
    get_mindmap,
    update_mindmap,
    delete_mindmap,
    add_notebook_entity,
    get_notebook_entities,
    NOTEBOOK_DB,
    get_db_conn,
    create_notebook_note,
    list_notebook_notes,
    update_notebook_note,
    delete_notebook_note,
    add_entity_relationship,
    get_entity_relationships,
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

@router.delete("/notebooks/{notebook_id}/messages")
async def api_delete_notebook_messages(notebook_id: str):
    from app.utils.document_store import clear_notebook_messages
    clear_notebook_messages(notebook_id)
    return {"status": "success"}

@router.get("/notebooks/{notebook_id}/entities")
async def api_get_notebook_entities(notebook_id: str):
    entities = get_notebook_entities(notebook_id)
    relationships = get_entity_relationships(notebook_id)
    return {"status": "success", "entities": entities, "relationships": relationships}

# --- Notebook Notes CRUD ---

class NoteCreate(BaseModel):
    id: str
    title: str
    type: str = 'markdown'
    content: str = ''
    icon: str = 'FileTextOutlined'
    color: str = '#1a73e8'

@router.post("/notebooks/{notebook_id}/notes")
async def api_create_note(notebook_id: str, req: NoteCreate):
    note = create_notebook_note(notebook_id, req.id, req.title, req.type, req.content, req.icon, req.color)
    return {"status": "success", "note": note}

@router.get("/notebooks/{notebook_id}/notes")
async def api_list_notes(notebook_id: str):
    notes = list_notebook_notes(notebook_id)
    return {"status": "success", "notes": notes}

class NoteUpdate(BaseModel):
    title: str = None
    content: str = None

@router.put("/notes/{note_id}")
async def api_update_note(note_id: str, req: NoteUpdate):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if not updates:
        return {"status": "success"}
    note = update_notebook_note(note_id, updates)
    return {"status": "success", "note": note}

@router.delete("/notes/{note_id}")
async def api_delete_note(note_id: str):
    success = delete_notebook_note(note_id)
    if not success:
        raise HTTPException(status_code=404, detail="Note not found")
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

# Semaphore to limit concurrent file processing (prevent embed_texts OOM with 10+ files)
_file_processing_semaphore = threading.Semaphore(3)

def process_file_background(notebook_id: str, source_id: str, filename: str, file_bytes: bytes):
    with _file_processing_semaphore:
        try:
            def progress_callback(processed, total):
                update_source_progress(source_id, "processing", processed, total)
                
            text = parse_file(filename, file_bytes, progress_callback)
            result = add_source_chunks(notebook_id, source_id, text)
            
            # Auto-generate summary after successful processing
            if result.get("status") == "success" and text.strip():
                try:
                    import asyncio
                    summary_text = text[:8000]  # First ~8K chars for summary
                    summary_prompt = (
                        "Tóm tắt tài liệu sau đây trong 2-3 câu ngắn gọn bằng tiếng Việt. "
                        "Nêu rõ loại tài liệu (ví dụ: bản cáo trạng, quyết định, biên bản...) và nội dung chính. "
                        "CHỈ TRẢ VỀ TÓM TẮT, không giải thích thêm."
                    )
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    summary = loop.run_until_complete(
                        LLMGateway.call_async(
                            messages=[{"role": "user", "content": summary_text}],
                            system_prompt=summary_prompt,
                            temperature=0.1,
                            max_tokens=300
                        )
                    )
                    loop.close()
                    if summary and len(summary.strip()) > 10:
                        update_source_summary(source_id, summary.strip())
                        print(f"[Auto-Summary] {filename}: {summary.strip()[:80]}...")
                except Exception as e:
                    print(f"[Auto-Summary] Skipped for {filename}: {e}")
                    
                # Auto-Extract Entities + Relationships
                try:
                    entity_prompt = (
                        "Trích xuất danh sách các thực thể quan trọng từ tài liệu pháp lý sau. "
                        "Chỉ lấy: Bị can (bị cáo), Bị hại, Người liên quan, Vật chứng, Thời gian, Địa điểm, Tội danh. "
                        "Trả về CHUẨN JSON format:\n"
                        "{\n"
                        '  "entities": [{"type": "loại", "name": "tên thực thể", "context": "đoạn trích ngắn gọn liên quan"}],\n'
                        '  "relationships": [{"source": "tên thực thể nguồn", "target": "tên thực thể đích", "type": "quan hệ", "description": "mô tả ngắn"}]\n'
                        "}\n"
                        "KHÔNG giải thích thêm. NẾU KHÔNG CÓ THỰC THỂ NÀO, TRẢ VỀ entities: [], relationships: []."
                    )
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    entities_json = loop.run_until_complete(
                        LLMGateway.call_async(
                            messages=[{"role": "user", "content": summary_text}],
                            system_prompt=entity_prompt,
                            temperature=0.1,
                            max_tokens=2000
                        )
                    )
                    loop.close()
                    
                    if entities_json:
                        # Clean JSON block
                        cleaned_json = entities_json.replace("```json", "").replace("```", "").strip()
                        # Try object format first (new)
                        import re as _re
                        cleaned_json = _re.sub(r"<think>[\s\S]*?</think>", "", cleaned_json, flags=_re.IGNORECASE).strip()
                        obj_match = _re.search(r"\{[\s\S]*\}", cleaned_json)
                        if obj_match:
                            try:
                                parsed = json.loads(obj_match.group())
                                entities_list = parsed.get("entities", [])
                                relationships_list = parsed.get("relationships", [])
                            except json.JSONDecodeError:
                                entities_list = []
                                relationships_list = []
                                # Fallback: try array format (old)
                                arr_match = _re.search(r"\[[\s\S]*\]", cleaned_json)
                                if arr_match:
                                    try:
                                        entities_list = json.loads(arr_match.group())
                                    except json.JSONDecodeError:
                                        pass
                        else:
                            entities_list = []
                            relationships_list = []
                        
                        # Save entities and build name→id map
                        entity_name_to_id = {}
                        for ent in entities_list:
                            result = add_notebook_entity(notebook_id, ent.get("type", "Khác"), ent.get("name", ""), ent.get("context", ""))
                            if "entity_id" in result:
                                entity_name_to_id[ent.get("name", "")] = result["entity_id"]
                        
                        # Save relationships
                        for rel in relationships_list:
                            src_id = entity_name_to_id.get(rel.get("source", ""))
                            tgt_id = entity_name_to_id.get(rel.get("target", ""))
                            if src_id and tgt_id:
                                add_entity_relationship(notebook_id, src_id, tgt_id, rel.get("type", "liên quan"), rel.get("description", ""))
                        
                        print(f"[Auto-Entities] {filename}: Extracted {len(entities_list)} entities, {len(relationships_list)} relationships.")
                except Exception as e:
                    print(f"[Auto-Entities] Skipped/Error for {filename}: {e}")
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
    
    conn = get_db_conn(NOTEBOOK_DB)
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
    docs = search_notebook_docs(notebook_id, search_query, top_k=30)
    
    # 3.0 Multi-Query RAG — Nếu câu hỏi phức tạp, tạo sub-queries để tìm thêm
    if len(search_query) > 40 and len(docs) < 15:
        try:
            decompose_prompt = (
                "Phân tách câu hỏi phức tạp sau thành 2-3 câu hỏi con đơn giản hơn để tìm kiếm trong tài liệu.\n"
                "CHỈ TRẢ VỀ các câu hỏi con, mỗi câu trên 1 dòng. KHÔNG giải thích.\n"
                f"Câu hỏi: {search_query}"
            )
            sub_queries_text = await LLMGateway.call_async(
                messages=[{"role": "user", "content": decompose_prompt}],
                system_prompt="Bạn phân tách câu hỏi. Trả về mỗi câu hỏi con trên 1 dòng.",
                temperature=0.0,
                max_tokens=300
            )
            sub_queries = [q.strip().lstrip('- ').lstrip('0123456789.) ') for q in sub_queries_text.strip().split('\n') if q.strip() and len(q.strip()) > 5]
            
            if sub_queries and len(sub_queries) >= 2:
                existing_texts = {d['text'][:200] for d in docs}
                for sq in sub_queries[:3]:
                    sub_docs = search_notebook_docs(notebook_id, sq, top_k=10)
                    for sd in sub_docs:
                        if sd['text'][:200] not in existing_texts:
                            docs.append(sd)
                            existing_texts.add(sd['text'][:200])
                print(f"[Multi-Query] Decomposed into {len(sub_queries)} sub-queries, total docs: {len(docs)}")
        except Exception as e:
            print(f"[Multi-Query] Skipped: {e}")
    
    if selected_source_ids is not None:
        docs = [d for d in docs if d['source_id'] in selected_source_ids]
    
    # 3.1. FPT Cloud Rerank (bge-reranker-v2-m3) — riêng cho Notebook, không ảnh hưởng module Luật
    if docs and len(docs) > 1:
        try:
            from app.config import FPT_CLOUD_API_KEY
            if FPT_CLOUD_API_KEY:
                import httpx
                rerank_passages = [d['text'][:2000] for d in docs[:30]]
                rerank_payload = {
                    "model": "bge-reranker-v2-m3",
                    "query": search_query,
                    "documents": rerank_passages,
                    "top_n": min(15, len(rerank_passages))
                }
                async with httpx.AsyncClient() as client:
                    rerank_res = await client.post(
                        "https://mkp-api.fptcloud.com/v1/rerank",
                        json=rerank_payload,
                        headers={"Authorization": f"Bearer {FPT_CLOUD_API_KEY}", "Content-Type": "application/json"},
                        timeout=10.0
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
    SCORE_THRESHOLD = 0.01
    docs = [d for d in docs if d.get('score', 0) >= SCORE_THRESHOLD]
    
    docs = docs[:15]  # Lấy 15 đoạn trích phù hợp nhất (gấp 3x so với trước)
    
    has_relevant_docs = len(docs) > 0
    doc_context = "\n\n".join([f"--- Đoạn trích {i+1} (Từ file: {d.get('filename', 'Unknown')}, Đoạn {d.get('chunk_index', 0) + 1}) ---\n{d['text']}" for i, d in enumerate(docs)])
    
    # 4. Sinh prompt cho LLM — cho phép trả lời DÀI và CHI TIẾT
    system_prompt = (
        "Bạn là Trợ lý AI Viện Kiểm sát (NoteBook AI) — chuyên gia phân tích hồ sơ vụ án.\n"
        "Dựa vào các đoạn trích từ hồ sơ vụ án do Kiểm sát viên cung cấp, hãy trả lời câu hỏi:\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. CHỈ SỬ DỤNG thông tin từ hồ sơ được cung cấp. KHÔNG BỊA thông tin.\n"
        "2. Trả lời CHI TIẾT, ĐẦY ĐỦ và TOÀN DIỆN — phân tích sâu khi câu hỏi yêu cầu.\n"
        "3. Sử dụng Markdown format: tiêu đề (##), bullet points, bảng, in đậm cho thông tin quan trọng.\n"
        "4. BẮT BUỘC trích dẫn nguồn cụ thể: [Tên file, Đoạn X] sau mỗi thông tin.\n"
        "5. Nếu câu hỏi yêu cầu so sánh, tổng hợp, phân tích → trả lời DÀI với nhiều phần.\n"
        "6. TUYỆT ĐỐI KHÔNG LẶP LẠI nội dung đã trả lời.\n"
    )
    if has_relevant_docs:
        system_prompt += f"\n[HỒ SƠ VỤ ÁN TỪ NOTEBOOK — {len(docs)} đoạn trích]\n{doc_context}"
    else:
        system_prompt += "\n[LƯU Ý] Không tìm thấy đoạn tài liệu nào đủ liên quan đến câu hỏi trong NoteBook này. Hãy trả lời rằng bạn không tìm thấy thông tin phù hợp trong tài liệu đã tải lên. KHÔNG ĐƯỢC BỊA thông tin."
        
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
    
    # 5. Stream — gửi cả chunk và accumulated để frontend không mất text
    async def event_generator():
        full_response = ""
        try:
            async for chunk in LLMGateway.call_stream(messages=messages, system_prompt=system_prompt, max_tokens=16384):
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk, 'accumulated': full_response, 'citations': citations}, ensure_ascii=False)}\n\n"
        except Exception as e:
            err_msg = f"\n\n[Lỗi AI]: {str(e)}"
            full_response += err_msg
            yield f"data: {json.dumps({'chunk': err_msg, 'accumulated': full_response})}\n\n"
            
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
- Tạo NHIỀU node chi tiết — bản đồ tư duy phải ĐẦY ĐỦ và TOÀN DIỆN
- Mỗi nhánh chính NÊN có 3-5 node con chi tiết. Nếu thông tin nhiều, ưu tiên tạo NHIỀU node hơn là gộp vào 1 node dài
- Nếu nhánh có quá nhiều thông tin, thêm field "expandable": true vào node nhánh đó để frontend biết cần mở rộng thêm"""

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
    from app.utils.document_store import NOTEBOOK_DB, get_db_conn

    req = await request.json()
    notebook_id = req.get("notebook_id")
    selected_source_ids = req.get("selected_source_ids")
    case_title = req.get("case_title", "Vụ án")

    if not notebook_id:
        raise HTTPException(status_code=400, detail="Missing notebook_id")

    # 1. Fetch ALL chunks from SQLite (no limit)
    conn = get_db_conn(NOTEBOOK_DB)
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
        combined_text = "\n\n---\n\n".join([f"[Tài liệu ID: {c['source_id']}]\n{c['text']}" for c in all_chunks])[:60000]
        
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
                    max_tokens=1500
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
            max_tokens=16384
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


# --- Mind Map Branch Expansion ---

BRANCH_EXPAND_PROMPT = """Bạn là trợ lý pháp lý chuyên phân tích hồ sơ vụ án tại Việt Nam.

Nhiệm vụ: Đọc tài liệu và tạo DANH SÁCH CHI TIẾT các node con cho nhánh "{branch_label}" (loại: {branch_type}) trong bản đồ tư duy vụ án.

Nhánh hiện tại đã có các node con sau:
{existing_children}

Hãy bổ sung THÊM các node con MỚI mà chưa có trong danh sách trên.

QUY TẮC:
1. CHỈ trích xuất thông tin CÓ trong tài liệu, KHÔNG bịa
2. Mỗi node phải có: id (duy nhất, format: "{branch_id}_exp_1"), label (ngắn gọn <50 ký tự), type "detail"
3. Thêm description chi tiết cho mỗi node
4. BẮT BUỘC thêm sourceRef = ID tài liệu gốc
5. Trả về JSON array, mỗi phần tử là 1 node. KHÔNG trả về object bao ngoài
6. Tạo TỐI THIỂU 5 node, TỐI ĐA 15 node
7. Nếu node có thông tin phụ, tạo children bên trong node đó

Format:
[
  {{
    "id": "{branch_id}_exp_1",
    "label": "Nội dung cụ thể",
    "type": "detail",
    "description": "Chi tiết đầy đủ...",
    "sourceRef": "src_xxx",
    "children": [
      {{"id": "{branch_id}_exp_1_1", "label": "...", "type": "detail", "sourceRef": "src_xxx"}}
    ]
  }}
]

Trả về CHỈ JSON array, không markdown, không giải thích."""


@router.post("/mindmap-expand-branch")
async def expand_mindmap_branch(request: Request):
    """
    Expand a specific branch of a mind map with more detailed nodes.
    Uses RAG search (FAISS+BM25) to find relevant chunks for the branch topic.
    """
    import re

    req = await request.json()
    notebook_id = req.get("notebook_id")
    branch_id = req.get("branch_id")
    branch_label = req.get("branch_label")
    branch_type = req.get("branch_type", "detail")
    existing_children = req.get("existing_children", [])
    selected_source_ids = req.get("selected_source_ids")

    if not notebook_id or not branch_label:
        raise HTTPException(status_code=400, detail="Missing notebook_id or branch_label")

    # 1. Use EXISTING hybrid search (FAISS + BM25 + RRF) to find relevant chunks
    search_query = branch_label
    if branch_type == "parties":
        search_query = f"các bên liên quan bị can bị cáo bị hại nhân chứng {branch_label}"
    elif branch_type == "evidence":
        search_query = f"chứng cứ vật chứng lời khai giám định {branch_label}"
    elif branch_type == "crime":
        search_query = f"cấu thành tội phạm hành vi khách thể chủ thể {branch_label}"
    elif branch_type == "procedure":
        search_query = f"quy trình tố tụng khởi tố điều tra truy tố xét xử {branch_label}"
    elif branch_type == "legal":
        search_query = f"căn cứ pháp lý điều luật tình tiết {branch_label}"
    elif branch_type == "info":
        search_query = f"thông tin chung vụ án số quyết định tội danh {branch_label}"

    docs = search_notebook_docs(notebook_id, search_query, top_k=25)

    # Filter by selected sources if specified
    if selected_source_ids:
        docs = [d for d in docs if d['source_id'] in selected_source_ids]

    if not docs:
        return {"children": [], "message": "Không tìm thấy tài liệu liên quan"}

    # 2. Build context from search results
    doc_context = "\n\n".join([
        f"--- [Tài liệu: {d.get('filename', 'Unknown')}, ID: {d['source_id']}, Đoạn {d.get('chunk_index', 0)+1}] ---\n{d['text']}"
        for d in docs[:20]
    ])

    # 3. Format existing children for the prompt
    existing_text = "\n".join([f"- {c}" for c in existing_children]) if existing_children else "(Chưa có node con nào)"

    # 4. Call LLM with branch-specific prompt
    system_prompt = BRANCH_EXPAND_PROMPT.format(
        branch_label=branch_label,
        branch_type=branch_type,
        branch_id=branch_id or "branch",
        existing_children=existing_text
    )

    print(f"[MindMap Expand] Branch '{branch_label}' ({branch_type}): {len(docs)} docs found")

    try:
        content = await LLMGateway.call_async(
            messages=[{
                "role": "user",
                "content": f"Nhánh cần mở rộng: {branch_label}\n\nTài liệu liên quan ({len(docs)} đoạn trích):\n\n{doc_context}"
            }],
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=8192
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    # 5. Parse JSON response
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()

    json_match = re.search(r"\[[\s\S]*\]", content)
    if not json_match:
        # Try object wrapper
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                children = parsed.get("children", [parsed])
                return {"children": children, "source_count": len(docs)}
            except json.JSONDecodeError:
                pass
        raise HTTPException(status_code=500, detail="AI did not return valid JSON")

    try:
        children = json.loads(json_match.group())
        return {"children": children, "source_count": len(docs)}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in AI response")
class StudyToolsRequest(BaseModel):
    notebook_id: str
    tool_type: str  # "flashcards" or "quizzes"
    selected_source_ids: list[str] = []
    case_title: str = ""

FLASHCARDS_PROMPT = """Bạn là trợ lý pháp lý. Nhiệm vụ: Tạo bộ Thẻ ghi nhớ (Flashcards) từ tài liệu vụ án.
Yêu cầu:
- Trích xuất 10-15 câu hỏi và đáp án quan trọng nhất (tên nhân vật, ngày tháng, quyết định, bằng chứng cốt lõi).
- Trả về ĐÚNG 1 MẢNG JSON ARRAY. KHÔNG có text giải thích, KHÔNG có markdown, CHỈ CÓ JSON ARRAY.
Format bắt buộc:
[
  {
    "q": "Nội dung câu hỏi ngắn gọn",
    "a": "Câu trả lời ngắn gọn",
    "ref": "ID tài liệu (ví dụ: src_123)"
  }
]"""

QUIZZES_PROMPT = """Bạn là trợ lý pháp lý. Nhiệm vụ: Tạo Bài kiểm tra trắc nghiệm (Quizzes) từ tài liệu vụ án.
Yêu cầu:
- Tạo 5-10 câu hỏi trắc nghiệm kiểm tra kiến thức về vụ án.
- Mỗi câu có chính xác 4 lựa chọn (options), và 1 đáp án đúng (answerIndex từ 0 đến 3).
- Có lời giải thích (explanation).
- Trả về ĐÚNG 1 MẢNG JSON ARRAY. KHÔNG có text giải thích, KHÔNG có markdown, CHỈ CÓ JSON ARRAY.
Format bắt buộc:
[
  {
    "question": "Nội dung câu hỏi?",
    "options": ["Lựa chọn 1", "Lựa chọn 2", "Lựa chọn 3", "Lựa chọn 4"],
    "answerIndex": 0,
    "explanation": "Giải thích ngắn gọn tại sao...",
    "ref": "ID tài liệu (ví dụ: src_123)"
  }
]"""

@router.post("/study-tools-generate")
async def generate_study_tools(req: StudyToolsRequest):
    import re
    from app.database import get_db_conn
    from app.config import NOTEBOOK_DB
    
    conn = get_db_conn(NOTEBOOK_DB)
    c = conn.cursor()
    
    if req.selected_source_ids:
        placeholders = ",".join(["?"] * len(req.selected_source_ids))
        c.execute(
            f"SELECT source_id, text FROM notebook_chunks WHERE notebook_id = ? AND source_id IN ({placeholders}) ORDER BY chunk_index LIMIT 80",
            [req.notebook_id] + req.selected_source_ids
        )
    else:
        c.execute(
            "SELECT source_id, text FROM notebook_chunks WHERE notebook_id = ? ORDER BY chunk_index LIMIT 80",
            (req.notebook_id,)
        )
    
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return []

    combined_text = "\n\n---\n\n".join([f"[Tài liệu ID: {r[0]}]\n{r[1]}" for r in rows if r[1]])[:60000]
    
    system_prompt = FLASHCARDS_PROMPT if req.tool_type == "flashcards" else QUIZZES_PROMPT
    
    messages = [
        {"role": "user", "content": f"Tiêu đề vụ án: {req.case_title}\n\nNội dung tài liệu:\n{combined_text}\n\nHãy tạo {req.tool_type} dựa trên nội dung trên."}
    ]
    
    try:
        content = await LLMGateway.call_async(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=8192
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()
    json_match = re.search(r"\[[\s\S]*\]", content)
    
    if not json_match:
        raise HTTPException(status_code=500, detail="AI did not return valid JSON Array")

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


# --- Giai đoạn 2: Tự động hóa Văn bản Tố tụng & Cây Suy luận ---

class GenerateDraftRequest(BaseModel):
    notebook_id: str = None
    context_text: str = None
    doc_type: str  # "cao_trang", "luan_toi", "xet_hoi"

@router.post("/generate-draft")
async def api_generate_draft(req: GenerateDraftRequest):
    """Sinh dự thảo văn bản tố tụng qua SSE Stream"""
    entities_text = ""
    summary_text = ""
    
    if req.notebook_id:
        notebook = get_notebook(req.notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        
        # Lấy toàn bộ entities
        entities = get_notebook_entities(req.notebook_id)
        entities_text = json.dumps([{"type": e["type"], "name": e["name"], "context": e["context"]} for e in entities], ensure_ascii=False)
        
        # Lấy các summary của tài liệu
        sources = list_sources(req.notebook_id)
        summaries = [s.get("summary", "") for s in sources if s.get("summary")]
        summary_text = "\n\n".join(summaries)
    else:
        summary_text = req.context_text or ""
        
    # Xây dựng prompt tùy theo doc_type
    if req.doc_type == "cao_trang":
        prompt = (
            "Dựa trên thông tin hồ sơ dưới đây, hãy VIẾT DỰ THẢO CÁO TRẠNG (Mẫu số 156/HS). "
            "TRÌNH BÀY DƯỚI DẠNG MARKDOWN, sử dụng Markdown headers (#, ##), in đậm, in nghiêng phù hợp. "
            "Nội dung cần có các phần: Diễn biến vụ án, Lý lịch bị can, Kết luận.\n\n"
        )
    elif req.doc_type == "luan_toi":
        prompt = (
            "Dựa trên thông tin hồ sơ dưới đây, hãy VIẾT DỰ THẢO BẢN LUẬN TỘI. "
            "TRÌNH BÀY DƯỚI DẠNG MARKDOWN, sử dụng Markdown headers (#, ##), in đậm, in nghiêng phù hợp. "
            "Cần có các phần: Đánh giá chứng cứ, Nhận định về hành vi, Đề nghị hình phạt.\n\n"
        )
    else:
        prompt = (
            "Dựa trên thông tin hồ sơ dưới đây, hãy LẬP KẾ HOẠCH XÉT HỎI tại phiên tòa. "
            "Ghi rõ câu hỏi cho Bị cáo, Bị hại, và dự kiến câu trả lời hoặc điểm cần làm rõ. "
            "TRÌNH BÀY DƯỚI DẠNG MARKDOWN.\n\n"
        )
        
    prompt += f"--- THỰC THỂ ---\n{entities_text}\n\n--- HỒ SƠ/TÓM TẮT ---\n{summary_text}"
    
    async def event_generator():
        try:
            async for token in LLMGateway.call_stream([{"role": "user", "content": prompt}], "Bạn là Kiểm sát viên dày dạn kinh nghiệm. Hãy soạn thảo văn bản chính xác, chuyên nghiệp."):
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'status': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")


class AnalyzeReasoningRequest(BaseModel):
    notebook_id: str
    toi_danh: str

@router.post("/analyze-reasoning")
async def api_analyze_reasoning(req: AnalyzeReasoningRequest):
    """Phân tích cấu thành tội phạm bằng LLM thật"""
    import re

    system_prompt = (
        "Bạn là chuyên gia pháp lý Việt Nam. Người dùng bôi đen một đoạn text từ hồ sơ vụ án. "
        "Hãy phân tích pháp lý cho đoạn text đó.\n\n"
        "Trả về JSON với format:\n"
        '{\n'
        '  "toi_danh": "Tội danh / Nhận định chính",\n'
        '  "nhan_dinh": "Nhận định pháp lý ngắn gọn",\n'
        '  "dieu": "Số điều luật áp dụng (nếu có)",\n'
        '  "khoan": "Số khoản (nếu có)",\n'
        '  "hinh_phat": "Khung hình phạt (nếu là tội phạm)",\n'
        '  "cau_thanh": ["Yếu tố 1", "Yếu tố 2", ...]\n'
        '}\n\n'
        "NẾU không phải tội phạm hoặc không xác định được, vẫn trả về JSON với nhận định phù hợp.\n"
        "CHỈ TRẢ VỀ JSON, KHÔNG giải thích thêm."
    )

    try:
        result = await LLMGateway.call_async(
            messages=[{"role": "user", "content": f"Đoạn text cần phân tích pháp lý:\n\n\"{req.toi_danh}\""}],
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1000
        )

        result = re.sub(r"<think>[\s\S]*?</think>", "", result, flags=re.IGNORECASE).strip()
        json_match = re.search(r"\{[\s\S]*\}", result)
        if json_match:
            parsed = json.loads(json_match.group())
            return parsed
        return {"toi_danh": req.toi_danh, "nhan_dinh": result, "cau_thanh": []}
    except Exception as e:
        return {
            "error": f"Lỗi phân tích: {str(e)}",
            "toi_danh": req.toi_danh,
            "nhan_dinh": "Không thể phân tích do lỗi kết nối AI",
            "cau_thanh": []
        }
