# 11 - Image Discovery & Aggregation Engine

The Image Discovery Engine (`backend/chats/presentation/services/image_search/`) aggregates photos and illustrations across multiple open and commercial repositories.

---

## 1. Multi-Source Aggregator Pipeline

```
Slide Content & Topic
        │
        ▼
ImageSelector (image_selector.py)
        ├── Visual Type Detection (photo, vector_illustration, icon, chart)
        ├── Query Expansion & Semantic Sanitization
        └── Search Dispatch
        │
        ├──► Unsplash API (unsplash_service.py) -> High-res photography
        ├──► Openverse API (openverse.py) -> Creative Commons indexed catalog
        ├──► Wikimedia Commons (wikimedia.py) -> Historical, scientific, encyclopedic photos
        └──► Pollinations AI (ai_image_service.py) -> Generative on-demand synthesis fallback
        │
        ▼
LicenseChecker (license_checker.py)
        ├── Evaluates License (CC0, CC-BY, CC-BY-SA, Unsplash License, Public Domain)
        └── Formats Mandatory Attribution String
        │
        ▼
ImageManager (image_manager.py)
        ├── Concurrent Image Downloader & Disk Cache (assets/ or outputs/)
        └── Pillow Aspect Ratio Cropper & Image Enhancer (image_enhancer.py)
```

---

## 2. Query Builder & Visual Intent Scoring

- `determine_visual_type(slide_title, bullet_points)`:
  - Detects whether the slide demands photographic realism (e.g. *Nature, City, Corporate team*) vs abstract conceptual icons (e.g. *Security protocol, Data flow*).
- `score_image_result(image, query_terms)`:
  - Scores search results based on resolution width ($\ge 1920	ext{px}$ preferred), aspect ratio matching (16:9 or 4:3 preferred), and keyword relevance.

---

## 3. License Evaluation & Attribution

- `LicenseChecker.evaluate_license(license_info)`:
  - Classifies licenses into: `PUBLIC_DOMAIN`, `COMMERCIAL_PERMITTED`, `ATTRIBUTION_REQUIRED`, `RESTRICTED`.
  - Rejects `NonCommercial` (CC-NC) or `NoDerivatives` (CC-ND) assets if strict commercial compliance mode is activated.
  - Automatically appends formatted attribution footnotes into slide presenter notes.