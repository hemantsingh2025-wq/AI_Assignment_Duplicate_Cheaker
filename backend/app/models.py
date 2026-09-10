from sqlalchemy import Column, Integer, String, Boolean, Float
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    password_hash = Column(
        String,
        nullable=False
    )

    role = Column(
        String,
        default="student",
        nullable=False
    )

    subject = Column(
        String,
        nullable=True
    )

    organization = Column(
        String,
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )


class SignupVerification(Base):
    __tablename__ = "signup_verifications"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)

    password_hash = Column(String, nullable=False)

    organization = Column(String, nullable=False)

    otp_hash = Column(String, nullable=False)

    attempt_count = Column(Integer, nullable=False, default=0)

    expires_at = Column(String, nullable=False)

    created_at = Column(String, nullable=False)


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    filename = Column(
        String,
        nullable=False
    )

    file_path = Column(
        String,
        nullable=False
    )

    extracted_text = Column(
        String,
        nullable=True
    )

    subject = Column(
        String,
        nullable=False,
        default="General"
    )

    uploaded_by = Column(
        Integer,
        nullable=False
    )

    is_duplicate = Column(
        Boolean,
        default=False
    )

    review_status = Column(
        String,
        nullable=False,
        default="pending"
    )

    teacher_decision = Column(
        String,
        nullable=True
    )


class SimilarityResult(Base):
    __tablename__ = "similarity_results"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    assignment_1_id = Column(
        Integer,
        nullable=False
    )

    assignment_2_id = Column(
        Integer,
        nullable=False
    )

    similarity = Column(
        Float,
        nullable=False
    )