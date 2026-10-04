# 06 - Database Architecture & Schema Reference

The MOTHER backend uses **SQLAlchemy 2.0 ORM** supporting PostgreSQL (production) with automatic SQLite fallback (development).

---

## 1. Engine & Session Management (`backend/api/database.py`)
- **Connection URL Resolution**: `SUPABASE_DATABASE_URL` -> `DATABASE_URL` -> `sqlite:///./instance/app.db`
- **Legacy URL Normalization**: Automatically replaces `postgres://` with `postgresql://`.
- **Connection Pool Configuration (PostgreSQL)**:
  - `pool_pre_ping=True` (Validates connection health before checkout)
  - `pool_recycle=1800` (Recycles connections after 30 minutes)
  - `pool_size=5`
  - `max_overflow=10`
- **Session Lifecycle**: `get_db()` FastAPI dependency yielding `SessionLocal()`, guaranteeing rollback on uncaught exceptions and `session.close()` on request completion.

---

## 2. Complete Entity Model Specifications (`backend/api/models/vitya.py`)

### 1. `TimestampMixin`
Abstract base columns added to all models:
- `created_at`: `DateTime(timezone=True)`, server default `func.now()`, non-nullable.
- `updated_at`: `DateTime(timezone=True)`, server default `func.now()`, onupdate `func.now()`, non-nullable.

---

### 2. `User` (`__tablename__ = "users"`)
Core user entity managing identity, authentication, and owning all personal data.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique user ID |
| `name` | `String(100)` | Non-nullable | User full name |
| `username` | `String(50)` | Unique, Index, Non-nullable | Unique handle |
| `email` | `String(255)`| Unique, Index, Non-nullable | Verified email |
| `password` | `String(255)`| Non-nullable | Bcrypt password hash |
| `profile_pic` | `String(500)`| Nullable | Path or URL to avatar |
| `bio` | `Text` | Nullable | Biography text |

**Relationships (Cascading `all, delete-orphan`, `passive_deletes=True`)**:
- `incomes`: One-to-Many -> `Income`
- `expenses`: One-to-Many -> `Expense`
- `conversations`: One-to-Many -> `Conversation`
- `sent_messages`: One-to-Many -> `Message` (`sender_id`)
- `received_messages`: One-to-Many -> `Message` (`receiver_id`)
- `notes`: One-to-Many -> `Note`
- `tasks`: One-to-Many -> `Task`
- `budgets`: One-to-Many -> `Budget`
- `calendar_events`: One-to-Many -> `CalendarEvent`
- `settings`: One-to-One -> `UserSettings` (`uselist=False`)
- `brand_profile`: One-to-One -> `PresentationBrand` (`uselist=False`)
- `savings_goals`: One-to-Many -> `SavingsGoal`
- `subscriptions`: One-to-Many -> `RecurringSubscription`

---

### 3. `Income` (`__tablename__ = "income"`)
Records user revenue streams.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique income ID |
| `amount` | `Float` | Non-nullable | Monetary amount |
| `source` | `String(100)`| Non-nullable | Source name (Salary, Freelance, etc.) |
| `date` | `DateTime(timezone=True)`| Server default `now()`, Non-nullable | Transaction date |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`) | Owner user ID |

---

### 4. `Expense` (`__tablename__ = "expense"`)
Records user expenditure transactions.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique expense ID |
| `amount` | `Float` | Non-nullable | Monetary amount spent |
| `category` | `String(100)`| Non-nullable | Expense category (Food, Rent, etc.) |
| `description` | `String(255)`| Nullable | Transaction memo |
| `date` | `DateTime(timezone=True)`| Server default `now()`, Non-nullable | Date of expense |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`) | Owner user ID |

---

### 5. `Budget` (`__tablename__ = "budgets"`)
Category budget limits for overspending alerts.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique budget cap ID |
| `category` | `String(100)`| Non-nullable | Target category |
| `monthly_limit` | `Float` | Non-nullable | Maximum allowed spending per month |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`) | Owner user ID |

---

### 6. `SavingsGoal` (`__tablename__ = "savings_goals"`)
Financial goal progress tracking.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique goal ID |
| `title` | `String(150)`| Non-nullable | Goal description |
| `target_amount` | `Float` | Non-nullable | Target financial objective |
| `current_amount`| `Float` | Default `0.0`, Non-nullable | Accumulated savings |
| `category` | `String(100)`| Nullable | Goal category |
| `target_date` | `String(50)` | Nullable | Target deadline |
| `is_completed` | `Boolean` | Default `False`, Non-nullable | Completion flag |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`) | Owner user ID |

---

### 7. `RecurringSubscription` (`__tablename__ = "recurring_subscriptions"`)
Recurring subscriptions and commitments.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique subscription ID |
| `name` | `String(150)`| Non-nullable | Service name (Netflix, AWS, etc.) |
| `amount` | `Float` | Non-nullable | Recurring cost |
| `billing_cycle` | `String(50)` | Default `"monthly"`, Non-nullable | monthly, yearly, weekly |
| `category` | `String(100)`| Default `"Entertainment"`, Non-nullable | Expense category |
| `next_due_date` | `String(50)` | Nullable | ISO date of next billing |
| `auto_renew` | `Boolean` | Default `True`, Non-nullable | Auto renewal flag |
| `status` | `String(50)` | Default `"active"`, Non-nullable | active, paused, cancelled |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`) | Owner user ID |

---

### 8. `UserSettings` (`__tablename__ = "user_settings"`)
Personalization, UI preferences, security flags, and tier settings.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique settings ID |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`), Unique | Associated user ID |
| `theme` | `String(50)` | Default `"dark"`, Non-nullable | UI theme |
| `accent_color` | `String(50)` | Default `"#8b5cf6"`, Non-nullable | UI accent hex color |
| `font_size` | `String(50)` | Default `"Medium"`, Nullable | Display font scale |
| `ai_model` | `String(50)` | Default `"GPT-4o (Default)"`, Nullable | Chosen AI model name |
| `language` | `String(50)` | Default `"English (US)"`, Nullable | Interface language |
| `response_style`| `String(50)`| Default `"Balanced"`, Nullable | Assistant tone |
| `email_alerts` | `Boolean` | Default `True`, Non-nullable | Email notification switch |
| `security_alerts`| `Boolean`| Default `True`, Non-nullable | Security alert switch |
| `ai_updates` | `Boolean` | Default `True`, Non-nullable | AI capability update switch |
| `marketing` | `Boolean` | Default `False`, Non-nullable | Marketing emails switch |
| `two_factor_enabled`| `Boolean`| Default `False`, Non-nullable | 2FA status |
| `data_privacy_opt_in`| `Boolean`| Default `True`, Non-nullable | Analytics opt-in |
| `subscription_plan`| `String(50)`| Default `"Pro User"`, Non-nullable | Current user plan |
| `subscription_status`| `String(50)`| Default `"active"`, Non-nullable | Billing subscription state |

---

### 9. `PresentationBrand` (`__tablename__ = "presentation_brands"`)
Custom branding parameters for presentation generation.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index | Unique brand profile ID |
| `user_id` | `Integer` | Foreign Key (`users.id`, ondelete `CASCADE`), Unique | Associated user ID |
| `brand_name` | `String(150)`| Default `"My Brand"`, Nullable | Brand display name |
| `brand_logo` | `Text` | Nullable | Logo URL or base64 data |
| `brand_color` | `String(50)` | Default `"#38bdf8"`, Nullable | Primary brand color |
| `brand_secondary_color`| `String(50)`| Default `"#c084fc"`, Nullable | Accent secondary color |
| `brand_font` | `String(50)` | Default `"Inter"`, Nullable | Primary typography |
| `brand_footer` | `String(255)`| Default `""`, Nullable | Custom footer text |

---

### 10. `Conversation` & `ChatMessage`
Conversational chat message persistence.

- `Conversation` (`__tablename__ = "conversations"`): `id`, `user_id` (FK -> `users.id`), `created_at`, `updated_at`.
- `ChatMessage` (`__tablename__ = "chat_messages"`): `id`, `conversation_id` (FK -> `conversations.id`), `role` (`"user"`, `"assistant"`, `"system"`), `content` (`Text`), `created_at`, `updated_at`.

---

### 11. Productivity Models: `Note`, `Task`, `CalendarEvent`
- `Note` (`__tablename__ = "notes"`): `id`, `content` (`Text`), `user_id` (FK -> `users.id`).
- `Task` (`__tablename__ = "tasks"`): `id`, `title` (`String(255)`), `user_id` (FK -> `users.id`).
- `CalendarEvent` (`__tablename__ = "calendar_events"`): `id`, `title` (`String(255)`), `date` (`String(50)`), `time` (`String(50)`), `description` (`Text`), `user_id` (FK -> `users.id`).

---

### 12. `SupportTicket` & `Message`
- `SupportTicket` (`__tablename__ = "support_tickets"`): `id`, `user_id` (FK -> `users.id`, ondelete `SET NULL`), `email`, `subject`, `category`, `message`, `status` (`"open"`).
- `Message` (`__tablename__ = "messages"`): Direct user-to-user messaging (`sender_id`, `receiver_id`, `content`).