# MOTHER Master API Endpoint Map

**Document Version**: 1.0.0  
**Status**: Code-Verified API Surface (Phase 1)  
**Date**: October 2026  
**Total Registered Endpoints**: 74 Endpoints across 14 Routers  

---

## 1. Module 1: Presentation Studio Endpoints

**Base Path**: `/api/presentation`  
**Router Module**: `backend/presentation/presentation_api.py`

| Method | Path | Function | Auth | Request Body / Params | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/health` | `health` | Public | None | `{"status": "ok", ...}` | Engine status and readiness probe |
| `GET` | `/templates` | `get_templates` | Public | None | `{"status": "success", "templates": [...]}` | Catalog of 14 design presets |
| `GET` | `/shapes/catalog` | `get_shapes_catalog` | Public | None | `{"status": "success", "shapes": [...]}` | Visual vector shapes and badges |
| `POST` | `/plan` | `preview_plan` | Optional | `GenerateRequest` | `PlanPreviewResponse` | **Stage 1**: Generate structured slide plan |
| `POST` | `/stage1/plan` | `preview_plan` | Optional | `GenerateRequest` | `PlanPreviewResponse` | Alias for `/plan` |
| `POST` | `/generate` | `generate_presentation` | Optional | `GenerateRequest` | `GenerateResponse` | **Stage 2**: Compile plan into `.pptx` deck |
| `POST` | `/stage2/generate`| `generate_presentation` | Optional | `GenerateRequest` | `GenerateResponse` | Alias for `/generate` |
| `POST` | `/save` | `save_presentation_endpoint`| Optional| `PresentationPlan` | `SaveResponse` | Re-renders and updates stored presentation |
| `POST` | `/refine-slide` | `refine_slide_text` | Optional | `RefineSlideRequest` | `RefineSlideResponse` | AI slide rewording (expand/summarize/professionalize) |
| `GET` | `/download/{file_name}` | `download_ppt` | Public | Path param: `file_name` | `FileResponse` (`.pptx`) | Stream compiled PowerPoint binary |
| `GET` | `/download-presentation/{presentation_id}` | `download_presentation_by_id` | Optional | Path param: `presentation_id` | `FileResponse` (`.pptx`) | Download deck by presentation UUID |
| `POST` | `/voiceover/synthesize` | `synthesize_voiceover_endpoint` | Optional | `VoiceoverRequest` | `{"status": "success", "audio_urls": [...]}` | Generate slide narration audio via Edge-TTS |
| `GET` | `/voiceover/audio/{file_name}` | `stream_voiceover_audio` | Public | Path param: `file_name` | `FileResponse` (`audio/mpeg`) | Stream synthesized narration MP3 |
| `GET` | `/brand-profile` | `get_brand_profile_endpoint` | Required | None | `BrandProfileResponse` | Retrieve user brand styling profile |
| `POST` | `/brand-profile` | `save_brand_profile_endpoint` | Required | `BrandProfileCreate` | `BrandProfileResponse` | Update user brand logo, colors, and typography |
| `GET` | `/list` | `list_user_presentations` | Required | None | `List[dict]` | Retrieve all saved user presentations |
| `GET` | `/my-presentations`| `list_user_presentations` | Required | None | `List[dict]` | Alias for `/list` |
| `GET` | `/{presentation_id}` | `get_presentation_details` | Optional | Path param: `presentation_id` | `PresentationDetailResponse` | Get full JSON slide specification of a deck |
| `PUT` | `/{presentation_id}` | `update_presentation_endpoint` | Required | `PresentationPlan` | `SaveResponse` | Update existing presentation deck |
| `DELETE` | `/{presentation_id}` | `delete_presentation_endpoint` | Required | Path param: `presentation_id` | `{"status": "deleted"}` | Delete stored presentation deck |
| `GET` | `/images/search` | `search_presentation_images_api` | Public | Query: `query, page, page_size, provider` | `List[ImageResult]` | Multi-source image search (Unsplash/Openverse/Wiki) |
| `POST` | `/images/suggest` | `suggest_presentation_images_api` | Public | `ImageSuggestRequest` | `ImageSuggestResponse` | AI recommended images matching slide content |
| `GET` | `/unsplash/photos` | `get_unsplash_photos_api` | Public | Query: `query, per_page` | `List[dict]` | Direct Unsplash image search |
| `POST` | `/ai-image/generate` | `generate_ai_image_api` | Public | `AIImageGenerateRequest` | `AIImageGenerateResponse` | Generative image creation via Pollinations AI |
| `POST` | `/cleanup` | `trigger_manual_cleanup` | Public | None | `{"status": "cleaned", ...}` | Purge expired temporary output files |

---

## 2. Module 2: Dora Dr. Endpoints

**Base Path**: `/api/dora`  
**Router Module**: `backend/dora/routes.py`

| Method | Path | Function | Auth | Request Body / Params | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/` | `dora_info` | Public | None | `{"status": "active", "total_symptoms": 132, ...}` | Engine status, model metadata, dataset stats |
| `GET` | `/symptoms` | `get_symptoms` | Public | Query: `query: Optional[str]` | `{"status": "success", "symptoms": [...]}` | List 130+ clinical symptoms |
| `GET` | `/diseases` | `get_diseases` | Public | None | `{"status": "success", "diseases": [...]}` | List 40+ classifiable diseases |
| `POST` | `/predict` | `predict_disease_endpoint` | Public | `SymptomsRequest` | `{"predicted_disease": str, "possible_diseases": [...]}` | Scikit-learn disease prediction with confidence |
| `POST` | `/chat` | `ai_health_chat` | Public | `ChatRequest` | `{"reply": str, "emergency": bool, ...}` | Medical triage chat with emergency guardrails |
| `POST` | `/health-assessment` | `calculate_health_assessment`| Public | `HealthAssessmentRequest` | `{"bmi": float, "category": str, "risk_factors": [...]}` | Comprehensive lifestyle and metabolic assessment |

---

## 3. Module 3: Vidya F.E.I Advisor Endpoints

### A. Income Management (`/api/income`)
**Router Module**: `backend/finance/routes/income.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/` | `add_income` | Required | `IncomeCreate` | `IncomeResponse` | Record new income entry |
| `GET` | `/` | `get_all_income` | Required | None | `List[IncomeResponse]` | List all incomes for current user |
| `GET` | `/{income_id}` | `get_income` | Required | Path param | `IncomeResponse` | Retrieve single income entry |
| `PUT` | `/{income_id}` | `update_income` | Required | `IncomeUpdate` | `IncomeResponse` | Update income entry |
| `DELETE` | `/{income_id}` | `delete_income` | Required | Path param | `{"message": "Income deleted"}` | Delete income entry |

### B. Expense Management (`/api/expense`)
**Router Module**: `backend/finance/routes/expense.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/` | `add_expense` | Required | `ExpenseCreate` | `ExpenseResponse` | Record new expense entry |
| `GET` | `/` | `get_all_expenses` | Required | None | `List[ExpenseResponse]` | List all expenses for current user |
| `GET` | `/{expense_id}` | `get_expense` | Required | Path param | `ExpenseResponse` | Retrieve single expense entry |
| `PUT` | `/{expense_id}` | `update_expense` | Required | `ExpenseUpdate` | `ExpenseResponse` | Update expense entry |
| `DELETE` | `/{expense_id}` | `delete_expense` | Required | Path param | `{"message": "Expense deleted"}` | Delete expense entry |

### C. Financial Telemetry & Ledgers (`/api/vitya`)
**Router Module**: `backend/finance/routes/vitya.py`

| Method | Path | Function | Auth | Request Body / Params | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/financial_overview` | `get_financial_overview` | Required | None | `dict` (totals, savings, net) | High-level ledger balance metrics |
| `GET` | `/expenses_chart` | `get_expenses_chart` | Required | None | `dict` (category breakdowns) | Category expense aggregation |
| `GET` | `/expense_income_trend`| `get_expense_income_trend`| Required| None | `dict` (monthly timelines) | Monthly income vs expense comparison |
| `GET` | `/transactions/recent` | `get_recent_transactions`| Required | None | `List[dict]` | Combined 10 most recent transactions |
| `GET` | `/graph` | `get_expense_graph` | Required | None | `StreamingResponse` (PNG) | Matplotlib generated visual expense chart |
| `GET` | `/export/csv` | `download_financial_csv` | Required | Query: `type=expenses|income`| `StreamingResponse` (CSV) | Export transactions to CSV |
| `GET` | `/csv/expenses` | `download_expenses_csv` | Required | None | `StreamingResponse` (CSV) | Expenses-only CSV export |
| `GET` | `/csv/incomes` | `download_incomes_csv` | Required | None | `StreamingResponse` (CSV) | Incomes-only CSV export |

### D. AI Financial Intelligence (`/api/analyse` & `/api/ai`)
**Router Module**: `backend/finance/analysis/analyse.py`

*Note: The frontend expects `/api/ai/*` for predictive endpoints, while the backend mounts it at `/api/analyse`. Both prefixes are supported for full backwards-compatibility.*

| Method | Path | Function | Auth | Request / Params | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/predict/{category}` | `predict_expense` | Required | Path param: `category` | `dict` | Linear regression future expense forecasting |
| `GET` | `/overspending/{category}`| `detect_overspending` | Required | Path param: `category` | `dict` | Category spend analysis vs budget cap |
| `GET` | `/waste-analysis` | `waste_analysis` | Required | None | `dict` | Redundant and wasteful expense identification |
| `GET` | `/budget-plan` | `budget_plan` | Required | None | `dict` | AI recommended 50/30/20 budget breakdown |
| `GET` | `/advisor/{category}` | `financial_advisor` | Required | Path param: `category` | `dict` | Targeted category savings optimization advice |
| `GET` | `/monthly-trend` | `monthly_trend` | Required | None | `dict` | Month-over-month rate of spend change |
| `GET` | `/anomaly/{category}` | `anomaly_detection` | Required | Path param: `category` | `dict` | Statistical anomaly detection (> 2x std dev) |
| `POST` | `/budget-cap` | `create_or_update_budget_cap`| Required| `BudgetCreate` | `BudgetResponse` | Set or update monthly category budget cap |
| `GET` | `/budget-cap` | `get_user_budget_caps` | Required | None | `List[BudgetResponse]` | List user active category budgets |
| `GET` | `/budget-alerts` | `get_budget_alerts` | Required | None | `List[BudgetAlertStatus]` | Warning alerts for categories reaching > 80% cap |
| `GET` | `/health-score` | `get_financial_health_score` | Required | None | `FinancialHealthScoreResponse` | 0–100 composite Financial Health Score |
| `GET` | `/executive-summary` | `get_financial_executive_summary`| Required| None | `FinancialExecutiveSummaryResponse` | Gemini fiduciary AI executive briefing |

### E. Savings Goals (`/api/savings`)
**Router Module**: `backend/finance/analysis/savings.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/` | `get_savings_goals` | Required | None | `List[SavingsGoalResponse]` | List all user savings targets |
| `POST` | `/` | `create_savings_goal` | Required | `SavingsGoalCreate` | `SavingsGoalResponse` | Create new target savings goal |
| `GET` | `/{goal_id}` | `get_single_savings_goal` | Required | Path param | `SavingsGoalResponse` | Retrieve single savings goal |
| `PUT` | `/{goal_id}` | `update_savings_goal` | Required | `SavingsGoalUpdate` | `SavingsGoalResponse` | Update savings goal target or title |
| `DELETE` | `/{goal_id}` | `delete_savings_goal` | Required | Path param | `{"status": "deleted"}` | Delete savings goal |
| `POST` | `/{goal_id}/deposit` | `deposit_to_savings_goal` | Required | `{"amount": float}` | `SavingsGoalResponse` | Add funds towards goal target |

### F. Recurring Subscriptions (`/api/subscriptions`)
**Router Module**: `backend/api/routes/subscriptions.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/` | `get_subscriptions` | Required | None | `List[SubscriptionResponse]` | List all active recurring commitments |
| `POST` | `/` | `create_subscription` | Required | `SubscriptionCreate` | `SubscriptionResponse` | Register new recurring subscription |
| `GET` | `/summary` | `get_subscriptions_summary` | Required | None | `SubscriptionSummaryResponse` | Monthly and annual subscription cost totals |
| `GET` | `/{subscription_id}` | `get_single_subscription` | Required | Path param | `SubscriptionResponse` | Retrieve single subscription |
| `PUT` | `/{subscription_id}` | `update_subscription` | Required | `SubscriptionUpdate` | `SubscriptionResponse` | Update subscription cycle or cost |
| `DELETE` | `/{subscription_id}` | `delete_subscription` | Required | Path param | `{"status": "deleted"}` | Cancel or delete subscription |

---

## 4. Shared Platform Core Endpoints

### A. Users & Authentication (`/api/users`)
**Router Module**: `backend/api/routes/users.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/register` | `register` | Public | `Register` | `UserResponse` | User account registration |
| `GET` | `/register` | `get_register` | Public | None | `dict` | Registration requirements schema |
| `POST` | `/login` | `login` | Public | `Login` | `{"token": str, "user": dict}` | User authentication; returns JWT token |
| `GET` | `/profile` | `get_profile` | Required | None | `UserResponse` | Retrieve current authenticated user profile |
| `PUT` | `/profile/edit` | `update_profile` | Required | `UserUpdate` | `UserResponse` | Update user name, avatar, or bio |
| `POST` | `/forgot-password` | `forgot_password` | Public | `ForgotPasswordRequest`| `{"message": str}` | Issue 15-minute password reset token |
| `POST` | `/reset-password` | `reset_password` | Public | `ResetPasswordRequest` | `{"message": str}` | Update password using reset token |
| `POST` | `/support` | `submit_support_ticket` | Optional | `SupportTicketCreate` | `SupportTicketResponse` | Submit customer support ticket |
| `GET` | `/export-data` | `export_user_data` | Required | None | `dict` | GDPR-compliant full user data JSON dump |

### B. User Settings & Subscriptions (`/api/settings`)
**Router Module**: `backend/api/routes/settings.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/` | `get_user_settings` | Required | None | `UserSettingsResponse` | Retrieve user preferences and themes |
| `PUT` | `/` | `update_user_settings` | Required | `UserSettingsUpdate` | `UserSettingsResponse` | Update user appearance and notifications |
| `POST` | `/change-password` | `change_password` | Required | `ChangePasswordRequest` | `{"message": str}` | Update account password |
| `GET` | `/subscription` | `get_subscription` | Required | None | `dict` | Fetch active subscription tier |
| `POST` | `/subscription/select`| `select_subscription` | Required | `SubscriptionPlanRequest`| `dict` | Upgrade or switch subscription tier |

### C. Conversational Chat & Intent Dispatcher (`/api/chat`)
**Router Module**: `backend/chats/chat.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/` | `chat` | Optional | `ChatRequest` | `ChatResponse` | Master conversational interface with intent router |
| `POST` | `/multimodal` | `multimodal_chat` | Optional | Multipart form (`files`, `message`) | `ChatResponse` | Multimodal chat with image vision reasoning |
| `POST` | `/receipt` | `scan_receipt_chat` | Optional | Multipart form (`file`) | `dict` | Extract and parse receipt items via OCR |
| `GET` | `/history` | `get_chat_history` | Required | Query: `conversation_id, limit, offset` | `List[ChatMessageResponse]` | Retrieve historical conversation turns |
| `GET` | `/conversations` | `get_conversations` | Required | Query: `limit` | `List[dict]` | List all conversation sessions |
| `POST` | `/new` | `create_new_conversation`| Required | None | `{"id": int, "title": str}` | Initialize fresh conversation session |
| `PUT` | `/conversation/{id}` | `update_conversation_title`| Required| `ConversationUpdate` | `dict` | Rename conversation thread |
| `DELETE` | `/conversation/{id}` | `delete_single_conversation`| Required| Path param: `id` | `{"status": "deleted"}` | Delete single conversation thread |
| `DELETE` | `/history` | `clear_chat_history` | Required | None | `{"status": "cleared"}` | Purge all user conversation history |

### D. Shared Productivity Apps (`/api/notes`, `/api/tasks`, `/api/calendar`)
**Router Modules**: `backend/api/WebApp/*`

| Router Prefix | Method | Path | Function | Auth | Description |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `/api/notes` | `GET` | `/` | `get_notes` | Required | List all user notes |
| `/api/notes` | `POST` | `/` | `create_note` | Required | Create new note |
| `/api/notes` | `PUT` | `/{note_id}` | `update_note` | Required | Update existing note |
| `/api/notes` | `DELETE` | `/{note_id}` | `delete_note` | Required | Delete note |
| `/api/tasks` | `GET` | `/` | `get_tasks` | Required | List all tasks |
| `/api/tasks` | `POST` | `/` | `create_task` | Required | Create new task |
| `/api/tasks` | `PUT` | `/{task_id}` | `update_task` | Required | Update task status or title |
| `/api/tasks` | `DELETE` | `/{task_id}` | `delete_task` | Required | Delete task |
| `/api/calendar` | `GET` | `/` | `get_calendar_events` | Required | List all calendar events |
| `/api/calendar` | `POST` | `/` | `create_calendar_event` | Required | Create calendar event |
| `/api/calendar` | `PUT` | `/{event_id}` | `update_calendar_event` | Required | Update event details |
| `/api/calendar` | `DELETE` | `/{event_id}` | `delete_calendar_event` | Required | Delete calendar event |

### E. Document RAG Management (`/api/rag`)
**Router Module**: `backend/chats/routes/rag_routes.py`

| Method | Path | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/upload` | `upload_rag_documents` | Optional | Multipart form (`files`) | `{"status": "indexed", ...}` | Ingest and chunk text/csv/pdf documents |
| `GET` | `/documents` | `get_rag_documents` | Optional | None | `List[dict]` | List currently indexed documents in memory |
| `DELETE` | `/documents` | `clear_rag_documents` | Optional | None | `{"status": "cleared"}` | Clear in-memory RAG index |

### F. System Root & Health
| Method | Path | Function | Auth | Description |
| :--- | :--- | :--- | :---: | :--- |
| `GET` | `/` | `root` | Public | Service heartbeat: `{"message": "API is running 🚀"}` |
| `GET` | `/health` | `health` | Public | Health probe: `{"status": "ok"}` |
| `HEAD` | `/health` | `health_head` | Public | Cloud load balancer 200 OK ping |
