from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
import os, uuid, re, time

# Optional deps
try: import pdfplumber
except: pdfplumber = None
try: import docx
except: docx = None
try:
    from PIL import Image
    import pytesseract
except: Image, pytesseract = None, None
try:
    import spacy
    nlp = None
except: spacy, nlp = None, None

# =========================
# App + DB setup
# =========================
app = FastAPI(title="Metadata Extraction API", version="1.0 (Day 1–19)")

DATABASE_URL = "sqlite:///./uploads.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# =========================
# Models
# =========================
class Upload(Base):
    __tablename__ = "uploads"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    saved_as = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    saved_in = Column(String, nullable=False)
    full_path = Column(String, nullable=False)
    # Metadata
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    date = Column(String, nullable=False)
    username = Column(String, nullable=False)
    address = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)
    description = Column(String, nullable=True)
    # Day 13–14
    category = Column(String, nullable=False)
    version = Column(Integer, default=1)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="viewer")

class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Share(Base):
    __tablename__ = "shares"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("uploads.id"), nullable=False)
    shared_with = Column(String, nullable=False)
    permission = Column(String, default="view")
    shared_file = relationship("Upload")

class ExtractionResult(Base):
    __tablename__ = "extraction_results"
    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("uploads.id"), nullable=False)
    metadata_json = Column(Text, nullable=False)
    pages = Column(Integer, default=0)
    time_taken = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    upload = relationship("Upload")

# ✅ DB init
Base.metadata.create_all(bind=engine)

# =========================
# Config + Auth helpers
# =========================
UPLOAD_DIR = "uploads"; os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docs",
    "image/jpeg": "images", "image/png": "images"}
MAX_FILE_SIZE = 5*1024*1024

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY, ALGORITHM = "mysecretkey123", "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(p): return pwd_context.hash(p)
def verify_password(p,h): return pwd_context.verify(p,h)
def create_access_token(data: dict, expires: timedelta=None):
    expire = datetime.utcnow() + (expires or timedelta(minutes=30))
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str=Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"username": payload["sub"], "role": payload["role"]}
    except: raise HTTPException(401,"Invalid token")

def require_role(roles:list):
    def checker(u=Depends(get_current_user)):
        if u["role"] not in roles: raise HTTPException(403,"Forbidden")
        return u
    return checker

def log_action(username, action):
    db=SessionLocal(); db.add(Log(username=username, action=action)); db.commit(); db.close()

def viewer_has_permission(db, file_id, viewer, required="view"):
    sh=db.query(Share).filter(Share.file_id==file_id,Share.shared_with==viewer).first()
    if not sh: return False
    return sh.permission=="edit" if required=="edit" else sh.permission in ("view","edit")

# =========================
# Extraction helpers (Day 17–18)
# =========================
_email_re=re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_phone_re=re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{6,10}")
_date_re=re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b")

def normalize_phone(p): return "+91-"+re.sub(r"\D","",p) if len(re.sub(r"\D","",p))==10 else p
def normalize_date(d):
    try:
        if "/" in d: dd,mm,yy=d.split("/"); return f"{yy}-{mm}-{dd}"
        if "-" in d and len(d.split("-")[0])!=4: dd,mm,yy=d.split("-"); return f"{yy}-{mm}-{dd}"
    except: return d; return d

def extract_text(path, ftype):
    if ftype=="application/pdf" and pdfplumber:
        with pdfplumber.open(path) as pdf: return "\n".join([p.extract_text() or "" for p in pdf.pages]),len(pdf.pages)
    if ftype.endswith("document") and docx: d=docx.Document(path); return "\n".join([p.text for p in d.paragraphs]),1
    if ftype.startswith("image") and pytesseract and Image: return pytesseract.image_to_string(Image.open(path)),1
    return "",0

def run_regex(text):
    return {"emails":list({e for e in _email_re.findall(text)}),
            "phones":list({normalize_phone(p) for p in _phone_re.findall(text)}),
            "dates":list({normalize_date(d) for d in _date_re.findall(text)})}

def run_ner(text):
    global nlp
    if not spacy: return {"names":[],"organizations":[],"locations":[]}
    if not nlp:
        try: nlp=spacy.load("en_core_web_sm")
        except: return {"names":[],"organizations":[],"locations":[]}
    doc=nlp(text)
    return {"names":list({e.text for e in doc.ents if e.label_=="PERSON"}),
            "organizations":list({e.text for e in doc.ents if e.label_=="ORG"}),
            "locations":list({e.text for e in doc.ents if e.label_ in ("GPE","LOC")})}

# =========================
# Routes Day 1–19
# =========================
@app.get("/")
def root(): return {"message":"Hello — Days 1 to 19 complete"}

# Day 19: Health
from sqlalchemy import text

@app.get("/health")
def health_check():
    services = {}
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))   # ✅ FIXED
        db.close()
        services["database"] = "up"
    except Exception as e:
        services["database"] = f"down ({str(e)})"

    services["extraction"] = "available" if (pdfplumber or docx or pytesseract) else "unavailable"
    services["ml"] = "available" if spacy else "unavailable"

    return {
        "status": "ok" if services["database"].startswith("up") else "error",
        "services": services,
        "timestamp": datetime.utcnow().isoformat()
    }


# Day 9: Auth
@app.post("/signup/")
def signup(username:str=Form(...), password:str=Form(...), role:str=Form("viewer")):
    db=SessionLocal()
    if db.query(User).filter(User.username==username).first(): db.close(); raise HTTPException(400,"Exists")
    u=User(username=username,hashed_password=get_password_hash(password),role=role); db.add(u); db.commit(); db.refresh(u); db.close()
    return {"username":u.username,"role":u.role}

@app.post("/login/")
def login(username:str=Form(...), password:str=Form(...)):
    db=SessionLocal(); u=db.query(User).filter(User.username==username).first(); db.close()
    if not u or not verify_password(password,u.hashed_password): raise HTTPException(401,"Bad creds")
    token=create_access_token({"sub":u.username,"role":u.role}); log_action(u.username,"Login")
    return {"access_token":token,"token_type":"bearer","role":u.role}

# Day 1–4 + 10 + 13 + 14: Upload
@app.post("/upload/")
async def upload(file:UploadFile=File(...), email:str=Form(...), phone:str=Form(...), date:str=Form(...),
                 username:str=Form(...), address:str=Form(...), age:int=Form(...), gender:str=Form(...),
                 category:str=Form(...), description:str=Form(None), user=Depends(require_role(["admin","editor"]))):
    contents=await file.read()
    if file.content_type not in ALLOWED_TYPES: raise HTTPException(400,"Type not allowed")
    if len(contents)>MAX_FILE_SIZE: raise HTTPException(400,"Too large")
    folder=ALLOWED_TYPES[file.content_type]; os.makedirs(os.path.join(UPLOAD_DIR,folder),exist_ok=True)
    db=SessionLocal()
    last=db.query(Upload).filter(Upload.filename==file.filename,Upload.username==username).order_by(Upload.version.desc()).first()
    version=(last.version+1) if last else 1
    saved=f"{uuid.uuid4()}_v{version}_{file.filename}"; path=os.path.join(UPLOAD_DIR,folder,saved)
    with open(path,"wb") as f: f.write(contents)
    rec=Upload(filename=file.filename,saved_as=saved,file_type=file.content_type,file_size=len(contents),
               saved_in=folder,full_path=path,email=email,phone=phone,date=date,username=username,
               address=address,age=age,gender=gender,description=description or "",category=category,version=version)
    db.add(rec); db.commit(); db.refresh(rec); db.close()
    return {"file_id":rec.id,"version":version}

# Day 15–16: Share
@app.post("/share/{file_id}")
def share(file_id:int, shared_with:str=Form(...), permission:str=Form("view"),
          user=Depends(require_role(["admin","editor"]))):
    db=SessionLocal(); u=db.query(Upload).filter(Upload.id==file_id).first()
    if not u: db.close(); raise HTTPException(404,"Not found")
    ex=db.query(Share).filter(Share.file_id==file_id,Share.shared_with==shared_with).first()
    if ex: ex.permission=permission
    else: db.add(Share(file_id=file_id,shared_with=shared_with,permission=permission))
    db.commit(); db.close(); return {"msg":"Shared"}

# Day 12: History
@app.get("/history/")
def history(skip:int=0, limit:int=10, user=Depends(get_current_user)):
    db=SessionLocal(); q=db.query(Upload)
    if user["role"]=="viewer": q=q.join(Share,Share.file_id==Upload.id).filter(Share.shared_with==user["username"])
    out=q.offset(skip).limit(limit).all(); db.close()
    return [{"id":x.id,"file":x.filename,"category":x.category} for x in out]

# Day 5: Single
@app.get("/history/{id}")
def get_upload(id:int, user=Depends(get_current_user)):
    db=SessionLocal(); u=db.query(Upload).filter(Upload.id==id).first()
    if not u: db.close(); raise HTTPException(404,"Not found")
    if user["role"]=="viewer" and not viewer_has_permission(db,id,user["username"]): raise HTTPException(403,"Not shared")
    db.close(); return {"id":u.id,"filename":u.filename}

# Day 6: Download
@app.get("/download/{id}")
def download(id:int, user=Depends(get_current_user)):
    db=SessionLocal(); u=db.query(Upload).filter(Upload.id==id).first()
    if not u: raise HTTPException(404,"Not found")
    if user["role"]=="viewer" and not viewer_has_permission(db,id,user["username"]): raise HTTPException(403,"Not shared")
    return FileResponse(u.full_path,filename=u.filename,media_type=u.file_type)

# Day 7: Update + Delete
@app.put("/update/{id}")
async def update_upload(id:int, email:str=Form(None), phone:str=Form(None), date:str=Form(None), username_:str=Form(None),
                        address:str=Form(None), age:int=Form(None), gender:str=Form(None), category:str=Form(None),
                        description:str=Form(None), file:UploadFile=File(None), user=Depends(get_current_user)):
    db=SessionLocal(); u=db.query(Upload).filter(Upload.id==id).first()
    if not u: db.close(); raise HTTPException(404,"Not found")
    can_edit=user["role"] in ("admin","editor") or (user["role"]=="viewer" and viewer_has_permission(db,id,user["username"],"edit"))
    if not can_edit: db.close(); raise HTTPException(403,"No edit permission")
    if email: u.email=email
    if phone: u.phone=phone
    if date: u.date=date
    if username_: u.username=username_
    if address: u.address=address
    if age: u.age=age
    if gender: u.gender=gender
    if category: u.category=category
    if description: u.description=description
    if file:
        contents=await file.read(); folder=ALLOWED_TYPES[file.content_type]
        saved=f"{uuid.uuid4()}_{file.filename}"; path=os.path.join(UPLOAD_DIR,folder,saved)
        with open(path,"wb") as f: f.write(contents)
        u.filename,file.saved_as,u.full_path=file.filename,saved,path
    db.commit(); db.refresh(u); db.close(); return {"msg":"Updated","id":u.id}

@app.delete("/delete/{id}")
def delete_upload(id:int, user=Depends(require_role(["admin"]))):
    db=SessionLocal(); u=db.query(Upload).filter(Upload.id==id).first()
    if not u: raise HTTPException(404,"Not found")
    if os.path.exists(u.full_path): os.remove(u.full_path)
    db.delete(u); db.commit(); db.close(); return {"msg":"Deleted"}

# Day 8: Search
@app.get("/search/")
def search(filename:str=Query(None), email:str=Query(None), category:str=Query(None), user=Depends(get_current_user)):
    db=SessionLocal(); q=db.query(Upload)
    if user["role"]=="viewer": q=q.join(Share,Share.file_id==Upload.id).filter(Share.shared_with==user["username"])
    if filename: q=q.filter(Upload.filename.contains(filename))
    if email: q=q.filter(Upload.email.contains(email))
    if category: q=q.filter(Upload.category==category)
    res=q.all(); db.close(); return [u.filename for u in res]

# Day 11: Logs
@app.get("/logs/")
def get_logs(user=Depends(require_role(["admin"]))):
    db=SessionLocal(); logs=db.query(Log).order_by(Log.timestamp.desc()).all(); db.close()
    return [{"user":l.username,"action":l.action,"time":l.timestamp} for l in logs]

# Day 17–18: Processing
@app.post("/process/{id}")
def process(id:int, user=Depends(get_current_user)):
    db=SessionLocal(); u=db.query(Upload).filter(Upload.id==id).first()
    if not u: db.close(); raise HTTPException(404,"File not found")
    try:
        start=time.time(); text,pages=extract_text(u.full_path,u.file_type); regex=run_regex(text); ner=run_ner(text)
        metadata={**regex,**ner}
        result=ExtractionResult(upload_id=id,metadata_json=str(metadata),pages=pages,time_taken=f"{time.time()-start:.2f}s")
        db.add(result); db.commit()
        response={"file_id":id,"metadata":metadata,"processing_stats":{"pages":result.pages,"time_taken":result.time_taken}}
        db.close(); return response
    except Exception as e: db.close(); raise HTTPException(500,f"Processing failed: {str(e)}")
