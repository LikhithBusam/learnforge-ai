# Frontend Authentication Architecture & Integration Guide (Phase 12.1)

## 1. Root Cause Diagnosis of Previous 422 Errors
The backend authentication routes (`/api/v1/auth/login` and `/api/v1/auth/register`) in `app.identity.router` are defined with strict Pydantic models:
```python
class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
```
- **The Problem**: The initial client implementation was sending a `FormData` object with `username` and `password` fields (`application/x-www-form-urlencoded` or `multipart/form-data`), which caused FastAPI to reject the requests with **HTTP 422 (Unprocessable Entity)** due to the `extra="forbid"` configuration and missing `email` field.
- **The Fix**: The frontend API client was refactored to send explicit JSON payloads with headers `Content-Type: application/json` containing `{"email": "...", "password": "..."}`.

---

## 2. Authentication Contract & Response Schema

### Login: `POST /api/v1/auth/login`
- **Request Body**:
  ```json
  {
    "email": "learner@studycompanion.app",
    "password": "LearnerSecurePass123!"
  }
  ```
- **Response (`TokenResponse`)**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
      "id": "uuid-v4-string",
      "email": "learner@studycompanion.app",
      "display_name": "Learner",
      "role": "learner"
    }
  }
  ```

### Registration: `POST /api/v1/auth/register`
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "display_name": "Alex Mercer"
  }
  ```
- **Response**: Exact same `TokenResponse` with `201 Created`. Tokens are immediately stored without requiring a redundant secondary login call.

### Session Verification: `GET /api/v1/auth/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response**: `{ "id": "...", "email": "...", "display_name": "...", "role": "..." }`

---

## 3. Client State Machine
Client authentication in `packages/web/src/context/AuthContext.tsx` follows a robust, predictable state machine:
```text
[Initial Page Load]
       │
       ▼
CHECKING_SESSION (reads localStorage 'study_access_token')
       ├───────── Token Present ───► GET /api/v1/auth/me
       │                                  ├─ 200 OK ──► AUTHENTICATED (sets user)
       │                                  └─ 401 ─────► UNAUTHENTICATED (clears token)
       └───────── No Token ────────► UNAUTHENTICATED (renders AuthModal)
```

---

## 4. Error Mapping & Human-Friendly Feedback
- **401 Unauthorized**: "Email or password is incorrect."
- **422 Unprocessable**: "Please enter a valid email and password."
- **429 Rate Limited**: "Too many login attempts. Please wait a moment and try again."
- **500 / Network Error**: "Unable to connect to the server. Please verify the backend is running."
