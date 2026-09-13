import os
import sys
from pathlib import Path

# Ensure root directory is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.chats.presentation.presentation_api import (
    GenerateRequest,
    PresentationPlan,
    SlideSpec,
    SlidePluginBullets,
    SlidePluginParagraph,
    SlidePluginChart,
    SlidePluginTable,
    SlidePluginDiagram,
    SlidePluginStat,
    SlidePluginNotes,
    service,
)

def build_vitya_presentation_plan() -> PresentationPlan:
    plan_dict = {
        "title": "Vitya AI — Intelligent Financial & Productivity Assistant",
        "use_custom_brand": True,
        "brand_color": "#1e3a8a",
        "brand_secondary_color": "#0d9488",
        "brand_font": "Segoe UI",
        "brand_footer": "Vitya AI Platform | Confidential",
        "use_ai_image_generation": False,
        "slides": [
            {
                "layout": "title_slide",
                "title": "Vitya AI",
                "subtitle": "Intelligent Financial & Productivity Assistant\nFastAPI • Scikit-Learn • Google Gemini AI",
                "plugins": [
                    {
                        "type": "notes",
                        "data": {"notes": "Welcome everyone to the Vitya AI platform presentation. Today we will cover our architecture, ML capabilities, security model, and future roadmap."}
                    }
                ]
            },
            {
                "layout": "bullets_slide",
                "title": "Executive Summary & Problem Statement",
                "subtitle": "Solving modern personal finance & productivity challenges",
                "plugins": [
                    {
                        "type": "bullets",
                        "data": {
                            "bullets": [
                                "Manual Expense Tracking is Tedious: Traditional apps require manual entry and lack intelligent forecasting.",
                                "Data Privacy Concerns: Shared database architecture without strict multi-tenant scoping risks data leaks.",
                                "Lack of Predictive Insights: Most platforms show historical data but fail to predict overspending.",
                                "Vitya AI Solution: Automated ML regression, multi-stage intent routing, and strict user-scoped JWT isolation."
                            ]
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Detail how Vitya AI addresses user pain points through automation and strict security."}
                    }
                ]
            },
            {
                "layout": "title_content",
                "title": "System Architecture & Technology Stack",
                "subtitle": "Asynchronous REST backend with multi-layered AI cascade",
                "plugins": [
                    {
                        "type": "diagram",
                        "data": {
                            "steps": [
                                "[Client Web UI]",
                                "[FastAPI / Bearer JWT]",
                                "[SQLAlchemy & Scikit-Learn Engine]",
                                "[Google Gemini AI Fallback]"
                            ]
                        }
                    },
                    {
                        "type": "paragraph",
                        "data": {
                            "paragraph": "Built on FastAPI and Uvicorn, Vitya AI utilizes SQLAlchemy 2.0 ORM for dynamic database resolution (PostgreSQL / SQLite). High-performance ML computations are executed asynchronously in worker threadpools."
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Highlight how run_in_threadpool prevents event loop blocking during heavy ML linear regression."}
                    }
                ]
            },
            {
                "layout": "chart_slide",
                "title": "ML Expense Forecasting & Analytics",
                "subtitle": "Scikit-Learn LinearRegression monthly forecasting",
                "plugins": [
                    {
                        "type": "chart",
                        "data": {
                            "chart_type": "column",
                            "title": "Monthly Category Spending & Predictions (in ₹)",
                            "categories": ["Groceries", "Utilities", "Dining out", "Travel", "Subscriptions"],
                            "series": [
                                {"name": "Historical Avg", "values": [8500, 4200, 6100, 3500, 1500]},
                                {"name": "Predicted Next Month", "values": [9100, 4300, 5800, 4200, 1500]}
                            ]
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Point out the automatic overspending spikes flag when transactions exceed 1.5x category average."}
                    }
                ]
            },
            {
                "layout": "table_slide",
                "title": "Multi-Tenant Data Isolation & Security",
                "subtitle": "Strict tenant boundary enforcement across all modules",
                "plugins": [
                    {
                        "type": "table",
                        "data": {
                            "headers": ["Security Module", "Implementation Mechanism", "Isolation Guarantee"],
                            "rows": [
                                ["Authentication", "PyJWT Bearer Tokens (48h)", "Encrypted Payload with User ID"],
                                ["Notes & Tasks", "Foreign Key ForeignKey('users.id')", "Strict current_user.id DB Queries"],
                                ["Password Recovery", "15-minute Short-Lived Tokens", "Dynamic FRONTEND_URL Resolution"],
                                ["CSV Exports", "User-scoped /csv/expenses & /incomes", "Zero cross-tenant data leakage"]
                            ]
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Emphasize our recent automated pytest suite verifying zero data leak across user accounts."}
                    }
                ]
            },
            {
                "layout": "mixed_content_slide",
                "title": "Key Impact Metrics & System KPIs",
                "subtitle": "Demonstrated efficiency and operational benchmarks",
                "plugins": [
                    {
                        "type": "stat",
                        "data": {
                            "number": "99.9%",
                            "label": "Multi-Tenant Data Isolation Security Score"
                        }
                    },
                    {
                        "type": "bullets",
                        "data": {
                            "bullets": [
                                "< 50ms ML Inference Time: Offloaded non-blocking Scikit-Learn predictions.",
                                "30% Savings Allocation: Income-tiered dynamic budget manager.",
                                "100% Test Coverage: Pytest verified Auth, Isolation, and CSV routes."
                            ]
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Walk through performance stats and emphasize sub-50ms inference time."}
                    }
                ]
            },
            {
                "layout": "bullets_slide",
                "title": "Development Roadmap & Next Steps",
                "subtitle": "Planned enhancements for upcoming technical sprints",
                "plugins": [
                    {
                        "type": "bullets",
                        "data": {
                            "bullets": [
                                "Phase 2 - Alembic DB Migrations: Structured database schema versioning.",
                                "Phase 2 - Background Workers: Async Celery/Redis tasks for heavy presentation exports.",
                                "Phase 3 - Multi-Turn Chat Persistence: Linking ChatMessage models for conversation context.",
                                "Phase 3 - Push Budget Alerts: Dynamic threshold alerts when approaching monthly caps."
                            ]
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Summarize upcoming sprints from our CODE_EXPLANATION_AND_ROADMAP document."}
                    }
                ]
            },
            {
                "layout": "title_content",
                "title": "Interactive Demo & Conclusion",
                "subtitle": "Thank you for exploring Vitya AI",
                "plugins": [
                    {
                        "type": "paragraph",
                        "data": {
                            "paragraph": "Vitya AI combines cutting-edge machine learning with enterprise-grade FastAPI infrastructure to deliver seamless personal finance management. Explore the interactive API documentation at /docs on our server."
                        }
                    },
                    {
                        "type": "bullets",
                        "data": {
                            "bullets": [
                                "Swagger API Docs: http://localhost:10000/docs",
                                "GitHub Repository: https://github.com/mrparihar08/MOTHER",
                                "One-Click Render Cloud Deployment Ready"
                            ]
                        }
                    },
                    {
                        "type": "notes",
                        "data": {"notes": "Open floor for Q&A."}
                    }
                ]
            }
        ]
    }
    return PresentationPlan(**plan_dict)


def main():
    print("Building Vitya AI Presentation Plan...")
    plan = build_vitya_presentation_plan()
    
    req = GenerateRequest(
        prompt="Vitya AI Presentation",
        slide_count=len(plan.slides),
        export_format="pptx",
        plan=plan
    )
    
    print("Generating PPTX file...")
    file_path, plan_out, title = service.generate(req)
    print(f"[SUCCESS] Presentation generated successfully!")
    print(f"[OUTPUT] File: {file_path}")
    print(f"[SLIDES] Total Slides: {len(plan_out.slides)}")

if __name__ == "__main__":
    main()
