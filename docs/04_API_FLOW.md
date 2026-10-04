# 04 - API Endpoint Catalog & Flow

This document details every registered endpoint in the MOTHER backend application.

---

## 1. Users & Authentication Router (`/api/users`)
**Router**: `backend.api.routes.users.router`

| Method | Endpoint | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/register` | `register` | None | `Register` | `UserResponse` | Registers new user account with hashed password |
| `GET` | `/register` | `get_register` | None | None | `dict` | Helper endpoint returning registration requirements |
| `POST` | `/login` | `login` | None | `Login` | `dict` (token, user) | Validates credentials and returns JWT bearer token |
| `GET` | `/profile` | `get_profile` | Required | None | `UserResponse` | Fetches currently authenticated user profile |
| `PUT` | `/profile/edit` | `update_profile` | Required | `UserUpdate` | `UserResponse` | Updates user details, avatar, or bio |
| `POST` | `/forgot-password`| `forgot_password`| None | `ForgotPasswordRequest` | `dict` | Generates 15-min password reset token |
| `POST` | `/reset-password` | `reset_password` | None | `ResetPasswordRequest` | `dict` | Resets password using valid reset token |
| `POST` | `/support` | `submit_support_ticket`| Optional | `SupportTicketCreate` | `SupportTicketResponse` | Submits user support ticket |
| `GET` | `/export-data` | `export_user_data` | Required | None | `dict` (Full Dump) | GDPR compliant export of all user transactions, notes & settings |

---

## 2. Income Router (`/api/income`)
**Router**: `backend.api.routes.income.router`

| Method | Endpoint | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/` | `add_income` | Required | `IncomeCreate` | `IncomeResponse` | Adds new income transaction |
| `GET` | `/` | `get_all_income` | Required | None | `List[IncomeResponse]` | Lists all incomes for authenticated user |
| `GET` | `/{income_id}` | `get_income` | Required | None | `IncomeResponse` | Retrieves single income entry |
| `PUT` | `/{income_id}` | `update_income` | Required | `IncomeUpdate` | `IncomeResponse` | Updates specified income entry |
| `DELETE` | `/{income_id}` | `delete_income` | Required | None | `dict` | Deletes specified income entry |

---

## 3. Expense Router (`/api/expense`)
**Router**: `backend.api.routes.expense.router`

| Method | Endpoint | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/` | `add_expense` | Required | `ExpenseCreate` | `ExpenseResponse` | Creates new expense transaction |
| `GET` | `/` | `get_all_expenses` | Required | None | `List[ExpenseResponse]` | Lists all user expenses |
| `GET` | `/{expense_id}`| `get_expense` | Required | None | `ExpenseResponse` | Retrieves single expense entry |
| `PUT` | `/{expense_id}`| `update_expense` | Required | `ExpenseUpdate` | `ExpenseResponse` | Updates specified expense entry |
| `DELETE` | `/{expense_id}`| `delete_expense` | Required | None | `dict` | Deletes specified expense entry |

---

## 4. Financial Analytics & Export Router (`/api/vitya`)
**Router**: `backend.api.routes.vitya.router`

| Method | Endpoint | Function | Auth | Response Type | Description |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `GET` | `/export/csv` | `download_financial_csv` | Required | `StreamingResponse` (CSV) | Combined income & expense CSV |
| `GET` | `/csv/expenses` | `download_expenses_csv` | Required | `StreamingResponse` (CSV) | Expenses-only CSV export |
| `GET` | `/csv/incomes` | `download_incomes_csv` | Required | `StreamingResponse` (CSV) | Incomes-only CSV export |
| `GET` | `/expenses_chart` | `get_expenses_chart` | Required | `dict` (Category breakdown) | Expense breakdown for charting |
| `GET` | `/financial_overview`| `get_financial_overview` | Required | `dict` (Totals, net, stats) | High-level summary metrics |
| `GET` | `/expense_income_trend`| `get_expense_income_trend`| Required | `dict` (Monthly timelines) | Trend comparison over time |
| `GET` | `/graph` | `get_expense_graph` | Required | `StreamingResponse` (PNG) | Matplotlib generated chart image |
| `GET` | `/transactions/recent`| `get_recent_transactions`| Required | `List[dict]` | Combined recent feed of 10 items |

---

## 5. AI Financial Intelligence Router (`/api/ai`)
**Router**: `backend.api.routes.ai.router`

| Method | Endpoint | Function | Auth | Request/Params | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/predict/{category}` | `predict_expense` | Required | `category: str` | `dict` | Predicts next month's category expense via Linear Regression |
| `GET` | `/overspending/{category}`| `detect_overspending` | Required | `category: str` | `dict` | Analyzes spend vs monthly budget limit |
| `GET` | `/waste-analysis` | `waste_analysis` | Required | None | `dict` | Detects redundant or wasteful subscriptions/spending |
| `GET` | `/budget-plan` | `budget_plan` | Required | None | `dict` | AI recommended 50/30/20 budget breakdown |
| `GET` | `/advisor/{category}` | `financial_advisor` | Required | `category: str` | `dict` | Category optimization advice |
| `GET` | `/monthly-trend` | `monthly_trend` | Required | None | `dict` | Month-over-month rate of spend |
| `GET` | `/anomaly/{category}` | `anomaly_detection` | Required | `category: str` | `dict` | Identifies statistical anomalies (> 2x std dev) |
| `POST` | `/budget-cap` | `create_or_update_budget_cap`| Required| `BudgetCreate` | `BudgetResponse` | Sets or updates category monthly budget limit |
| `GET` | `/budget-cap` | `get_user_budget_caps` | Required | None | `List[BudgetResponse]` | Lists all active category budgets |
| `GET` | `/budget-alerts` | `get_budget_alerts` | Required | None | `List[BudgetAlertStatus]` | Returns warning alerts for categories > 80% limit |
| `GET` | `/health-score` | `get_financial_health_score` | Required | None | `FinancialHealthScoreResponse`| 0-100 composite financial health score |
| `GET` | `/executive-summary` | `get_financial_executive_summary`| Required| None | `FinancialExecutiveSummaryResponse`| Gemini LLM generated executive report |

---

## 6. Conversational Chat Router (`/api/chat`)
**Router**: `backend.chats.chat.router`

| Method | Endpoint | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/` or `` | `chat` | Optional | `ChatRequest` | `ChatResponse` | Main conversational endpoint with intent routing |
| `GET` | `/history` | `get_chat_history` | Required | `conversation_id: Optional[int]` | `List[ChatMessageResponse]`| Fetches chat messages for current or specific session |
| `GET` | `/conversations` | `get_conversations` | Required | None | `List[dict]` | Lists all user conversation sessions |
| `POST` | `/new` | `create_new_conversation` | Required | None | `dict` (id, title) | Spawns fresh conversation session |
| `DELETE` | `/history` | `clear_chat_history` | Required | None | `dict` | Deletes all conversations for current user |
| `DELETE` | `/conversation/{conversation_id}`| `delete_single_conversation`| Required| `conversation_id: int` | `dict` | Deletes single conversation thread |

---

## 7. Presentation Engine Router (`/api/presentation`)
**Router**: `backend.chats.presentation.presentation_api.router`

| Method | Endpoint | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/health` | `health` | None | None | `dict` | Presentation engine status check |
| `GET` | `/templates` | `get_templates` | None | None | `dict` | Returns catalog of 14 theme presets |
| `GET` | `/shapes/catalog` | `get_shapes_catalog` | None | None | `dict` | Returns visual shape & badge primitives |
| `POST` | `/plan` & `/stage1/plan` | `preview_plan` | Optional | `GenerateRequest` | `PlanPreviewResponse` | **Stage 1**: Generates slide specifications without rendering PPTX |
| `POST` | `/generate` & `/stage2/generate` | `generate_presentation` | Optional | `GenerateRequest` | `GenerateResponse` | **Stage 2**: Full planning + PPTX compilation |
| `POST` | `/save` | `save_presentation_endpoint`| Optional | `PresentationPlan` | `SaveResponse` | Re-renders and saves edited `PresentationPlan` |
| `POST` | `/refine-slide` | `refine_slide_text` | Optional | `RefineSlideRequest` | `RefineSlideResponse` | AI slide text rewording (summarize, expand, professionalize) |
| `GET` | `/download/{file_name}`| `download_ppt` | None | Path param | `FileResponse` | Streams generated PPTX file |
| `GET` | `/download-presentation/{presentation_id}`| `download_presentation_by_id`| Optional | Path param | `FileResponse` | Downloads PPTX by presentation UUID |
| `POST` | `/voiceover/synthesize`| `synthesize_voiceover_endpoint`| Optional| `VoiceoverRequest` | `dict` (audio URLs) | Generates MP3 slide narration audio via Edge-TTS |
| `GET` | `/voiceover/audio/{file_name}`| `stream_voiceover_audio`| None | Path param | `FileResponse` (MP3) | Streams synthesized narration audio |
| `GET` | `/brand-profile` | `get_brand_profile_endpoint`| Required | None | `BrandProfileResponse` | Retrieves user's custom presentation brand profile |
| `POST` | `/brand-profile` | `save_brand_profile_endpoint`| Required | `BrandProfileCreate` | `BrandProfileResponse` | Saves custom brand colors, logo, and fonts |
| `GET` | `/list` & `/my-presentations`| `list_user_presentations`| Required | None | `List[dict]` | Lists user's saved presentations |
| `GET` | `/{presentation_id}` | `get_presentation_details` | Optional | Path param | `PresentationDetailResponse`| Retrieves presentation JSON structure |
| `PUT` | `/{presentation_id}` | `update_presentation_endpoint`| Required | `PresentationPlan` | `SaveResponse` | Updates stored presentation structure |
| `DELETE` | `/{presentation_id}` | `delete_presentation_endpoint`| Required | Path param | `dict` | Deletes stored presentation |
| `GET` | `/images/search` | `search_presentation_images_api`| None | `query: str` | `List[ImageResult]` | Multi-source image search (Unsplash/Openverse/Wikimedia) |
| `POST` | `/images/suggest` | `suggest_presentation_images_api`| None | `ImageSuggestRequest` | `ImageSuggestResponse` | AI suggested images tailored to slide content |
| `GET` | `/unsplash/photos` | `get_unsplash_photos_api` | None | `query: str` | `List[dict]` | Direct Unsplash image search |
| `GET` | `/ai-image/generate` | `generate_ai_image_api` | None | `prompt: str` | `dict` (image_url) | Generates AI image via Pollinations AI |
| `POST` | `/cleanup` | `trigger_manual_cleanup` | None | None | `dict` | Triggers manual temporary file purge |

---

## 8. DORA Health Router (`/api/dora`)
**Router**: `backend.dora.routes.router`

| Method | Endpoint | Function | Auth | Request Body | Response Schema | Description |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/` | `dora_info` | None | None | `dict` | Returns DORA ML engine metadata and status |
| `GET` | `/symptoms` | `get_symptoms` | None | None | `dict` (List[str]) | Returns all 130+ supported clinical symptoms |
| `GET` | `/diseases` | `get_diseases` | None | None | `dict` (List[str]) | Returns all 40+ classifiable diseases |
| `POST` | `/predict` | `predict_disease_endpoint` | None | `SymptomsRequest` | `dict` | Predicts probable diseases and confidence |
| `POST` | `/chat` | `ai_health_chat` | None | `ChatRequest` | `dict` | Conversational medical guidance with emergency screening |
| `POST` | `/health-assessment`| `calculate_health_assessment`| None | `HealthAssessmentRequest`| `dict` | Comprehensive risk assessment & department referral |

---

## 9. WebApp & Settings Routers

### Notes (`/api/notes`)
- `GET /` -> `get_notes` (List notes)
- `POST /` -> `create_note` (Create note)
- `PUT /{note_id}` -> `update_note` (Update note)
- `DELETE /{note_id}` -> `delete_note` (Delete note)

### Tasks (`/api/tasks`)
- `GET /` -> `get_tasks` (List tasks)
- `POST /` -> `create_task` (Create task)
- `PUT /{task_id}` -> `update_task` (Update task)
- `DELETE /{task_id}` -> `delete_task` (Delete task)

### Calendar (`/api/calendar`)
- `GET /` -> `get_calendar_events` (List events)
- `POST /` -> `create_calendar_event` (Create event)
- `PUT /{event_id}` -> `update_calendar_event` (Update event)
- `DELETE /{event_id}` -> `delete_calendar_event` (Delete event)

### Settings & Preferences (`/api/settings`)
- `GET /` -> `get_user_settings` (Fetch UI/Theme settings)
- `PUT /` -> `update_user_settings` (Update preferences)
- `POST /change-password` -> `change_password` (Update account password)
- `GET /subscription` -> `get_subscription` (Fetch active subscription plan)
- `POST /subscription/select` -> `select_subscription` (Switch subscription tier)

### Savings Goals (`/api/savings`)
- `GET /` -> `get_savings_goals` (List user goals)
- `POST /` -> `create_savings_goal` (Create savings target)
- `GET /{goal_id}` -> `get_single_savings_goal` (Fetch goal by ID)
- `PUT /{goal_id}` -> `update_savings_goal` (Modify target amount or date)
- `DELETE /{goal_id}` -> `delete_savings_goal` (Remove savings goal)
- `POST /{goal_id}/deposit` -> `deposit_to_savings_goal` (Add funds toward target)

### Recurring Subscriptions (`/api/subscriptions`)
- `GET /` -> `get_subscriptions` (List active subscriptions)
- `POST /` -> `create_subscription` (Create recurring commitment)
- `GET /summary` -> `get_subscriptions_summary` (Monthly/Yearly totals)
- `GET /{subscription_id}` -> `get_single_subscription` (Fetch subscription)
- `PUT /{subscription_id}` -> `update_subscription` (Modify cycle or cost)
- `DELETE /{subscription_id}` -> `delete_subscription` (Cancel/delete subscription)

### RAG Document Management (`/api/rag`)
- `POST /upload` -> `upload_rag_documents` (Upload TXT/CSV/PDF for semantic RAG)
- `GET /documents` -> `get_rag_documents` (List indexed documents)
- `DELETE /documents` -> `clear_rag_documents` (Purge RAG index)