# Developer Guide

## 1. Purpose

Ye guide aapko is project ko samajhne, modify karne aur extend karne mein help karegi.

Is project ka focus hai ek AI-powered personal finance assistant banana jisme:
- user authentication
- income/expense tracking
- AI-based financial insights
- chat assistant
- notes/tasks management

---

## 2. Project Architecture

Project ko main 3 layers mein socha gaya hai:

### A. Presentation Layer
Ye frontend se related hota hai aur user interactions handle karta hai.

### B. API Layer
Ye FastAPI routes aur controllers ka layer hai.
- request receive karta hai
- validation karta hai
- business logic call karta hai
- response bhejta hai

### C. Data Layer
Ye SQLAlchemy models aur database ka layer hai.
- data store karta hai
- relationships manage karta hai
- CRUD operations handle karta hai

---

## 3. Main Folder Structure

```text
backend/
  app/
    app.py
  api/
    auth.py
    database.py
    models/
    routes/
    schemas/
    services/
    WebApp/
  chats/
    chat.py
    chatbot.py
    gemini_service.py
    handlers/
    utils/
  main.py
```

### Important folders

- app/: FastAPI app initialization
- api/: core backend logic
- chats/: AI chatbot and Gemini integration
- main.py: server entry point

---

## 4. How the Backend Starts

Server start hota hai [backend/main.py](backend/main.py).

Ye file simply uvicorn ko run karta hai:
- app import karta hai
- host aur port provide karta hai

Actual FastAPI application [backend/app/app.py](backend/app/app.py) mein define hai.

### Startup flow
1. app create hoti hai
2. database tables create ki jaati hain
3. routers include kiye jaate hain
4. CORS setup hota hai
5. server ready ho jaata hai

---

## 5. Core Components

### 5.1 Database Setup
File: [backend/api/database.py](backend/api/database.py)

Is file mein:
- database engine create hoti hai
- session factory define hoti hai
- `get_db()` dependency provide hoti hai

### Why it matters
Har route ko database access dene ke liye ye central dependency use hoti hai.

### 5.2 Models
File: [backend/api/models/vitya.py](backend/api/models/vitya.py)

Yahan database tables define hain:
- users
- income
- expense
- notes
- tasks
- conversations/chat messages

### Best practice
Jab bhi new feature add karo, pehle model define karo phir route aur schema banao.

### 5.3 Schemas
File: [backend/api/schemas/vitya.py](backend/api/schemas/vitya.py)

Schemas request/response structure define karti hain.

Ye useful hai kyunki:
- input validation hoti hai
- API contract clear hota hai
- response structure consistent rehti hai

---

## 6. Authentication Flow

File: [backend/api/auth.py](backend/api/auth.py)

### Authentication process
1. user login/register karta hai
2. backend JWT token generate karta hai
3. client token ko save karta hai
4. future requests mein token bhejta hai
5. backend token verify karta hai
6. current user identify hota hai

### Important functions
- `create_access_token()`
- `token_required()`
- `create_reset_token()`
- `verify_reset_token()`

### Developer note
Agar aap protected route add karte ho, to us route par `Depends(token_required)` lagana zaroori hai.

---

## 7. Route Structure

### 7.1 User Routes
File: [backend/api/routes/users.py](backend/api/routes/users.py)

Contains:
- register
- login
- profile get/update
- forgot password
- reset password

### 7.2 Income Routes
File: [backend/api/routes/income.py](backend/api/routes/income.py)

Contains:
- create income
- list incomes
- get one income
- update income
- delete income

### 7.3 Expense Routes
File: [backend/api/routes/expense.py](backend/api/routes/expense.py)

Contains:
- create expense
- list expenses
- get one expense
- update expense
- delete expense

### 7.4 AI Routes
File: [backend/api/routes/ai.py](backend/api/routes/ai.py)

Contains:
- prediction
- overspending detection
- budget planning
- waste analysis
- monthly trend
- anomaly detection

### 7.5 Notes and Tasks
Files:
- [backend/api/WebApp/notes.py](backend/api/WebApp/notes.py)
- [backend/api/WebApp/tasks.py](backend/api/WebApp/tasks.py)

These are simple CRUD endpoints.

---

## 8. Chat System Flow

### Entry point
File: [backend/chats/chat.py](backend/chats/chat.py)

Ye file incoming user message ko process karta hai.

### Flow
1. user message aata hai
2. file/news/wiki handlers check hote hain
3. agar koi handler match karta hai to response return hota hai
4. warna chatbot handler call hota hai

### Chatbot flow
File: [backend/chats/chatbot.py](backend/chats/chatbot.py)

Ye message ko categories mein divide karta hai:
- transaction handling
- chart requests
- utility requests
- info/help requests

### Gemini integration
File: [backend/chats/gemini_service.py](backend/chats/gemini_service.py)

Yahan Gemini API se response generate hota hai.

### Developer note
Agar aap new chat feature add karna chahte ho to:
- handler create karo
- chatbot flow mein include karo
- agar required ho to Gemini service ko use karo

---

## 9. How to Add a New Feature

### Step 1: Create / update model
Agar feature ko database mein store karna hai to model add karo.

### Step 2: Create schema
Request aur response ke liye schema define karo.

### Step 3: Create route
New endpoint add karo in routes folder.

### Step 4: Include router in app
File: [backend/app/app.py](backend/app/app.py) mein router include karo.

### Step 5: Test manually
Use FastAPI docs or Postman to test the endpoint.

---

## 10. Best Practices

### Code style
- simple and readable code likho
- function names descriptive rakho
- comments ka use moderate rakho

### Database
- always use dependency injection for DB session
- avoid direct DB access in unrelated files

### Authentication
- protected routes ko always secure karo
- JWT secret ko safely manage karo

### Error handling
- proper HTTP exceptions use karo
- user-friendly messages do

### Validation
- Pydantic schemas ka use karo
- empty values ko reject karo

---

## 11. Local Development Setup

### Step 1: Create virtual environment
```bash
python -m venv venv
```

### Step 2: Activate environment
On Windows:
```bash
venv\Scripts\activate
```

### Step 3: Install requirements
```bash
pip install -r requirements.txt
```

### Step 4: Set environment variables
Create `.env` file:
```text
SECRET_KEY=your_secret_key
DATABASE_URL=sqlite:///./instance/test.db
GEMINI_API_KEY=your_gemini_key
```

### Step 5: Run app
```bash
python backend/main.py
```

---

## 12. Testing Checklist

Jab aap feature add ya modify karo to ye check karo:
- app starts without errors
- route responds correctly
- auth works properly
- DB operations succeed
- error messages are clear
- no broken imports

---

## 13. Common Issues

### Import errors
Aksar issue hota hai jab package path wrong ho.
Solution:
- confirm Python path
- run from project root
- check `backend` package structure

### Database errors
Aksar issue hota hai:
- missing env var
- wrong database URL
- table not created

### Authentication issues
Aksar issue hota hai:
- expired token
- wrong secret key
- missing auth header

---

## 14. Future Improvements

Aap is project ko aur improve kar sakte ho:
- add tests
- add logging
- add dashboard analytics
- add voice assistant
- add bank API integration
- improve chatbot memory and context

---

## 15. Summary

Is project ko samajhne ka easiest approach ye hai:
1. app entry point samjho
2. routes samjho
3. models aur schemas samjho
4. auth flow samjho
5. chat system samjho

Ye hi backend ka core structure hai.
