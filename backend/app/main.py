# =========================================================
# AI ASSIGNMENT DUPLICATE CHECKER - MAIN.PY
# =========================================================
import asyncio
import json
import os
import re
import secrets
import smtplib
import uuid
import logging
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
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, EmailStr

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from PIL import Image
import pytesseract
from pypdf import PdfReader

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from jose import jwt, JWTError

from app.database import Base, engine, SessionLocal
from app.models import (
    Assignment,
    AssignmentNotification,
    Classroom,
    ClassroomMembership,
    SignupVerification,
    User,
)
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


@app.middleware("http")
async def rewrite_vercel_api_path(request, call_next):
    route_path = request.query_params.get("__route")
    if route_path:
        route_path = "/" + route_path.lstrip("/")
    elif request.url.path.startswith("/api/"):
        route_path = request.url.path[4:]

    if route_path:
        request.scope["path"] = route_path
        request.scope["raw_path"] = route_path.encode("utf-8")
    return await call_next(request)


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

UPLOAD_DIR = Path(
    os.getenv(
        "UPLOAD_DIR",
        "/tmp/assignment-checker-uploads" if os.getenv("VERCEL") == "1" else "uploads",
    )
)

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

PERSONAL_EMAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "msn.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}

OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 5
logger = logging.getLogger(__name__)


class OnlineClassManager:
    def __init__(self):
        self.rooms: dict[int, dict[str, dict[str, Any]]] = {}
        self.lock = asyncio.Lock()

    async def has_teacher(self, classroom_id: int) -> bool:
        async with self.lock:
            participants = self.rooms.get(classroom_id, {}).values()
            return any(participant["role"] == "teacher" for participant in participants)

    async def join(
        self,
        classroom_id: int,
        websocket: WebSocket,
        user_id: int,
        name: str,
        role: str,
    ) -> tuple[str, list[dict[str, str]]] | None:
        participant_id = str(uuid.uuid4())
        async with self.lock:
            room = self.rooms.setdefault(classroom_id, {})
            participants = list(room.values())
            host_is_online = any(item["role"] == "teacher" for item in participants)

            if role == "student" and not host_is_online:
                if not room:
                    self.rooms.pop(classroom_id, None)
                await websocket.send_json({
                    "type": "error",
                    "message": "The teacher has not started this online class yet.",
                })
                await websocket.close(code=4404)
                return None

            if role == "teacher" and host_is_online:
                await websocket.send_json({
                    "type": "error",
                    "message": "This online class is already being hosted.",
                })
                await websocket.close(code=4409)
                return None

            if len(participants) >= 6:
                await websocket.send_json({
                    "type": "error",
                    "message": "This online class has reached its 6-participant limit.",
                })
                await websocket.close(code=4429)
                return None

            room[participant_id] = {
                "socket": websocket,
                "user_id": user_id,
                "name": name,
                "role": role,
            }
            existing = [
                {"id": key, "name": item["name"], "role": item["role"]}
                for key, item in room.items()
                if key != participant_id
            ]

        return participant_id, existing

    async def notify_joined(
        self,
        classroom_id: int,
        participant_id: str,
        name: str,
        role: str,
    ) -> None:
        await self.broadcast(
            classroom_id,
            {"type": "participant_joined", "participant": {
                "id": participant_id,
                "name": name,
                "role": role,
            }},
            exclude=participant_id,
        )

    async def relay(
        self,
        classroom_id: int,
        sender_id: str,
        target_id: str,
        message_type: str,
        data: Any,
    ) -> bool:
        async with self.lock:
            target = self.rooms.get(classroom_id, {}).get(target_id)
        if not target:
            return False
        try:
            await target["socket"].send_json({
                "type": message_type,
                "from": sender_id,
                "data": data,
            })
        except WebSocketDisconnect:
            await self.leave(classroom_id, target_id)
            return False
        return True

    async def broadcast(
        self,
        classroom_id: int,
        message: dict[str, Any],
        exclude: str | None = None,
    ) -> None:
        async with self.lock:
            participants = [
                (participant_id, participant["socket"])
                for participant_id, participant in self.rooms.get(classroom_id, {}).items()
                if participant_id != exclude
            ]
        for participant_id, socket in participants:
            try:
                await socket.send_json(message)
            except WebSocketDisconnect:
                await self.leave(classroom_id, participant_id)

    async def leave(self, classroom_id: int, participant_id: str) -> None:
        async with self.lock:
            room = self.rooms.get(classroom_id)
            if not room:
                return
            participant = room.pop(participant_id, None)
            if not participant:
                return
            if participant["role"] == "teacher":
                remaining = list(room.values())
                self.rooms.pop(classroom_id, None)
            else:
                remaining = []
                if not room:
                    self.rooms.pop(classroom_id, None)

        if participant["role"] == "teacher":
            for other in remaining:
                await other["socket"].send_json({"type": "class_ended"})
                await other["socket"].close(code=4001)
        else:
            await self.broadcast(
                classroom_id,
                {"type": "participant_left", "participant_id": participant_id},
            )


online_class_manager = OnlineClassManager()


def allow_dev_otp() -> bool:
    configured_value = os.getenv("ALLOW_DEV_OTP")
    if configured_value is not None:
        return configured_value.lower() == "true"
    return os.getenv("VERCEL") != "1"


def send_signup_otp(email: str, otp: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_username or "")

    if not all((smtp_host, smtp_username, smtp_password, sender_email)):
        if allow_dev_otp():
            return False
        raise RuntimeError(
            "Email delivery is not configured. Set SMTP_HOST, SMTP_PORT, "
            "SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM in the backend environment."
        )

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


def is_personal_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].lower().strip() in PERSONAL_EMAIL_DOMAINS


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
    if not domain or domain in PERSONAL_EMAIL_DOMAINS:
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
    except (RuntimeError, ValueError) as exc:
        db.rollback()
        logger.error("Signup OTP email is not configured: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (smtplib.SMTPException, OSError) as exc:
        db.rollback()
        logger.exception("Signup OTP email delivery failed")
        raise HTTPException(
            status_code=503,
            detail="Unable to deliver the verification email. Check the backend SMTP settings.",
        ) from exc

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

    minimum_file_count = 1 if current_user.role == "student" else 2
    if len(files) < minimum_file_count:
        raise HTTPException(
            status_code=400,
            detail=(
                "Please upload at least 1 assignment"
                if current_user.role == "student"
                else "Please upload at least 2 assignments"
            )
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
        if classroom_id is not None:
            membership = db.query(ClassroomMembership).filter(
                ClassroomMembership.classroom_id == classroom_id,
                ClassroomMembership.user_id == current_user.id,
            ).first()
            if not membership:
                raise HTTPException(status_code=403, detail="You are not enrolled in this classroom")
            if subject_name.lower() != classroom.subject.lower():
                raise HTTPException(status_code=403, detail="Student subject must match classroom subject")
            teacher_id = classroom.teacher_id
        else:
            has_classroom = db.query(ClassroomMembership).filter(
                ClassroomMembership.user_id == current_user.id,
            ).first()
            if has_classroom:
                raise HTTPException(
                    status_code=400,
                    detail="Choose one of your enrolled classrooms before uploading",
                )
            if subject_name not in SUBJECTS:
                raise HTTPException(status_code=400, detail="Invalid subject selection")
        if current_user.subject and current_user.subject.lower() != subject_name.lower():
            raise HTTPException(
                status_code=403,
                detail="Students can only upload assignments for their assigned subject"
            )
        if not current_user.subject:
            current_user.subject = subject_name
            db.commit()
        if classroom_id is None:
            teacher_id = None
    else:
        if classroom_id is not None and classroom and classroom.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only manage your own classroom")
        teacher_id = current_user.id if current_user.role in {"teacher", "authority"} else None

    if current_user.role in {"teacher", "authority"}:
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

    if current_user.role not in {"teacher", "authority", "super_admin"}:
        raise HTTPException(status_code=403, detail="Teacher access required")

    return get_teacher_classroom_assignments(current_user, db)


def get_teacher_classroom_assignments(current_user: User, db: Session):
    query = (
        db.query(Assignment, User.name, Classroom.name)
        .outerjoin(User, User.id == Assignment.uploaded_by)
        .outerjoin(Classroom, Classroom.id == Assignment.classroom_id)
    )
    if current_user.role == "teacher":
        teacher_classrooms = db.query(Classroom.id).filter(
            Classroom.teacher_id == current_user.id
        )
        query = query.filter(or_(
            Assignment.teacher_id == current_user.id,
            Assignment.classroom_id.in_(teacher_classrooms),
        ))

    rows = query.order_by(Assignment.id.desc()).all()
    return {
        "message": "Assignments organized by classroom and section",
        "total_assignments": len(rows),
        "assignments": [
            {
                "id": assignment.id,
                "filename": assignment.filename,
                "subject": assignment.subject,
                "classroom_id": assignment.classroom_id,
                "classroom_name": classroom_name,
                "class_section": classroom_name or "No classroom assigned",
                "text_length": len(assignment.extracted_text or ""),
                "uploaded_by": assignment.uploaded_by,
                "is_duplicate": assignment.is_duplicate,
                "review_status": assignment.review_status,
                "teacher_decision": assignment.teacher_decision,
                "uploader_name": uploader_name or "Unknown",
            }
            for assignment, uploader_name, classroom_name in rows
        ],
    }


@app.get("/assignments/all")
def get_all_assignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role not in {"teacher", "authority", "super_admin"}:
        raise HTTPException(
            status_code=403,
            detail="Teacher or admin access required",
        )

    if current_user.role == "teacher":
        return get_teacher_classroom_assignments(current_user, db)

    rows = (
        db.query(Assignment, User.name, Classroom.name)
        .outerjoin(User, User.id == Assignment.uploaded_by)
        .outerjoin(Classroom, Classroom.id == Assignment.classroom_id)
        .order_by(Assignment.id.desc())
        .all()
    )
    return {
        "message": "Assignment uploads",
        "total_assignments": len(rows),
        "assignments": [
            {
                "id": assignment.id,
                "filename": assignment.filename,
                "file_path": assignment.file_path,
                "subject": assignment.subject,
                "classroom_id": assignment.classroom_id,
                "classroom_name": classroom_name,
                "class_section": classroom_name or "No classroom assigned",
                "text_length": len(assignment.extracted_text or ""),
                "uploaded_by": assignment.uploaded_by,
                "is_duplicate": assignment.is_duplicate,
                "review_status": assignment.review_status,
                "teacher_decision": assignment.teacher_decision,
                "uploader_name": uploader_name or "Unknown",
            }
            for assignment, uploader_name, classroom_name in rows
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
    if current_user.role == "student":
        raise HTTPException(
            status_code=403,
            detail="Students can upload assignments and check their review status, but cannot run similarity checks",
        )

    texts = None
    assignment_ids = None
    subject = None
    source_assignments = None

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

        if current_user.role == "teacher":
            teacher_classrooms = db.query(Classroom.id).filter(
                Classroom.teacher_id == current_user.id
            )
            assignments = db.query(Assignment).filter(
                Assignment.id.in_(assignment_ids),
                or_(
                    Assignment.teacher_id == current_user.id,
                    Assignment.classroom_id.in_(teacher_classrooms),
                ),
            ).all()
        elif current_user.role in {"authority", "super_admin"}:
            assignments = db.query(Assignment).filter(
                Assignment.id.in_(assignment_ids)
            ).all()
        else:
            assignments = db.query(Assignment).filter(
                Assignment.id.in_(assignment_ids),
                Assignment.uploaded_by == current_user.id,
            ).all()

        assignments_by_id = {assignment.id: assignment for assignment in assignments}
        if len(assignments_by_id) != len(assignment_ids):
            raise HTTPException(
                status_code=403,
                detail="You can only compare assignments you are allowed to access",
            )

        source_assignments = [assignments_by_id[assignment_id] for assignment_id in assignment_ids]
        texts = [assignment.extracted_text or "" for assignment in source_assignments]

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
    comparison_assignments = []
    for index, text in enumerate(texts):
        if text is None:
            text = ""
        cleaned = clean_ocr_text(str(text))
        if cleaned:
            cleaned_texts.append(cleaned)
            assignment = source_assignments[index] if source_assignments else None
            comparison_assignments.append({
                "id": assignment.id if assignment else None,
                "filename": assignment.filename if assignment else f"Assignment {index + 1}",
            })

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
            score = float(similarity_matrix[i][j])
            score_percentage = score * 100
            if score_percentage >= 80:
                status_text = "High Similarity"
            elif score_percentage >= 50:
                status_text = "Moderate Similarity"
            else:
                status_text = "Low Similarity"

            comparisons.append({
                "assignment_1": i + 1,
                "assignment_2": j + 1,
                "assignment_1_id": comparison_assignments[i]["id"],
                "assignment_2_id": comparison_assignments[j]["id"],
                "assignment_1_name": comparison_assignments[i]["filename"],
                "assignment_2_name": comparison_assignments[j]["filename"],
                "cosine_similarity": round(score, 4),
                "similarity_percentage": round(score_percentage, 2),
                "status": status_text,
            })

    return {
        "message": "Similarity check completed",
        "method": "TF-IDF cosine similarity",
        "total_assignments": len(cleaned_texts),
        "comparisons": comparisons,
    }


@app.post("/assignments/review")
def review_assignment(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role not in {"teacher", "authority", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only teachers can review assignments")

    assignment_id = payload.get("assignment_id")
    decision = str(payload.get("decision", "")).strip().lower()

    if assignment_id is None or decision not in {"pass", "reject"}:
        raise HTTPException(status_code=400, detail="assignment_id and decision(pass/reject) are required")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if current_user.role == "teacher":
        teacher_classrooms = db.query(Classroom.id).filter(
            Classroom.teacher_id == current_user.id
        )
        has_access = (
            assignment.teacher_id == current_user.id
            or assignment.classroom_id in {
                classroom_id
                for (classroom_id,) in teacher_classrooms.all()
            }
        )
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="You can only review assignments sent to your classrooms",
            )

    previous_decision = assignment.teacher_decision
    assignment.review_status = "reviewed"
    assignment.teacher_decision = decision
    if decision == "pass":
        assignment.is_duplicate = False
    else:
        assignment.is_duplicate = True

    assignment_owner = db.query(User).filter(User.id == assignment.uploaded_by).first()
    if previous_decision != decision and assignment_owner and assignment_owner.role == "student":
        decision_label = "approved" if decision == "pass" else "rejected"
        db.add(AssignmentNotification(
            user_id=assignment.uploaded_by,
            assignment_id=assignment.id,
            message=f"Your assignment '{assignment.filename}' was {decision_label} by your teacher.",
            is_read=False,
            created_at=datetime.utcnow().isoformat(),
        ))

    db.commit()

    return {
        "message": "Assignment reviewed successfully",
        "assignment_id": assignment.id,
        "decision": decision,
        "subject": assignment.subject,
    }


@app.get("/notifications")
def get_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Only students can view assignment notifications",
        )

    notifications = db.query(AssignmentNotification).filter(
        AssignmentNotification.user_id == current_user.id,
    ).order_by(AssignmentNotification.id.desc()).limit(50).all()

    return {
        "unread_count": sum(not notification.is_read for notification in notifications),
        "notifications": [
            {
                "id": notification.id,
                "assignment_id": notification.assignment_id,
                "message": notification.message,
                "is_read": notification.is_read,
                "created_at": notification.created_at,
            }
            for notification in notifications
        ],
    }


@app.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Only students can update assignment notifications",
        )

    notification = db.query(AssignmentNotification).filter(
        AssignmentNotification.id == notification_id,
        AssignmentNotification.user_id == current_user.id,
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}


# =========================================================
# AUTHORITY OVERVIEW
# =========================================================

@app.get("/authority/overview")
def get_authority_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in {"authority", "super_admin"}:
        raise HTTPException(status_code=403, detail="Authority access required")

    return {
        "total_users": db.query(User).count(),
        "students": db.query(User).filter(User.role == "student").count(),
        "teachers": db.query(User).filter(User.role == "teacher").count(),
        "assignments": db.query(Assignment).count(),
        "pending_reviews": db.query(Assignment).filter(
            Assignment.review_status == "pending"
        ).count(),
        "duplicate_assignments": db.query(Assignment).filter(
            Assignment.is_duplicate.is_(True)
        ).count(),
    }


# =========================================================
# AUTHORITY USER DIRECTORY
# =========================================================

@app.get("/admin/users")
def get_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in {"authority", "super_admin"}:
        raise HTTPException(
            status_code=403,
            detail="Authority access required"
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
    if current_user.role not in {"teacher", "authority", "super_admin"}:
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
async def get_classrooms(
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

    classroom_results = []
    for item in classrooms:
        classroom_results.append({
                "id": item.id,
                "name": item.name,
                "subject": item.subject,
                "teacher_id": item.teacher_id,
                "join_code": item.join_code,
                "organization": item.organization,
                "is_online": await online_class_manager.has_teacher(item.id),
            })

    return {"classrooms": classroom_results}


def can_access_online_class(
    db: Session,
    classroom: Classroom,
    user: User,
) -> bool:
    if user.role == "teacher":
        return classroom.teacher_id == user.id
    if user.role == "student":
        return db.query(ClassroomMembership).filter(
            ClassroomMembership.classroom_id == classroom.id,
            ClassroomMembership.user_id == user.id,
        ).first() is not None
    return False


@app.get("/classrooms/{classroom_id}/online-config")
def get_online_class_config(
    classroom_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if not can_access_online_class(db, classroom, current_user):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    ice_servers: list[dict[str, Any]] = [
        {"urls": "stun:stun.l.google.com:19302"},
    ]
    turn_url = os.getenv("WEBRTC_TURN_URL")
    if turn_url:
        turn_server: dict[str, Any] = {
            "urls": [url.strip() for url in turn_url.split(",") if url.strip()],
        }
        turn_username = os.getenv("WEBRTC_TURN_USERNAME")
        turn_credential = os.getenv("WEBRTC_TURN_CREDENTIAL")
        if turn_username:
            turn_server["username"] = turn_username
        if turn_credential:
            turn_server["credential"] = turn_credential
        ice_servers.append(turn_server)

    return {"ice_servers": ice_servers}


@app.websocket("/classrooms/{classroom_id}/online")
@app.websocket("/api/classrooms/{classroom_id}/online")
async def online_class_websocket(
    websocket: WebSocket,
    classroom_id: int,
):
    offered_protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
    token_protocol = next(
        (protocol.strip() for protocol in offered_protocols if protocol.strip().startswith("bearer.")),
        "",
    )
    token = token_protocol.removeprefix("bearer.")
    if not token:
        await websocket.close(code=4401)
        return

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except (JWTError, TypeError, ValueError):
        await websocket.close(code=4401)
        return

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
        if (
            not user
            or not user.is_active
            or not classroom
            or not can_access_online_class(db, classroom, user)
        ):
            await websocket.close(code=4403)
            return
        user_name = user.name
        user_role = user.role

    if user_role not in {"teacher", "student"}:
        await websocket.close(code=4403)
        return

    await websocket.accept(subprotocol="assignment-checker")
    joined = await online_class_manager.join(
        classroom_id,
        websocket,
        user_id,
        user_name,
        user_role,
    )
    if not joined:
        return

    participant_id, existing_participants = joined
    try:
        await websocket.send_json({
            "type": "room_state",
            "participant_id": participant_id,
            "participants": existing_participants,
        })
        if user_role == "teacher":
            await online_class_manager.broadcast(
                classroom_id,
                {"type": "class_started"},
            )
        else:
            await online_class_manager.notify_joined(
                classroom_id,
                participant_id,
                user_name,
                user_role,
            )

        while True:
            message_text = await websocket.receive_text()
            if len(message_text) > 65536:
                await websocket.send_json({"type": "error", "message": "Signaling message is too large."})
                continue
            try:
                message = json.loads(message_text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid signaling message."})
                continue

            message_type = message.get("type") if isinstance(message, dict) else None
            if message_type not in {"offer", "answer", "ice_candidate"}:
                await websocket.send_json({"type": "error", "message": "Unsupported signaling message."})
                continue

            target_id = message.get("to")
            if not isinstance(target_id, str):
                await websocket.send_json({"type": "error", "message": "A valid signaling recipient is required."})
                continue
            delivered = await online_class_manager.relay(
                classroom_id,
                participant_id,
                target_id,
                message_type,
                message.get("data"),
            )
            if not delivered:
                await websocket.send_json({"type": "error", "message": "The selected participant is no longer online."})
    except WebSocketDisconnect:
        pass
    finally:
        await online_class_manager.leave(classroom_id, participant_id)


@app.post("/teachers/students/add")
def add_student_to_classroom(
    payload: TeacherAssignStudentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in {"teacher", "authority", "super_admin"}:
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
            ("student@college.edu.in", "Student User", "student", "123456", "Computer Science", "college.edu.in"),
            ("teacher@college.edu.in", "Teacher User", "teacher", "123456", "Computer Science", "college.edu.in"),
        ]
        admin_email = os.getenv("DEMO_ADMIN_EMAIL", "").strip().lower()
        admin_password = os.getenv("DEMO_ADMIN_PASSWORD")
        if bool(admin_email) != bool(admin_password):
            raise RuntimeError(
                "Set both DEMO_ADMIN_EMAIL and DEMO_ADMIN_PASSWORD to seed the demo admin account."
            )
        if admin_email and admin_password:
            demo_users.append((
                admin_email,
                os.getenv("DEMO_ADMIN_NAME", "Demo Admin"),
                "super_admin",
                admin_password,
                None,
                get_organization_from_email(admin_email),
            ))

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