from fastapi import FastAPI, UploadFile, File, Form
import os
import uuid

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docs",
    "image/jpeg": "images",
    "image/png": "images",
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}


@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    email: str = Form(...),
    phone: str = Form(...),
    date: str = Form(...),
    username: str = Form(...),
    address: str = Form(...),
    age: int = Form(...),
    gender: str = Form(...),
    description: str = Form(None)  # optional field
):
    # --- Validation ---
    if file.content_type not in ALLOWED_TYPES:
        return {"error": "File type not allowed! Upload PDF, DOCX, JPG, or PNG."}

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        return {"error": "File too large! Max size is 5 MB."}

    # --- Save the file ---
    folder_name = ALLOWED_TYPES[file.content_type]
    folder_path = os.path.join(UPLOAD_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    unique_id = str(uuid.uuid4())
    save_path = os.path.join(folder_path, f"{unique_id}_{file.filename}")

    with open(save_path, "wb") as buffer:
        buffer.write(contents)

    # --- Response ---
    return {
        "message": "File uploaded successfully!",
        "filename": file.filename,
        "saved_as": f"{unique_id}_{file.filename}",
        "file_type": file.content_type,
        "file_size": len(contents),
        "saved_in": folder_name,
        "full_path": save_path,
        "email": email,
        "phone": phone,
        "date": date,
        "username": username,
        "address": address,
        "age": age,
        "gender": gender,
        "description": description
    }
