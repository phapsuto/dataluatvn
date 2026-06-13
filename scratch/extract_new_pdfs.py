import os
import sys

def extract_pdf(pdf_path, txt_path):
    print(f"Extracting {pdf_path} to {txt_path}...")
    
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} does not exist.")
        return False
        
    extracted = False
    
    # Try PyMuPDF (fitz)
    if not extracted:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            text = []
            for page in doc:
                text.append(page.get_text())
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n\n=== PAGE BOUNDARY ===\n\n".join(text))
            print("Successfully extracted using PyMuPDF (fitz)!")
            extracted = True
        except ImportError:
            pass
        except Exception as e:
            print(f"fitz extraction failed: {e}")
            
    # Try pypdf
    if not extracted:
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            text = []
            for page in reader.pages:
                text.append(page.extract_text() or "")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n\n=== PAGE BOUNDARY ===\n\n".join(text))
            print("Successfully extracted using pypdf!")
            extracted = True
        except ImportError:
            pass
        except Exception as e:
            print(f"pypdf extraction failed: {e}")

    # Try pdfplumber
    if not extracted:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                text = []
                for page in pdf.pages:
                    text.append(page.extract_text() or "")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n\n=== PAGE BOUNDARY ===\n\n".join(text))
            print("Successfully extracted using pdfplumber!")
            extracted = True
        except ImportError:
            pass
        except Exception as e:
            print(f"pdfplumber extraction failed: {e}")

    # Try pdfminer
    if not extracted:
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(pdf_path)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            print("Successfully extracted using pdfminer!")
            extracted = True
        except ImportError:
            pass
        except Exception as e:
            print(f"pdfminer extraction failed: {e}")
            
    if not extracted:
        print("Error: No PDF parsing library could be imported or extract successfully.")
        return False
    return True

if __name__ == "__main__":
    pdf1 = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/ai study vnlaw/Hướng Dẫn Nghiên Cứu Luật Học Chuẩn.pdf"
    pdf2 = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/ai study vnlaw/PPNC_Le Thi Hong Nhung.pdf"
    
    out_dir = "/Users/tonguyen/.gemini/antigravity-ide/brain/d97ddf69-2480-422e-91ae-ad6271b61690/scratch"
    os.makedirs(out_dir, exist_ok=True)
    
    txt1 = os.path.join(out_dir, "huong_dan_chuan.txt")
    txt2 = os.path.join(out_dir, "ppnc_hong_nhung.txt")
    
    extract_pdf(pdf1, txt1)
    extract_pdf(pdf2, txt2)
