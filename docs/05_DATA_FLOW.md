# 05 - End-to-End Data & Event Flows

This document details the complete step-by-step lifecycle of key data operations within the MOTHER backend.

---

## 1. Presentation Generation Pipeline Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Client / User
    participant API as /api/presentation/generate
    participant Planner as PromptPlanner (planner.py)
    participant LLM as Google Gemini (gemini_service)
    participant ImgMgr as ImageManager (image_service)
    participant Geom as LayoutResolver (geometry.py)
    participant Shapes as ShapeEngine (shapes.py)
    participant Renderer as PptRenderer (ppt_renderer.py)
    participant Exporter as Exporter (exporter.py)
    participant Store as PresentationStore (store.py)

    User->>API: POST /stage2/generate (topic, slides_count, theme, visual_style)
    API->>Planner: plan_presentation(prompt, options)
    Planner->>LLM: Generate StructuredPresentationPlan (JSON Schema)
    LLM-->>Planner: Structured JSON (Slides, Layouts, Content, Intents)
    Planner->>ImgMgr: ensure_plan_images(plan)
    ImgMgr->>ImgMgr: Query Unsplash / Openverse / Wikimedia
    ImgMgr-->>Planner: Enriched plan with image URLs & attributions
    Planner-->>API: PresentationPlan object
    API->>Geom: MixedLayoutResolver.resolve_layouts(plan)
    Geom-->>API: Resolved Box coordinates & element grids
    API->>Shapes: DecorativeShapeEngine.decorate_slides(plan)
    Shapes-->>API: ShapeSpecs injected into slides
    API->>Renderer: PptRenderer.render(plan)
    Renderer->>Renderer: Instantiate 21 content plugins & draw elements
    Renderer-->>Exporter: python-pptx Presentation object
    Exporter->>Exporter: Save to outputs/<uuid>.pptx
    API->>Store: save_presentation(plan, file_url)
    API-->>User: GenerateResponse (presentation_id, download_url, plan)
```

---

## 2. Conversational Intent & Multi-Agent Dispatch Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Authenticated User
    participant Router as /api/chat (chat.py)
    participant DORA as dora_handler.py
    participant TXN as transaction_handler.py
    participant CHART as chart_handler.py
    participant FILE as file_handler.py
    participant INFO as info_handler.py
    participant LLM as chatbot_handler.py (Gemini)
    participant DB as PostgreSQL (SQLAlchemy)

    User->>Router: POST /api/chat {"message": "I spent $50 on Groceries today"}
    Router->>DB: Fetch recent conversation history
    
    alt Medical Query Detected
        Router->>DORA: handle_dora_health(message)
        DORA->>DORA: Extract symptoms & run KnowledgeEngine
        DORA-->>Router: Clinical assessment reply
    else Transaction Intent Detected
        Router->>TXN: handle_transaction(message, user_id, db)
        TXN->>DB: Insert into Expense(amount=50, category="Groceries")
        TXN-->>Router: "Expense of $50 for Groceries recorded."
    else Chart / Visualization Intent
        Router->>CHART: handle_chart_request(message, user_id, db)
        CHART->>DB: Query monthly aggregates
        CHART-->>Router: Formatted Chart data payload
    else Document Export Intent
        Router->>FILE: handle_file_request(message, user_id, db)
        FILE->>FILE: Compile CSV/PDF/DOCX
        FILE-->>Router: Download URL link
    else Live Web / Weather Intent
        Router->>INFO: handle_info_request(message)
        INFO->>INFO: Fetch DuckDuckGo or OpenWeather
        INFO-->>Router: Real-time search context reply
    else General Knowledge / LLM Fallback
        Router->>LLM: handle_chatbot(message, history)
        LLM-->>Router: Gemini synthesized response
    end

    Router->>DB: Save User & Assistant ChatMessage records
    Router-->>User: ChatResponse {"reply": "..."}
```

---

## 3. Financial Analytics & AI Health Score Flow

1. **User requests health score**: `GET /api/ai/health-score`
2. **Data Aggregation**:
   - Fetches all user `Income` records.
   - Fetches all user `Expense` records.
   - Fetches all active `Budget` limits.
   - Fetches active `RecurringSubscription` totals.
3. **Metric Computation** (`compute_financial_health_score`):
   - $	ext{Savings Rate} = rac{	ext{Total Income} - 	ext{Total Expense}}{	ext{Total Income}} 	imes 100$
   - $	ext{Expense Ratio} = rac{	ext{Total Expense}}{	ext{Total Income}} 	imes 100$
   - $	ext{Budget Adherence} = 100 - 	ext{Average Percent Exceeded Across Caps}$
   - $	ext{Subscription Ratio} = rac{	ext{Committed Monthly Subscriptions}}{	ext{Total Monthly Income}} 	imes 100$
4. **Weighted Composite Score**:
   - $Score = 0.35(	ext{Savings}) + 0.25(	ext{Budget Adherence}) + 0.25(100 - 	ext{Expense Ratio}) + 0.15(100 - 	ext{Sub Ratio})$
5. **Output**: Grade assignment (`Excellent`, `Good`, `Fair`, `Needs Attention`) + actionable AI recommendations.