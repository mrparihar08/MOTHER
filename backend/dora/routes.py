import re
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.dora.engine import engine, TYPE_TO_SPECIALIST, DEFAULT_PRECAUTIONS, DEFAULT_TESTS
from backend.chats.services.gemini_service import generate_response

logger = logging.getLogger("DORA-ROUTES")

router = APIRouter()

# ===========================================
# Request & Response Schemas
# ===========================================
class SymptomsRequest(BaseModel):
    symptoms: List[str] = Field(..., example=["fever", "dry cough", "fatigue"])
    severity: Optional[str] = Field(None, example="Moderate")
    duration_days: Optional[int] = Field(None, example=3)
    age: Optional[int] = Field(None, example=28)
    gender: Optional[str] = Field(None, example="Male")
    include_ai_explanation: Optional[bool] = Field(False, description="Generate Gemini clinical summary")
    language: Optional[str] = Field("auto", description="Target language: en, hi, hinglish, or auto")

class ChatMessage(BaseModel):
    role: str = Field(..., example="user")
    content: str = Field(..., example="I have had a mild headache and sneezing for 2 days. What should I do?")

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    user_context: Optional[Dict[str, Any]] = None
    language: Optional[str] = Field("auto", description="Target language: en, hi, hinglish, or auto")

class HealthAssessmentRequest(BaseModel):
    age: int = Field(..., ge=1, le=120)
    gender: str = Field(..., example="male")
    height_cm: float = Field(..., ge=50, le=250)
    weight_kg: float = Field(..., ge=20, le=300)
    activity_level: str = Field(..., example="moderate")
    has_smoker_history: Optional[bool] = False
    has_diabetes_history: Optional[bool] = False
    has_hypertension: Optional[bool] = False
    include_ai_plan: Optional[bool] = Field(False, description="Generate personalized Gemini wellness plan")
    language: Optional[str] = Field("auto", description="Target language: en, hi, hinglish, or auto")


def get_language_instruction(lang: Optional[str]) -> str:
    if not lang or lang == "auto":
        return "Detect the user's language (Hindi, Hinglish, English, etc.) and reply in the exact same language and dialect naturally."
    l = lang.lower().strip()
    if l in ("hi", "hindi"):
        return "You MUST respond entirely in clear, natural Hindi (हिन्दी / Devanagari script)."
    elif l in ("hinglish", "hi-en", "en-hi"):
        return "You MUST respond in natural Hinglish (Romanized Hindi/English mix - e.g. 'Aapko rest karna chahiye aur garam paani peena chahiye')."
    elif l in ("en", "english"):
        return "You MUST respond in clear, empathetic English."
    return f"Respond in the user's preferred language ({lang})."

def extract_symptoms_from_text(text: str) -> List[str]:
    """Helper to detect and normalize symptoms from natural language text."""
    lower = text.lower()
    matched = []
    for s in engine.symptom_list:
        if len(s) < 3:
            continue
        clean_s = s.replace("_", " ").strip()
        if re.search(rf"\b{re.escape(clean_s)}\b", lower) or re.search(rf"\b{re.escape(s)}\b", lower):
            matched.append(clean_s)
    return list(set(matched))



# ===========================================
# Endpoints
# ===========================================
@router.get("/")
def dora_info():
    return {
        "service": "DORA Health Intelligence Module",
        "status": "online",
        "version": "2.1.0",
        "ai_powered_by": "Google Gemini & DORA Random Forest / TF-IDF",
        "total_diseases_indexed": len(engine.disease_records),
        "total_symptoms_indexed": len(engine.symptom_list)
    }

@router.get("/symptoms")
def get_symptoms(query: Optional[str] = None):
    """Returns all unique indexed symptoms with optional search filter."""
    if query:
        q = query.lower().strip()
        filtered = [s for s in engine.symptom_list if q in s]
        return {"query": query, "count": len(filtered), "symptoms": filtered}
    return {"count": len(engine.symptom_list), "symptoms": engine.symptom_list}

@router.get("/diseases")
def get_diseases():
    """Returns all indexed diseases with category and severity info."""
    summary = [
        {
            "disease": r["Disease"],
            "type": r["Type"],
            "severity": r["Severity_Level"],
            "symptoms_count": len(r["Symptoms"])
        }
        for r in engine.disease_records
    ]
    return {"total": len(summary), "diseases": summary}

@router.post("/predict")
def predict_disease_endpoint(request: SymptomsRequest, top_k: int = Query(5, ge=1, le=15)):
    """
    Predicts condition based on symptom set, returns confidence ranking,
    specialist recommendation, precautions, suggested lab tests, triage urgency,
    and optional Gemini AI clinical explanation.
    """
    if not request.symptoms:
        raise HTTPException(status_code=400, detail="Please provide at least one symptom.")

    try:
        results = engine.predict(request.symptoms, top_k=top_k)
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])
        
        results["user_context"] = {
            "severity_input": request.severity,
            "duration_days": request.duration_days,
            "age": request.age,
            "gender": request.gender
        }

        # Optional Gemini clinical AI explanation
        if request.include_ai_explanation:
            top_disease = results.get("predicted_disease", "Condition")
            primary_details = results.get("primary_details", {})
            specialist = primary_details.get("Specialist", "General Physician")
            precautions = primary_details.get("Precautions", [])
            tests = primary_details.get("Recommended_Tests", [])
            lang_rule = get_language_instruction(request.language)

            prompt = (
                f"Symptom Profile: {', '.join(request.symptoms)}\n"
                f"Predicted Condition: {top_disease}\n"
                f"Recommended Specialist: {specialist}\n"
                f"Precautions: {'; '.join(precautions)}\n"
                f"Diagnostic Tests: {', '.join(tests)}\n\n"
                f"Language Requirement: {lang_rule}\n\n"
                "Please generate a concise, doctor-like clinical summary explaining the relationship between these symptoms and condition, what the patient should do next, and reassurance in the requested language."
            )
            ai_summary = generate_response(
                prompt,
                system_instruction=f"You are DORA AI, a compassionate and expert clinical medical AI assistant. {lang_rule}"
            )
            if ai_summary and not ai_summary.startswith("Gemini error") and not ai_summary.startswith("Gemini API key"):
                results["ai_clinical_summary"] = ai_summary

        results["disclaimer"] = (
            "DORA Dr. is an AI triage companion providing statistical symptom-matching for informational purposes only. "
            "It does NOT constitute a confirmed medical diagnosis or substitute for professional clinical judgment. "
            "In case of severe or life-threatening symptoms, contact emergency services immediately."
        )
        results["uncertainty_notice"] = (
            "Predictions reflect statistical similarity from reported symptoms, not diagnostic certainty. "
            "Please consult a certified medical practitioner for formal evaluation."
        )

        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=f"Internal prediction error: {str(e)}")

@router.post("/chat")
def ai_health_chat(request: ChatRequest):
    """
    Intelligent AI Health Consultation Assistant powered by Gemini & DORA Knowledge Engine.
    Provides empathetic, grounded clinical guidance, triage warnings, specialist referrals, and precautions.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Message history cannot be empty.")

    last_user_message = request.messages[-1].content.strip()
    lower_query = last_user_message.lower()

    # 1. Medical emergency triage check
    emergency_keywords = [
        "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
        "severe bleeding", "unconscious", "stroke", "paralyzed", "severe allergic reaction",
        "heart attack", "coughing blood", "blood in vomit", "sudden numbness", "anaphylaxis"
    ]
    is_emergency = any(kw in lower_query for kw in emergency_keywords)

    if is_emergency:
        reply = (
            "🚨 **URGENT MEDICAL ALERT**: The symptoms you described could indicate a life-threatening medical emergency. "
            "Please call your local emergency services (**911 / 112 / 108**) or proceed immediately to the nearest hospital emergency department. "
            "Do not attempt home remedies or delay clinical attention."
        )
        return {
            "reply": reply,
            "is_emergency": True,
            "category": "Emergency",
            "detected_symptoms": [],
            "suggested_specialist": "Emergency Medicine / Trauma Physician"
        }

    # 2. Symptom extraction & DORA ML grounding
    matched_symptoms = extract_symptoms_from_text(last_user_message)
    suggested_specialist = "General Physician / Internist"
    top_pred_dict = {}
    dora_grounding = ""

    if matched_symptoms:
        pred_result = engine.predict(matched_symptoms, top_k=3)
        possible = pred_result.get("possible_diseases", [])
        if possible:
            top_pred_dict = possible[0]
            disease_name = top_pred_dict.get("Disease", "a potential condition")
            suggested_specialist = top_pred_dict.get("Specialist", suggested_specialist)
            precautions = top_pred_dict.get("Precautions", ["Stay well-hydrated", "Get adequate rest"])
            lab_tests = top_pred_dict.get("Recommended_Tests", ["Complete Blood Count (CBC)"])
            urgency = top_pred_dict.get("Urgency", "Moderate")
            similarity = top_pred_dict.get("Similarity", 0.5)

            dora_grounding = (
                f"DORA MEDICAL ENGINE GROUNDING FACTS:\n"
                f"- Reported Symptoms: {', '.join(matched_symptoms)}\n"
                f"- Predicted Primary Condition: {disease_name} (Confidence: {int(similarity * 100)}%)\n"
                f"- Triage Priority: {urgency}\n"
                f"- Specialist Recommendation: {suggested_specialist}\n"
                f"- Recommended Diagnostic Tests: {', '.join(lab_tests)}\n"
                f"- Clinical Precautions: {'; '.join(precautions)}\n"
            )

    # 3. Build Conversation History Context
    history_lines = []
    for m in request.messages[-5:]:
        role = "User" if m.role.lower() == "user" else "DORA AI"
        history_lines.append(f"{role}: {m.content}")
    conversation_context = "\n".join(history_lines)

    # 4. Invoke Gemini with Clinical Grounding
    lang_instruction = get_language_instruction(request.language)
    system_instruction = (
        "You are DORA AI, an empathetic, helpful, and expert medical AI health assistant.\n\n"
        "MULTI-LANGUAGE & TONE RULES:\n"
        f"1. {lang_instruction}\n"
        "If the user communicates in Hindi or Hinglish, reply in natural, friendly Hindi/Hinglish without awkward formal translation.\n"
        "2. Avoid rigid, repetitive boilerplate intros (do NOT say 'Hello! I am DORA AI, your Doctor Online Remote Assistant...'). Directly address the user's issue with empathy.\n"
        "3. Provide concise, clear, and practical health guidance: explain reasons in simple terms, list helpful self-care tips, indicate which specialist to consult if symptoms continue, and conclude with a short one-line health disclaimer."
    )

    prompt = (
        f"{dora_grounding}\n\n"
        f"Conversation History:\n{conversation_context}\n\n"
        f"Latest User Query: \"{last_user_message}\"\n\n"
        f"Language Directive: {lang_instruction}\n\n"
        f"Please provide an empathetic, clear, structured medical guidance response in the requested language."
    )


    ai_reply = None
    try:
        gemini_res = generate_response(prompt, system_instruction=system_instruction, temperature=0.3)
        if gemini_res and not gemini_res.startswith("Gemini error") and not gemini_res.startswith("Gemini API key is not"):
            ai_reply = gemini_res
    except Exception as e:
        logger.warning(f"Gemini API call failed in DORA chat: {e}")

    # 5. Deterministic fallback if Gemini is offline
    if not ai_reply:
        if matched_symptoms and top_pred_dict:
            precautions = top_pred_dict.get("Precautions", ["Stay hydrated", "Get adequate rest"])
            reply = (
                f"Hello! Based on the symptoms you mentioned (**{', '.join(matched_symptoms)}**):\n\n"
                f"🩺 **Potential Assessment**: These symptoms are commonly associated with **{top_pred_dict.get('Disease')}**.\n\n"
                f"💡 **Recommended Self-Care & Precautions**:\n" +
                "\n".join([f"• {p}" for p in precautions[:3]]) + "\n\n"
                f"👨‍⚕️ **Recommended Specialist**: We recommend consulting a **{suggested_specialist}** for professional evaluation.\n\n"
                f"⚠️ *Disclaimer: DORA is an AI health companion for informational purposes and cannot replace professional medical diagnosis.*"
            )
        elif any(greeting in lower_query for greeting in ["hi", "hello", "hey", "namaste"]):
            reply = (
                "👋 Hello! I am **DORA AI**, your intelligent healthcare assistant.\n\n"
                "You can ask me about:\n"
                "• Symptoms you are experiencing (e.g., headache, fever, cough, fatigue)\n"
                "• Dietary and lifestyle advice for specific health conditions\n"
                "• Health assessments (BMI, BMR, hydration, risk profile)\n"
                "• First-aid guidance and wellness recommendations\n\n"
                "How can I assist you with your health today?"
            )
        elif "diet" in lower_query or "food" in lower_query or "eat" in lower_query:
            reply = (
                "🥗 **Nutritional & Dietary Guidance**:\n\n"
                "• **Hydration**: Drink 2.5–3 liters of water daily.\n"
                "• **Whole Foods**: Prioritize fresh leafy vegetables, fruits, whole grains, and lean proteins.\n"
                "• **Anti-inflammatory**: Include turmeric, ginger, berries, and omega-3s.\n"
                "• **Limit**: High-sugar drinks, excess sodium, and ultra-processed foods.\n\n"
                "Let me know if you have a specific health condition for customized dietary advice!"
            )
        else:
            reply = (
                f"Thank you for reaching out! Regarding your query: *\"{last_user_message}\"*\n\n"
                "To give you the most accurate medical insights, could you share:\n"
                "1. What specific symptoms you are feeling right now?\n"
                "2. How many days have you had these symptoms?\n"
                "3. Are they mild, moderate, or severe?\n\n"
                "You can also use our **Symptom Checker** for an instant interactive check!"
            )
    else:
        reply = ai_reply

    return {
        "reply": reply,
        "is_emergency": False,
        "detected_symptoms": matched_symptoms,
        "suggested_specialist": suggested_specialist,
        "primary_prediction": top_pred_dict.get("Disease") if top_pred_dict else None
    }

@router.post("/health-assessment")
def calculate_health_assessment(req: HealthAssessmentRequest):
    """
    Calculates Body Mass Index (BMI), Basal Metabolic Rate (BMR),
    daily water requirements, cardiovascular wellness risk profile,
    and optional personalized Gemini AI wellness coaching plan.
    """
    height_m = req.height_cm / 100.0
    bmi = round(req.weight_kg / (height_m ** 2), 1)

    if bmi < 18.5:
        bmi_category = "Underweight"
        bmi_status = "warning"
        bmi_advice = "Focus on nutrient-dense calorie sources, complex carbohydrates, and strength training to build healthy muscle mass."
    elif 18.5 <= bmi < 24.9:
        bmi_category = "Normal / Healthy Weight"
        bmi_status = "success"
        bmi_advice = "Excellent! Continue your balanced diet, regular exercise, and consistent sleep hygiene."
    elif 25.0 <= bmi < 29.9:
        bmi_category = "Overweight"
        bmi_status = "warning"
        bmi_advice = "Incorporate 30–45 minutes of aerobic exercise daily and monitor refined sugar & carbohydrate intake."
    else:
        bmi_category = "Obesity"
        bmi_status = "danger"
        bmi_advice = "Consider consulting a clinical nutritionist or physician for a structured weight management and metabolic health plan."

    # Basal Metabolic Rate (Mifflin-St Jeor Equation)
    if req.gender.lower() == "male":
        bmr = 10 * req.weight_kg + 6.25 * req.height_cm - 5 * req.age + 5
    else:
        bmr = 10 * req.weight_kg + 6.25 * req.height_cm - 5 * req.age - 161

    # Daily Water Intake estimation (35 ml per kg body weight)
    daily_water_liters = round((req.weight_kg * 0.035), 1)
    daily_glasses = int(round(daily_water_liters / 0.25))

    # Activity Multipliers
    activity_multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9
    }
    tdee = int(bmr * activity_multipliers.get(req.activity_level.lower(), 1.4))

    # Overall wellness risk factor score
    risk_points = 0
    if bmi >= 30: risk_points += 2
    elif bmi >= 25: risk_points += 1
    if req.has_smoker_history: risk_points += 2
    if req.has_diabetes_history: risk_points += 2
    if req.has_hypertension: risk_points += 2
    if req.age > 50: risk_points += 1

    if risk_points <= 1:
        overall_risk = "Low Risk / Optimal Health"
        risk_badge = "success"
    elif risk_points <= 3:
        overall_risk = "Moderate Risk (Preventative Lifestyle Recommended)"
        risk_badge = "warning"
    else:
        overall_risk = "High Risk (Periodic Health Screenings Recommended)"
        risk_badge = "danger"

    result = {
        "bmi": bmi,
        "bmi_category": bmi_category,
        "bmi_status": bmi_status,
        "bmi_advice": bmi_advice,
        "bmr_calories": int(bmr),
        "daily_maintenance_calories": tdee,
        "recommended_daily_water_liters": daily_water_liters,
        "recommended_daily_glasses": daily_glasses,
        "overall_risk_profile": overall_risk,
        "risk_badge": risk_badge
    }

    if req.include_ai_plan:
        lang_rule = get_language_instruction(req.language)
        prompt = (
            f"User Profile: Age {req.age}, Gender {req.gender}, BMI {bmi} ({bmi_category}), "
            f"Activity Level {req.activity_level}, Maintenance Calories {tdee} kcal/day, "
            f"Risk Profile: {overall_risk}.\n"
            f"Medical History: Smoker={req.has_smoker_history}, Diabetes History={req.has_diabetes_history}, Hypertension={req.has_hypertension}.\n\n"
            f"Language Requirement: {lang_rule}\n\n"
            "Create a personalized 4-point health and wellness optimization plan (Diet, Exercise, Hydration, Preventative Care) in the requested language."
        )
        ai_plan = generate_response(
            prompt,
            system_instruction=f"You are DORA AI, a preventive health and wellness physician. {lang_rule}"
        )
        if ai_plan and not ai_plan.startswith("Gemini error") and not ai_plan.startswith("Gemini API key"):
            result["ai_wellness_plan"] = ai_plan

    return result

