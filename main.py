from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import uuid

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(
    title="FastAPI Upload API",
    description="Day1 - Day7 complete",
    version="1.0"
)

# -----------------------------
# Database Setup (SQLite)
# -----------------------------
DATABASE_URL = "sqlite:///./uploads.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------
# Model (Table)
# -----------------------------
class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    saved_as = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    saved_in = Column(String, nullable=False)
    full_path = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    date = Column(String, nullable=False)
    username = Column(String, nullable=False)
    address = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)
    description = Column(String, nullable=True)

# Create tables
Base.metadata.create_all(bind=engine)

# -----------------------------
# File upload setup
# -----------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docs",
    "image/jpeg": "images",
    "image/png": "images",
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def read_root():
    return {"message": "Hello FastAPI - Day1 to Day7 complete!"}


# -----------------------------
# Day1-Day4 Upload Route
# -----------------------------
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
    description: str = Form(None),
):
    # --- Day 2: Validate file type ---
    if file.content_type not in ALLOWED_TYPES:
        return {"error": "File type not allowed! Upload PDF, DOCX, JPG, or PNG."}

    contents = await file.read()

    # --- Day 2: Validate file size ---
    if len(contents) > MAX_FILE_SIZE:
        return {"error": "File too large! Max size is 5 MB."}

    # --- Day 3: Save file locally ---
    folder_name = ALLOWED_TYPES[file.content_type]
    folder_path = os.path.join(UPLOAD_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    unique_id = str(uuid.uuid4())
    saved_filename = f"{unique_id}_{file.filename}"
    save_path = os.path.join(folder_path, saved_filename)

    with open(save_path, "wb") as buffer:
        buffer.write(contents)

    # --- Day 4: Save metadata to DB ---
    db = SessionLocal()
    new_upload = Upload(
        filename=file.filename,
        saved_as=saved_filename,
        file_type=file.content_type,
        file_size=len(contents),
        saved_in=folder_name,
        full_path=save_path,
        email=email,
        phone=phone,
        date=date,
        username=username,
        address=address,
        age=age,
        gender=gender,
        description=description,
    )
    db.add(new_upload)
    db.commit()
    db.refresh(new_upload)
    db.close()

    return {"message": "File uploaded & saved to DB successfully!", "db_id": new_upload.id}


# -----------------------------
# Day5 - Retrieve All Uploads
# -----------------------------
@app.get("/history/")
def get_all_uploads():
    db = SessionLocal()
    uploads = db.query(Upload).all()
    db.close()
    return uploads


# -----------------------------
# Day5 - Retrieve Single Upload
# -----------------------------
@app.get("/history/{upload_id}")
def get_upload(upload_id: int):
    db = SessionLocal()
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    db.close()

    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


# -----------------------------
# Day6 - Download File
# -----------------------------
@app.get("/download/{upload_id}")
def download_file(upload_id: int):
    db = SessionLocal()
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    db.close()

    if not upload:
        raise HTTPException(status_code=404, detail="File not found in DB")

    if not os.path.exists(upload.full_path):
        raise HTTPException(status_code=404, detail="File missing on server")

    return FileResponse(
        path=upload.full_path,
        filename=upload.filename,
        media_type=upload.file_type
    )


# -----------------------------
# Day7 - Update Metadata / Replace File
# -----------------------------
@app.put("/update/{upload_id}")
async def update_upload(
    upload_id: int,
    email: str = Form(None),
    phone: str = Form(None),
    date: str = Form(None),
    username: str = Form(None),
    address: str = Form(None),
    age: int = Form(None),
    gender: str = Form(None),
    description: str = Form(None),
    file: UploadFile = File(None),
):
    db = SessionLocal()
    upload = db.query(Upload).filter(Upload.id == upload_id).first()

    if not upload:
        db.close()
        raise HTTPException(status_code=404, detail="Upload not found")

    # Update metadata if provided
    if email: upload.email = email
    if phone: upload.phone = phone
    if date: upload.date = date
    if username: upload.username = username
    if address: upload.address = address
    if age: upload.age = age
    if gender: upload.gender = gender
    if description: upload.description = description

    # If new file uploaded → replace old one
    if file:
        if file.content_type not in ALLOWED_TYPES:
            db.close()
            raise HTTPException(status_code=400, detail="File type not allowed")

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            db.close()
            raise HTTPException(status_code=400, detail="File too large! Max size 5MB")

        # delete old file
        if os.path.exists(upload.full_path):
            os.remove(upload.full_path)

        # save new file
        folder_name = ALLOWED_TYPES[file.content_type]
        folder_path = os.path.join(UPLOAD_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        unique_id = str(uuid.uuid4())
        saved_filename = f"{unique_id}_{file.filename}"
        save_path = os.path.join(folder_path, saved_filename)

        with open(save_path, "wb") as buffer:
            buffer.write(contents)

        # update DB fields
        upload.filename = file.filename
        upload.saved_as = saved_filename
        upload.file_type = file.content_type
        upload.file_size = len(contents)
        upload.saved_in = folder_name
        upload.full_path = save_path

    db.commit()
    db.refresh(upload)
    db.close()

    return {"message": "Upload updated successfully", "upload_id": upload.id}


# -----------------------------
# Day7 - Delete Upload
# -----------------------------
@app.delete("/delete/{upload_id}")
def delete_upload(upload_id: int):
    db = SessionLocal()
    upload = db.query(Upload).filter(Upload.id == upload_id).first()

    if not upload:
        db.close()
        raise HTTPException(status_code=404, detail="Upload not found")

    # Delete file from disk
    if os.path.exists(upload.full_path):
        os.remove(upload.full_path)

    # Delete record from DB
    db.delete(upload)
    db.commit()
    db.close()

    return {"message": "Upload deleted successfully", "upload_id": upload_id}
