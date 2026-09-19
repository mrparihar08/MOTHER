import pytest
from pathlib import Path
from backend.chats.presentation.services.presentation_store import PresentationStore, presentation_store
from backend.chats.presentation.schemas import PresentationPlan, SlideSpec, SlidePluginBullets, SlidePluginText


def test_presentation_store_atomic_operations(tmp_path):
    store = PresentationStore(store_dir=tmp_path)
    pres_id = "pres_test_store_123"

    assert not store.exists(pres_id)
    assert store.get(pres_id) is None

    # Initial save
    data1 = {"title": "Test Pres", "theme": "corporate", "slides_count": 2}
    saved1 = store.save(pres_id, data1)
    assert saved1["presentation_id"] == pres_id
    assert saved1["version"] == 1
    assert "updated_at" in saved1
    assert store.exists(pres_id)

    # Update save
    data2 = {"title": "Updated Pres Title", "theme": "neon", "slides_count": 3}
    saved2 = store.save(pres_id, data2)
    assert saved2["presentation_id"] == pres_id
    assert saved2["version"] == 2
    assert saved2["title"] == "Updated Pres Title"
    assert saved2["theme"] == "neon"

    # Fetch
    fetched = store.get(pres_id)
    assert fetched["version"] == 2
    assert fetched["title"] == "Updated Pres Title"

    # Delete
    assert store.delete(pres_id)
    assert not store.exists(pres_id)


def test_presentation_save_update_reload_download_flow(client):
    # 1. Initial Creation
    initial_payload = {
        "prompt": "Artificial Intelligence Strategy",
        "topic": "AI Strategy",
        "slide_count": 2,
        "content_theme": "corporate_light",
        "template_name": "corporate_light.pptx",
        "use_ai_image_generation": False,
        "use_gemini": False,
    }

    res = client.post("/api/presentation/save", json=initial_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "saved"
    pres_id = data["presentation_id"]
    assert pres_id.startswith("pres_")
    assert data["version"] == 1
    file_name = data["file_name"]
    download_url = data["download_url"]
    assert download_url is not None

    # 2. Re-open / Reload initial presentation state
    res_get = client.get(f"/api/presentation/{pres_id}")
    assert res_get.status_code == 200
    details = res_get.json()
    assert details["presentation_id"] == pres_id
    assert details["version"] == 1
    assert details["content_theme"] == "corporate_light"
    assert details["template_name"] == "corporate_light.pptx"
    initial_plan = details["plan"]
    assert len(initial_plan["slides"]) >= 2

    # 3. User performs multiple modifications in Editor:
    #    - Change Theme to cyber_neon
    #    - Change Template to cyber_neon.pptx
    #    - Change Layout of slide 2
    #    - Modify text & add custom text plugin element
    modified_plan = initial_plan.copy()
    modified_plan["slides"][0]["title"] = "MODIFIED AI Strategy Title"
    modified_plan["slides"].append({
        "layout": "bullets_slide",
        "title": "Newly Added Slide Element",
        "plugins": [
            {
                "type": "bullets",
                "data": {
                    "bullets": ["Point 1: Executive ROI", "Point 2: Security Governance"]
                }
            }
        ]
    })

    update_payload = {
        "presentation_id": pres_id,
        "prompt": "AI Strategy Updated",
        "topic": "AI Strategy Updated",
        "content_theme": "cyber_neon",
        "template_name": "cyber_neon.pptx",
        "plan": modified_plan
    }

    # 4. Perform Save (or PUT update)
    res_update = client.put(f"/api/presentation/{pres_id}", json=update_payload)
    assert res_update.status_code == 200
    update_data = res_update.json()
    assert update_data["presentation_id"] == pres_id
    assert update_data["version"] == 2

    # 5. Reload after closing/reopening editor to verify exact latest state
    res_reload = client.get(f"/api/presentation/{pres_id}")
    assert res_reload.status_code == 200
    reload_details = res_reload.json()
    assert reload_details["version"] == 2
    assert reload_details["content_theme"] == "cyber_neon"
    assert reload_details["template_name"] == "cyber_neon.pptx"
    assert reload_details["plan"]["slides"][0]["title"] == "MODIFIED AI Strategy Title"
    assert len(reload_details["plan"]["slides"]) == len(modified_plan["slides"])

    # 6. Verify Download from latest saved state
    res_dl = client.get(f"/api/presentation/download-presentation/{pres_id}")
    assert res_dl.status_code == 200
    assert len(res_dl.content) > 0
    assert res_dl.headers["content-type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    # Also check /download/{file_name}
    res_dl2 = client.get(f"/api/presentation/download/{file_name}")
    assert res_dl2.status_code == 200
    assert len(res_dl2.content) > 0
