# =========================================================
# AI ASSIGNMENT DUPLICATE CHECKER - MAIN.PY
# =========================================================
import os
import re
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from fastapi import (
    Body,
    FastAPI,
    Depends,
    Form,
    HTTPException,
    UploadFile,
    File,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, EmailStr

from sqlalchemy import text
from sqlalchemy.orm import Session

from PIL import Image
import pytesseract
from pypdf import PdfReader

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from jose import jwt, JWTError

from app.database import Base, engine, SessionLocal
from app.models import Assignment, Classroom, ClassroomMembership, SignupVerification, User
from app.auth import hash_password, verify_password


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="AI Assignment Duplicate Checker",
    version="1.0.0",
    description="Backend API for handwritten assignment duplicate detection"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# DATABASE
# =========================================================

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# =========================================================
# JWT CONFIGURATION
# =========================================================

SECRET_KEY = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_KEY_123456789"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60


# =========================================================
# SECURITY
# =========================================================

security = HTTPBearer()


# =========================================================
# DIRECTORIES
# =========================================================

UPLOAD_DIR = Path("uploads")

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# ALLOWED FILE TYPES
# =========================================================

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".webp",
    ".pdf",
}

SUBJECTS = [
    "Mathematics",
    "Physics",
    "Chemistry",
    "Computer Science",
    "English",
    "Biology",
    "History",
    "Economics",
]

OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 5


def allow_dev_otp() -> bool:
    return os.getenv("ALLOW_DEV_OTP", "true").lower() == "true"


def send_signup_otp(email: str, otp: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_username or "")

    if not all((smtp_host, smtp_username, smtp_password, sender_email)):
        if allow_dev_otp():
            return False
        raise RuntimeError("Email service is not configured")

    message = EmailMessage()
    message["Subject"] = "Assignment Checker email verification code"
    message["From"] = sender_email
    message["To"] = email
    message.set_content(
        f"Your Assignment Checker verification code is {otp}. "
        f"It expires in {OTP_EXPIRY_MINUTES} minutes."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(message)

    return True


def get_organization_from_email(email: str) -> str:
    if not email or "@" not in email:
        return ""

    domain = email.split("@")[-1].lower().strip()
    if not domain:
        return ""

    return domain


def is_college_email(email: str) -> bool:
    if not email or "@" not in email:
        return False

    domain = email.split("@")[-1].lower().strip()
    if not domain or domain in {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}:
        return False

    allowed_markers = (
        "college",
        "edu",
        "ac.",
        "university",
        "campus",
        ".edu.",
        ".edu",
        ".org",
        "org",
    )

    if any(marker in domain for marker in allowed_markers):
        return True

    if domain.count(".") >= 2 and not domain.startswith("mail"):
        return True

    return False


# =========================================================
# PYDANTIC MODELS
# =========================================================

class AdminCreate(BaseModel):

    name: str

    email: EmailStr

    password: str

    organization: str | None = None


class LoginRequest(BaseModel):

    email: EmailStr

    password: str


class SignupRequest(BaseModel):

    name: str

    email: EmailStr

    password: str

    role: str | None = "student"

    subject: str | None = None


class VerifySignupRequest(BaseModel):

    email: EmailStr

    otp: str


class CreateClassroomRequest(BaseModel):

    name: str
    subject: str
    join_code: str | None = None


class JoinClassroomRequest(BaseModel):

    join_code: str


class TeacherAssignStudentRequest(BaseModel):

    student_email: EmailStr
    classroom_id: int


# =========================================================
# JWT TOKEN
# =========================================================

def create_access_token(
    user_id: int,
    role: str
):

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        user_id = int(user_id)

    except (JWTError, ValueError):

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    if not user.is_active:

        raise HTTPException(
            status_code=403,
            detail="Account is disabled"
        )

    return user


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return {
        "message": "AI Assignment Duplicate Checker API is running",
        "version": "1.0.0",
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "subject": current_user.subject,
        "organization": current_user.organization,
    }


# =========================================================
# CREATE SUPER ADMIN
# =========================================================

@app.post(
    "/admin/create",
    responses={
        200: {"description": "Super admin created successfully"},
        400: {"description": "Email already registered or invalid payload"},
        422: {"description": "Validation error"},
    },
)
def create_super_admin(
    admin: AdminCreate,
    db: Session = Depends(get_db),
):

    normalized_email = str(admin.email).strip().lower()

    # -----------------------------------------------------
    # Check if email already exists
    # -----------------------------------------------------

    existing_user = db.query(User).filter(
        User.email == normalized_email
    ).first()

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="User with this email already exists"
        )

    # -----------------------------------------------------
    # Create admin
    # -----------------------------------------------------

    organization = (admin.organization or get_organization_from_email(normalized_email) or "").strip()

    new_admin = User(
        name=admin.name.strip(),
        email=normalized_email,
        password_hash=hash_password(admin.password),
        role="super_admin",
        organization=organization or None,
        is_active=True,
    )

    db.add(new_admin)

    db.commit()

    db.refresh(new_admin)

    return {

        "message": "Super Admin created successfully",

        "admin_id": new_admin.id,

        "name": new_admin.name,

        "email": new_admin.email,

        "organization": new_admin.organization,

        "role": new_admin.role,

    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/login")
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):

    email = str(login_data.email).strip().lower()
    password = login_data.password

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if user.role == "student" and not is_college_email(email):
        raise HTTPException(
            status_code=403,
            detail="Student accounts must use a college email address"
        )

    try:
        password_valid = verify_password(
            password,
            user.password_hash
        )
    except Exception:
        password_valid = False

    if not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is disabled"
        )

    if not user.organization:
        user.organization = get_organization_from_email(email)
        db.commit()

    token = create_access_token(
        user.id,
        user.role
    )

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "subject": user.subject,
            "organization": user.organization,
        }
    }


# =========================================================
# STUDENT SIGNUP AND EMAIL OTP VERIFICATION
# =========================================================

@app.post("/signup")
def signup(
    signup_data: SignupRequest,
    db: Session = Depends(get_db),
):
    name = signup_data.name.strip()
    email = str(signup_data.email).strip().lower()
    password = signup_data.password
    requested_role = (signup_data.role or "student").strip().lower()
    subject = (signup_data.subject or "").strip()

    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Name is required")

    if len(password.encode("utf-8")) > 72 or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be 6 to 72 characters")

    if requested_role not in {"student", "teacher"}:
        raise HTTPException(status_code=400, detail="Role must be either student or teacher")

    if not is_college_email(email):
        raise HTTPException(
            status_code=400,
            detail="Signup requires a valid college or university email address",
        )

    if requested_role == "teacher" and not subject:
        raise HTTPException(status_code=400, detail="Teacher signup requires a subject")

    if requested_role == "teacher" and subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Invalid teacher subject selected")

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="User with this email already exists")

    otp = f"{secrets.randbelow(1_000_000):06d}"
    pending = db.query(SignupVerification).filter(
        SignupVerification.email == email
    ).first()

    if pending:
        pending.name = name
        pending.password_hash = hash_password(password)
        pending.role = requested_role
        pending.subject = subject or None
        pending.organization = get_organization_from_email(email)
        pending.otp_hash = hash_password(otp)
        pending.attempt_count = 0
        pending.expires_at = (datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
        pending.created_at = datetime.utcnow().isoformat()
    else:
        db.add(SignupVerification(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=requested_role,
            subject=subject or None,
            organization=get_organization_from_email(email),
            otp_hash=hash_password(otp),
            attempt_count=0,
            expires_at=(datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat(),
            created_at=datetime.utcnow().isoformat(),
        ))

    try:
        email_sent = send_signup_otp(email, otp)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="Unable to send verification email")

    response = {
        "message": "Verification OTP sent to your college email",
        "email": email,
        "role": requested_role,
        "expires_in_minutes": OTP_EXPIRY_MINUTES,
    }
    if not email_sent and allow_dev_otp():
        response["development_otp"] = otp
    return response


@app.post("/signup/verify")
def verify_signup(
    verification_data: VerifySignupRequest,
    db: Session = Depends(get_db),
):
    email = str(verification_data.email).strip().lower()
    pending = db.query(SignupVerification).filter(
        SignupVerification.email == email
    ).first()

    if not pending:
        raise HTTPException(status_code=400, detail="No pending signup found for this email")

    try:
        expired = datetime.fromisoformat(pending.expires_at) <= datetime.utcnow()
    except ValueError:
        expired = True

    if expired:
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP expired. Please start signup again")

    if pending.attempt_count >= MAX_OTP_ATTEMPTS:
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please start signup again")

    if not verify_password(verification_data.otp.strip(), pending.otp_hash):
        pending.attempt_count += 1
        if pending.attempt_count >= MAX_OTP_ATTEMPTS:
            db.delete(pending)
            db.commit()
            raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please start signup again")
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if db.query(User).filter(User.email == email).first():
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=400, detail="User with this email already exists")

    user = User(
        name=pending.name,
        email=pending.email,
        password_hash=pending.password_hash,
        role=pending.role or "student",
        subject=pending.subject,
        organization=pending.organization,
        is_active=True,
    )
    db.add(user)
    db.delete(pending)
    db.commit()
    db.refresh(user)

    return {
        "message": "Email verified. Account created successfully. You can now login.",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization": user.organization,
        },
    }


# =========================================================
# OCR - IMAGE
# =========================================================

def clean_ocr_text(text: str | None) -> str:
    if text is None:
        return ""

    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", str(text))
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return ""

    alpha_count = sum(1 for ch in cleaned if ch.isalpha())
    if alpha_count < max(8, int(len(cleaned) * 0.15)):
        return ""

    return cleaned


def extract_text_from_image(
    file_path: str
):

    try:

        image = Image.open(file_path)

        text = pytesseract.image_to_string(
            image,
            lang="eng"
        )

        return clean_ocr_text(text)

    except Exception as e:

        return ""


# =========================================================
# OCR - PDF
# =========================================================

def extract_text_from_pdf(
    file_path: str
):

    try:

        reader = PdfReader(file_path)

        text = ""

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

        return clean_ocr_text(text)

    except Exception:

        return ""


# =========================================================
# EXTRACT ASSIGNMENT TEXT
# =========================================================

def extract_assignment_text(
    file_path: str
):

    extension = Path(file_path).suffix.lower()

    if extension in {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".webp",
    }:

        return extract_text_from_image(
            file_path
        )

    elif extension == ".pdf":

        return extract_text_from_pdf(
            file_path
        )

    else:

        return ""


# =========================================================
# UPLOAD ASSIGNMENTS
# =========================================================

@app.post("/assignments/upload")
async def upload_assignments(
    files: list[UploadFile] = File(...),
    subject: str = Form(...),
    classroom_id: int | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if len(files) < 2:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least 2 assignments"
        )

    if len(files) > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 assignments allowed"
        )

    subject_name = subject.strip()
    if not subject_name:
        raise HTTPException(
            status_code=400,
            detail="Subject is required"
        )

    classroom = None
    if classroom_id is not None:
        classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
        if not classroom:
            raise HTTPException(status_code=404, detail="Classroom not found")

    if current_user.role == "student":
        if classroom_id is None:
            raise HTTPException(status_code=400, detail="Students must submit inside a classroom")
        membership = db.query(ClassroomMembership).filter(
            ClassroomMembership.classroom_id == classroom_id,
            ClassroomMembership.user_id == current_user.id,
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="You are not enrolled in this classroom")
        if subject_name.lower() != classroom.subject.lower():
            raise HTTPException(status_code=403, detail="Student subject must match classroom subject")
        if current_user.subject and current_user.subject.lower() != subject_name.lower():
            raise HTTPException(
                status_code=403,
                detail="Students can only upload assignments for their assigned subject"
            )
        if not current_user.subject:
            current_user.subject = subject_name
            db.commit()
        teacher_id = classroom.teacher_id
    else:
        if classroom_id is not None and classroom and classroom.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only manage your own classroom")
        teacher_id = current_user.id if current_user.role in {"teacher", "super_admin"} else None

    if current_user.role in {"teacher", "super_admin"}:
        if subject_name not in SUBJECTS:
            raise HTTPException(
                status_code=400,
                detail="Invalid subject selection"
            )

    results = []

    for file in files:
        original_filename = file.filename or "unknown"
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            results.append({
                "filename": original_filename,
                "status": "failed",
                "message": "Unsupported file type"
            })
            continue

        unique_filename = f"{uuid.uuid4()}{extension}"
        save_path = UPLOAD_DIR / unique_filename

        try:
            contents = await file.read()
            with open(save_path, "wb") as buffer:
                buffer.write(contents)

            text = extract_assignment_text(str(save_path))
            if not text or len(text.strip()) < 20:
                raise ValueError("No readable text detected. Please upload a clearer assignment image or PDF.")

            assignment = Assignment(
                filename=original_filename,
                file_path=str(save_path),
                extracted_text=text,
                subject=subject_name,
                uploaded_by=current_user.id,
                classroom_id=classroom_id,
                teacher_id=teacher_id,
                is_duplicate=False,
                review_status="pending",
                teacher_decision=None,
            )

            db.add(assignment)
            db.commit()
            db.refresh(assignment)

            results.append({
                "filename": original_filename,
                "saved_file": str(save_path),
                "assignment_id": assignment.id,
                "subject": assignment.subject,
                "status": "success",
                "text": text,
                "text_length": len(text),
            })

        except Exception as e:
            results.append({
                "filename": original_filename,
                "status": "failed",
                "message": str(e)
            })

    return {
        "message": "Assignments processed successfully",
        "total_files": len(files),
        "results": results,
    }


# =========================================================
# VIEW MY ASSIGNMENTS
# =========================================================

@app.get("/assignments/my-uploads")
def get_my_assignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    assignments = db.query(Assignment).filter(
        Assignment.uploaded_by == current_user.id
    ).order_by(Assignment.id.desc()).all()

    return {
        "message": "Your uploaded assignments",
        "total_assignments": len(assignments),
        "assignments": [
            {
                "id": item.id,
                "filename": item.filename,
                "file_path": item.file_path,
                "subject": item.subject,
                "text_length": len(item.extracted_text or ""),
                "is_duplicate": item.is_duplicate,
                "review_status": item.review_status,
                "teacher_decision": item.teacher_decision,
                "uploaded_by": item.uploaded_by,
            }
            for item in assignments
        ],
    }


@app.get("/assignments/teacher-subject")
def get_teacher_assignments_for_subject(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role not in {"teacher", "super_admin"}:
        raise HTTPException(status_code=403, detail="Teacher access required")

    if current_user.role == "teacher" and not current_user.subject:
        raise HTTPException(status_code=400, detail="Teacher subject is not assigned")

    subject_filter = current_user.subject if current_user.role == "teacher" else None
    query = db.query(Assignment)

    if subject_filter:
        query = query.filter(Assignment.subject == subject_filter)

    assignments = query.order_by(Assignment.id.desc()).all()

    return {
        "message": "Assignments for teacher subject",
        "subject": subject_filter,
        "total_assignments": len(assignments),
        "assignments": [
            {
                "id": item.id,
                "filename": item.filename,
                "subject": item.subject,
                "file_path": item.file_path,
                "text_length": len(item.extracted_text or ""),
                "uploaded_by": item.uploaded_by,
                "is_duplicate": item.is_duplicate,
                "review_status": item.review_status,
                "teacher_decision": item.teacher_decision,
                "uploader_name": db.query(User).filter(User.id == item.uploaded_by).first().name if db.query(User).filter(User.id == item.uploaded_by).first() else "Unknown",
            }
            for item in assignments
        ],
    }


@app.get("/assignments/all")
def get_all_assignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role not in {"teacher", "super_admin"}:
        raise HTTPException(
            status_code=403,
            detail="Teacher or admin access required",
        )

    query = db.query(Assignment)
    if current_user.role == "teacher" and current_user.subject:
        query = query.filter(Assignment.subject == current_user.subject)

    assignments = query.order_by(Assignment.id.desc()).all()

    return {
        "message": "Assignment uploads",
        "total_assignments": len(assignments),
        "assignments": [
            {
                "id": item.id,
                "filename": item.filename,
                "file_path": item.file_path,
                "subject": item.subject,
                "text_length": len(item.extracted_text or ""),
                "uploaded_by": item.uploaded_by,
                "is_duplicate": item.is_duplicate,
                "review_status": item.review_status,
                "teacher_decision": item.teacher_decision,
                "uploader_name": db.query(User).filter(User.id == item.uploaded_by).first().name if db.query(User).filter(User.id == item.uploaded_by).first() else "Unknown",
            }
            for item in assignments
        ],
    }


# =========================================================
# CHECK SIMILARITY
# =========================================================

@app.post("/assignments/check-similarity")
def check_similarity(
    payload: Any = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    texts = None
    assignment_ids = None
    subject = None

    if isinstance(payload, list):
        texts = payload
    elif isinstance(payload, dict):
        texts = payload.get("texts")
        assignment_ids = payload.get("assignment_ids")
        subject = payload.get("subject")

    if assignment_ids is not None:
        if not isinstance(assignment_ids, list) or len(assignment_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 assignment IDs are required",
            )

        if current_user.role in {"teacher", "super_admin"}:
            assignments = db.query(Assignment).filter(
                Assignment.id.in_(assignment_ids)
            ).all()
            if current_user.role == "teacher" and current_user.subject:
                assignments = [a for a in assignments if a.subject == current_user.subject]
        else:
            assignments = db.query(Assignment).filter(
                Assignment.id.in_(assignment_ids),
                Assignment.uploaded_by == current_user.id,
            ).all()

        if len(assignments) < 2:
            raise HTTPException(
                status_code=403,
                detail="You can only compare assignments you are allowed to access",
            )

        texts = [assignment.extracted_text or "" for assignment in assignments]

    if texts is None:
        raise HTTPException(
            status_code=400,
            detail="Please provide assignment texts or assignment IDs",
        )

    if len(texts) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 assignment texts are required"
        )

    cleaned_texts = []
    for text in texts:
        if text is None:
            text = ""
        cleaned = clean_ocr_text(str(text))
        if cleaned:
            cleaned_texts.append(cleaned)

    if len(cleaned_texts) < 2:
        raise HTTPException(
            status_code=400,
            detail="No readable text was detected in enough assignments. Please upload clearer assignment scans or PDFs."
        )

    try:
        vectorizer = TfidfVectorizer()
        vectors = vectorizer.fit_transform(cleaned_texts)
        similarity_matrix = cosine_similarity(vectors)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Similarity calculation failed: {str(e)}"
        )

    comparisons = []
    for i in range(len(cleaned_texts)):
        for j in range(i + 1, len(cleaned_texts)):
            score = similarity_matrix[i][j] * 100
            if score >= 80:
                status_text = "High Similarity"
            elif score >= 50:
                status_text = "Moderate Similarity"
            else:
                status_text = "Low Similarity"

            comparisons.append({
                "assignment_1": i + 1,
                "assignment_2": j + 1,
                "similarity_percentage": round(float(score), 2),
                "status": status_text,
            })

    return {
        "message": "Similarity check completed",
        "total_assignments": len(cleaned_texts),
        "comparisons": comparisons,
    }


@app.post("/assignments/review")
def review_assignment(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role not in {"teacher", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only teachers can review assignments")

    assignment_id = payload.get("assignment_id")
    decision = str(payload.get("decision", "")).strip().lower()

    if assignment_id is None or decision not in {"pass", "reject"}:
        raise HTTPException(status_code=400, detail="assignment_id and decision(pass/reject) are required")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if current_user.role == "teacher" and current_user.subject and assignment.subject != current_user.subject:
        raise HTTPException(status_code=403, detail="This teacher can only review assignments in their subject")

    assignment.review_status = "reviewed"
    assignment.teacher_decision = decision
    if decision == "pass":
        assignment.is_duplicate = False
    else:
        assignment.is_duplicate = True

    db.commit()

    return {
        "message": "Assignment reviewed successfully",
        "assignment_id": assignment.id,
        "decision": decision,
        "subject": assignment.subject,
    }


# =========================================================
# DEBUG - CHECK CURRENT USERS
# =========================================================

@app.get("/admin/users")
def get_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    # Only super admin
    if current_user.role != "super_admin":

        raise HTTPException(
            status_code=403,
            detail="Super Admin access required"
        )

    users = db.query(User).all()

    return {

        "users": [

            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "organization": user.organization,
                "role": user.role,
                "is_active": user.is_active,
            }

            for user in users

        ]

    }


# =========================================================
# STARTUP
# =========================================================

def ensure_database_schema(db: Session):
    user_columns = [row[1] for row in db.execute(text("PRAGMA table_info(users)")).fetchall()]
    assignment_columns = [row[1] for row in db.execute(text("PRAGMA table_info(assignments)")).fetchall()]
    verification_columns = [
        row[1]
        for row in db.execute(text("PRAGMA table_info(signup_verifications)")).fetchall()
    ]

    if "subject" not in user_columns:
        db.execute(text("ALTER TABLE users ADD COLUMN subject VARCHAR"))

    if "organization" not in user_columns:
        db.execute(text("ALTER TABLE users ADD COLUMN organization VARCHAR"))

    if "role" not in [row[1] for row in db.execute(text("PRAGMA table_info(signup_verifications)")).fetchall()]:
        db.execute(text("ALTER TABLE signup_verifications ADD COLUMN role VARCHAR DEFAULT 'student'"))

    if "subject" not in [row[1] for row in db.execute(text("PRAGMA table_info(signup_verifications)")).fetchall()]:
        db.execute(text("ALTER TABLE signup_verifications ADD COLUMN subject VARCHAR"))

    if "attempt_count" not in verification_columns:
        db.execute(text("ALTER TABLE signup_verifications ADD COLUMN attempt_count INTEGER DEFAULT 0"))

    if "review_status" not in assignment_columns:
        db.execute(text("ALTER TABLE assignments ADD COLUMN review_status VARCHAR DEFAULT 'pending'"))

    if "teacher_decision" not in assignment_columns:
        db.execute(text("ALTER TABLE assignments ADD COLUMN teacher_decision VARCHAR"))

    if "subject" not in assignment_columns:
        db.execute(text("ALTER TABLE assignments ADD COLUMN subject VARCHAR DEFAULT 'General'"))

    if "classroom_id" not in assignment_columns:
        db.execute(text("ALTER TABLE assignments ADD COLUMN classroom_id INTEGER"))

    if "teacher_id" not in assignment_columns:
        db.execute(text("ALTER TABLE assignments ADD COLUMN teacher_id INTEGER"))

    classroom_columns = [row[1] for row in db.execute(text("PRAGMA table_info(classrooms)")).fetchall()]
    if not classroom_columns:
        db.execute(text("CREATE TABLE IF NOT EXISTS classrooms (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR NOT NULL, subject VARCHAR NOT NULL, teacher_id INTEGER NOT NULL, organization VARCHAR, join_code VARCHAR UNIQUE, created_at VARCHAR NOT NULL)"))

    membership_columns = [row[1] for row in db.execute(text("PRAGMA table_info(classroom_memberships)")).fetchall()]
    if not membership_columns:
        db.execute(text("CREATE TABLE IF NOT EXISTS classroom_memberships (id INTEGER PRIMARY KEY AUTOINCREMENT, classroom_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role VARCHAR DEFAULT 'student', joined_at VARCHAR NOT NULL)"))

    db.commit()


@app.post("/classrooms")
def create_classroom(
    payload: CreateClassroomRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in {"teacher", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only teachers can create classrooms")

    name = payload.name.strip()
    subject = payload.subject.strip()
    if not name or not subject:
        raise HTTPException(status_code=400, detail="Classroom name and subject are required")
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Invalid subject selected")

    join_code = (payload.join_code or "").strip().upper()
    if not join_code:
        join_code = "CLS" + secrets.token_urlsafe(5).upper().replace("-", "")[:8]

    classroom = Classroom(
        name=name,
        subject=subject,
        teacher_id=current_user.id,
        organization=current_user.organization,
        join_code=join_code,
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(classroom)
    db.commit()
    db.refresh(classroom)

    return {
        "message": "Classroom created successfully",
        "classroom": {
            "id": classroom.id,
            "name": classroom.name,
            "subject": classroom.subject,
            "teacher_id": classroom.teacher_id,
            "join_code": classroom.join_code,
            "organization": classroom.organization,
        },
    }


@app.post("/classrooms/join")
def join_classroom(
    payload: JoinClassroomRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can join a classroom")

    join_code = payload.join_code.strip().upper()
    classroom = db.query(Classroom).filter(Classroom.join_code == join_code).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Invalid classroom join code")

    existing = db.query(ClassroomMembership).filter(
        ClassroomMembership.classroom_id == classroom.id,
        ClassroomMembership.user_id == current_user.id,
    ).first()
    if existing:
        return {"message": "You are already a member of this classroom", "classroom_id": classroom.id}

    membership = ClassroomMembership(
        classroom_id=classroom.id,
        user_id=current_user.id,
        role="student",
        joined_at=datetime.utcnow().isoformat(),
    )
    db.add(membership)
    current_user.subject = classroom.subject
    db.commit()

    return {
        "message": "Joined classroom successfully",
        "classroom": {
            "id": classroom.id,
            "name": classroom.name,
            "subject": classroom.subject,
            "teacher_id": classroom.teacher_id,
        },
    }


@app.get("/classrooms")
def get_classrooms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == "teacher":
        classrooms = db.query(Classroom).filter(Classroom.teacher_id == current_user.id).all()
    elif current_user.role == "student":
        membership_ids = db.query(ClassroomMembership.classroom_id).filter(ClassroomMembership.user_id == current_user.id).subquery()
        classrooms = db.query(Classroom).filter(Classroom.id.in_(membership_ids)).all()
    else:
        classrooms = db.query(Classroom).all()

    return {
        "classrooms": [
            {
                "id": item.id,
                "name": item.name,
                "subject": item.subject,
                "teacher_id": item.teacher_id,
                "join_code": item.join_code,
                "organization": item.organization,
            }
            for item in classrooms
        ]
    }


@app.post("/teachers/students/add")
def add_student_to_classroom(
    payload: TeacherAssignStudentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in {"teacher", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only teachers can add students")

    classroom = db.query(Classroom).filter(Classroom.id == payload.classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if current_user.role == "teacher" and classroom.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only add students to your own classroom")

    student = db.query(User).filter(User.email == str(payload.student_email).strip().lower()).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found with this email")

    if student.role != "student":
        raise HTTPException(status_code=400, detail="Only student accounts can be added")

    existing = db.query(ClassroomMembership).filter(
        ClassroomMembership.classroom_id == classroom.id,
        ClassroomMembership.user_id == student.id,
    ).first()
    if existing:
        return {"message": "Student already enrolled in this classroom", "student_id": student.id}

    db.add(ClassroomMembership(
        classroom_id=classroom.id,
        user_id=student.id,
        role="student",
        joined_at=datetime.utcnow().isoformat(),
    ))
    student.subject = classroom.subject
    db.commit()

    return {
        "message": "Student added to classroom successfully",
        "student": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "subject": student.subject,
        },
        "classroom_id": classroom.id,
    }


@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    try:
        ensure_database_schema(db)

        demo_users = [
            ("tuktuksingh6317@gmail.com", "Tuktu Singh", "super_admin", "Admin@123", None, "gmail.com"),
            ("student@college.edu.in", "Student User", "student", "123456", "Computer Science", "college.edu.in"),
            ("teacher@college.edu.in", "Teacher User", "teacher", "123456", "Computer Science", "college.edu.in"),
        ]

        for email, name, role, password, subject, org in demo_users:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                existing.name = name
                existing.role = role
                existing.subject = subject
                existing.organization = org
                existing.is_active = True
                existing.password_hash = hash_password(password)
            else:
                db.add(User(
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role=role,
                    subject=subject,
                    organization=org,
                    is_active=True,
                ))

        db.commit()
    finally:
        db.close()


print("=" * 60)

print("AI Assignment Duplicate Checker")

print("Backend started successfully")

print("Swagger: http://127.0.0.1:8000/docs")

print("=" * 60)