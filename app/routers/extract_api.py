from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import asyncio
import re
import uuid

from app.utils.document_store import list_sources, get_source_text, save_notebook_extraction, get_notebook_extraction
from app.utils.llm_gateway import LLMGateway

router = APIRouter()

# In-memory job store
# Format: { "job_id": { "status": "processing" | "success" | "error", "progress": "string", "data": dict, "error": str } }
JOBS = {}

class ExtractRequest(BaseModel):
    notebook_id: str
    source_ids: Optional[List[str]] = None
    query: Optional[str] = None
    extract_types: Optional[List[str]] = None

async def call_llm_extract(text: str, filename: str, query: str = None) -> dict:
    prompt = f"""
Hãy TRÍCH XUẤT tất cả thông tin quan trọng từ phần tài liệu sau.
Tên tài liệu: {filename}

PHÂN LOẠI CẦN TRÍCH XUẤT:
- tables: Các bảng dữ liệu, dòng tiền, bảng kê tài sản.
- quotes: Các câu nói, lời khai quan trọng.
- metrics: Các con số, ngày tháng, tỷ lệ, số tiền.
- decisions: Quyết định tố tụng, kết luận.

Output JSON format bắt buộc:
{{
  "tables": [
    {{ "title": "Tên bảng", "columns": ["Cột 1", "Cột 2"], "rows": [["Dòng 1", "Dòng 2"]], "source_file": "{filename}", "page_number": 1 }}
  ],
  "quotes": [
    {{ "content": "Nội dung", "person": "Người nói (nếu có)", "context": "Ngữ cảnh", "source_file": "{filename}" }}
  ],
  "metrics": [
    {{ "label": "Tên số liệu", "value": "Giá trị", "source_file": "{filename}" }}
  ],
  "decisions": [
    {{ "content": "Nội dung quyết định", "authority": "Cơ quan/Người ra quyết định", "source_file": "{filename}" }}
  ]
}}

NẾU BẠN KHÔNG TÌM THẤY DỮ LIỆU, HÃY TRẢ VỀ CÁC MẢNG RỖNG: [].
CHỈ TRẢ VỀ JSON, KHÔNG GIẢI THÍCH THÊM.
"""
    if query:
        prompt += f"\nYÊU CẦU ĐẶC BIỆT (chỉ lấy các thông tin liên quan): {query}"
        
    user_msg = f"--- TÀI LIỆU ---\n{text}"
    
    try:
        result = await LLMGateway.call_async(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=prompt,
            temperature=0.1,
            max_tokens=2500
        )
        
        result = re.sub(r"<think>[\s\S]*?</think>", "", result, flags=re.IGNORECASE).strip()
        json_match = re.search(r"\{[\s\S]*\}", result)
        
        if json_match:
            json_str = json_match.group(0)
            return json.loads(json_str)
        else:
            return {"tables": [], "quotes": [], "metrics": [], "decisions": []}
    except Exception as e:
        print("Extract Error:", e)
        return {"tables": [], "quotes": [], "metrics": [], "decisions": []}

async def process_extraction_job(job_id: str, sources: list, req_query: str):
    try:
        all_results = {"tables": [], "quotes": [], "metrics": [], "decisions": []}
        tasks = []
        
        JOBS[job_id]["progress"] = "Đang chuẩn bị dữ liệu tài liệu..."
        
        for src in sources:
            text = get_source_text(src['id'])
            if not text:
                continue
                
            chunk_size = 30000 
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i+chunk_size]
                tasks.append({"func": call_llm_extract, "args": (chunk, src['filename'], req_query)})
                
        total_tasks = len(tasks)
        if total_tasks == 0:
            JOBS[job_id]["status"] = "success"
            JOBS[job_id]["progress"] = "Hoàn thành."
            JOBS[job_id]["data"] = all_results
            return

        batch_size = 3
        completed_tasks = 0
        
        for i in range(0, total_tasks, batch_size):
            batch_tasks = tasks[i:i+batch_size]
            JOBS[job_id]["progress"] = f"Đang phân tích phần {completed_tasks + 1} đến {min(completed_tasks + batch_size, total_tasks)} trên tổng số {total_tasks} phần..."
            
            # Execute batch
            awaitables = [t["func"](*t["args"]) for t in batch_tasks]
            results = await asyncio.gather(*awaitables)
            
            for r in results:
                all_results["tables"].extend(r.get("tables", []))
                all_results["quotes"].extend(r.get("quotes", []))
                all_results["metrics"].extend(r.get("metrics", []))
                all_results["decisions"].extend(r.get("decisions", []))
                
            completed_tasks += len(batch_tasks)
            
            if completed_tasks < total_tasks:
                await asyncio.sleep(1)
                
        JOBS[job_id]["status"] = "success"
        JOBS[job_id]["progress"] = "Hoàn thành."
        JOBS[job_id]["data"] = all_results
        
        # Save to database
        save_notebook_extraction(notebook_id=sources[0]['notebook_id'], data_json=json.dumps(all_results))
        
    except Exception as e:
        print("Job Exception:", e)
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)


@router.post("/extract")
async def api_extract_notebook(req: ExtractRequest):
    sources = list_sources(req.notebook_id)
    if req.source_ids:
        sources = [s for s in sources if s['id'] in req.source_ids]
        
    if not sources:
        raise HTTPException(status_code=400, detail="Không tìm thấy tài liệu nào.")
        
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "processing",
        "progress": "Khởi tạo tiến trình...",
        "data": None,
        "error": None
    }
    
    # Bắn chạy ngầm
    asyncio.create_task(process_extraction_job(job_id, sources, req.query))
    
    return {"status": "success", "job_id": job_id}

@router.get("/extract/{job_id}")
async def api_get_extract_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job không tồn tại.")
        
    return JOBS[job_id]

@router.get("/extract/saved/{notebook_id}")
async def api_get_saved_extraction(notebook_id: str):
    data_str = get_notebook_extraction(notebook_id)
    if data_str:
        try:
            data = json.loads(data_str)
            return {"status": "success", "data": data}
        except:
            pass
    return {"status": "success", "data": None}
