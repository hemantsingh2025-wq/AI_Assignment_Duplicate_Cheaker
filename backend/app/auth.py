# =========================================================
# AI ASSIGNMENT DUPLICATE CHECKER - AUTH.PY
# =========================================================

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext


# =========================================================
# JWT CONFIGURATION
# =========================================================

SECRET_KEY = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_KEY_123456789"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60


# =========================================================
# PASSWORD CONFIGURATION
# =========================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


# =========================================================
# HASH PASSWORD
# =========================================================

def hash_password(password: str) -> str:

    password_bytes = password.encode("utf-8")

    if len(password_bytes) > 72:
        raise ValueError(
            "Password must be 72 bytes or less."
        )

    return pwd_context.hash(password)


# =========================================================
# VERIFY PASSWORD
# =========================================================

def verify_password(
    password: str,
    password_hash: str,
) -> bool:

    password_bytes = password.encode("utf-8")

    if len(password_bytes) > 72:
        return False

    try:
        return pwd_context.verify(
            password,
            password_hash,
        )

    except Exception:
        return False


# =========================================================
# CREATE ACCESS TOKEN
# =========================================================

def create_access_token(
    user_id: int,
    role: str,
) -> str:

    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# =========================================================
# DECODE ACCESS TOKEN
# =========================================================

def decode_access_token(
    token: str,
):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        return payload

    except JWTError:

        return None