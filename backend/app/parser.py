import io
import pypdf
from typing import Tuple


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """
    Extract raw text from uploaded .txt, .md, or .pdf files.
    """
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    if ext in ['txt', 'md']:
        try:
            return file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            return file_bytes.decode('latin-1', errors='replace')

    elif ext == 'pdf':
        try:
            pdf_file = io.BytesIO(file_bytes)
            reader = pypdf.PdfReader(pdf_file)
            extracted_text = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    extracted_text.append(page_text)
            
            full_text = "\n\n".join(extracted_text).strip()
            if not full_text:
                return f"[PDF file '{filename}' contained no readable text or scanned pages without OCR]"
            return full_text
        except Exception as e:
            raise ValueError(f"Failed to parse PDF file '{filename}': {str(e)}")

    else:
        # Fallback: attempt UTF-8 decode for text-like formats
        try:
            return file_bytes.decode('utf-8')
        except Exception:
            raise ValueError(f"Unsupported file extension '.{ext}'. Supported formats are .txt, .md, and .pdf.")
