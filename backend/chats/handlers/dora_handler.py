# backend/chats/handlers/dora_handler.py
"""
DORA Health & Medical Intelligence Handler for MOTHER Chatbot
Integrates DORA's ML Knowledge Engine with Google Gemini AI
"""

import logging
import re
from typing import Optional, Dict, Any, List

from backend.dora.engine import engine, TYPE_TO_SPECIALIST, DEFAULT_PRECAUTIONS, DEFAULT_TESTS
from backend.chats.services.gemini_service import generate_response

logger = logging.getLogger("DORA-CHAT-HANDLER")

HEALTH_KEYWORDS = {
    # Symptoms & Conditions
    "fever", "cough", "cold", "headache", "head ache", "body pain", "fatigue", "nausea",
    "vomiting", "diarrhea", "rash", "skin rash", "itch", "itching", "chest pain", "pain",
    "breath", "breathing", "shortness of breath", "dizziness", "infection", "migraine",
    "flu", "allergy", "allergic", "throat", "sore throat", "stomach", "stomach ache",
    "cramp", "cramps", "swelling", "swollen", "joint pain", "back pain", "diabetes",
    "blood pressure", "hypertension", "cholesterol", "asthma", "typhoid", "malaria",
    "dengue", "pneumonia", "jaundice", "covid", "corona", "weakness", "acidity", "gas",
    "constipation", "ulcer", "vomit", "sneezing", "runny nose", "chills", "feverish",
    # Medical consultation keywords
    "symptom", "symptoms", "doctor", "specialist", "medicine", "medication", "pill",
    "tablet", "cure", "treatment", "remedy", "precaution", "precautions", "lab test",
    "medical test", "diagnosis", "disease", "illness", "prescription", "consultation",
    "hospital", "clinic", "health", "wellness", "bmi", "bmr", "dora", "medical",
}

EMERGENCY_KEYWORDS = [
    "severe chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "severe bleeding", "unconscious", "stroke", "paralyzed", "severe allergic reaction",
    "heart attack", "coughing blood", "blood in vomit", "sudden numbness", "anaphylaxis"
]


def is_health_query(message: str) -> bool:
    """Detects whether a user message contains health, symptom, or medical consultation intent."""
    if not message:
        return False
    text = message.lower().strip()
    
    # Check explicitly defined keywords
    for kw in HEALTH_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", text):
            return True
            
    # Check if any indexed symptom from DORA dataset is mentioned
    for sym in engine.symptom_list:
        if sym in text or text in sym:
            if len(sym) >= 4: # avoid matching short noise
                return True
                
    return False


def extract_symptoms_from_text(text: str) -> List[str]:
    """Extracts known clinical symptoms from free-form user message."""
    text_lower = text.lower()
    matched = []
    
    for symptom in engine.symptom_list:
        if len(symptom) < 3:
            continue
        clean_s = symptom.replace("_", " ").strip()
        if re.search(rf"\b{re.escape(clean_s)}\b", text_lower) or re.search(rf"\b{re.escape(symptom)}\b", text_lower):
            matched.append(clean_s)
            
    # Fallback / alias mapping for common terms
    common_terms = {
        "fever": "high_fever",
        "headache": "headache",
        "cough": "cough",
        "cold": "runny_nose",
        "fatigue": "fatigue",
        "tiredness": "fatigue",
        "weakness": "weakness",
        "vomiting": "vomiting",
        "nausea": "nausea",
        "chills": "chills",
        "body ache": "body_pain",
        "body pain": "body_pain",
        "joint pain": "joint_pain",
        "stomach pain": "stomach_pain",
        "sore throat": "sore_throat",
        "breathlessness": "shortness_of_breath",
        "rash": "skin_rash",
        "itching": "itching",
    }
    for term, norm in common_terms.items():
        if re.search(rf"\b{re.escape(term)}\b", text_lower) and norm not in matched:
            matched.append(norm)
            
    return list(set(matched))



def handle_dora_health(msg: str, user_message: str, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Handles health, medical consultation, and symptom inquiries in the main Chatbot.
    Combines DORA ML predictions with Gemini clinical grounding.
    """
    text = (msg or "").lower().strip()
    
    # Check trigger condition
    if not force and not is_health_query(user_message):
        return None

    # 1. Emergency Safety Check
    is_emergency = any(kw in text for kw in EMERGENCY_KEYWORDS)
    if is_emergency:
        alert_content = (
            "🚨 **URGENT MEDICAL ALERT**: The symptoms you described may require immediate emergency medical care.\n\n"
            "• Please call your local emergency hotline (**112 / 911 / 108**) immediately.\n"
            "• Proceed to the nearest hospital Emergency Room.\n"
            "• Do not attempt home remedies or delay clinical attention."
        )
        return {
            "type": "dora",
            "content": alert_content,
            "is_emergency": True,
            "category": "Emergency",
        }

    # 2. Extract Symptoms and run DORA ML Engine
    detected_symptoms = extract_symptoms_from_text(user_message)
    
    dora_context = ""
    primary_disease = None
    similarity = 0.0
    specialist = "General Physician / Internal Medicine"
    precautions = []
    recommended_tests = []
    urgency = "Routine"

    if detected_symptoms:
        try:
            pred_results = engine.predict(detected_symptoms, top_k=3)
            possible = pred_results.get("possible_diseases", [])
            if possible:
                top_pred = possible[0]
                primary_disease = top_pred.get("Disease", "Unknown Condition")
                similarity = top_pred.get("Similarity", 0.0)
                specialist = top_pred.get("Specialist", specialist)
                precautions = top_pred.get("Precautions", [])
                recommended_tests = top_pred.get("Recommended_Tests", [])
                urgency = top_pred.get("Urgency", "Moderate")
                
                dora_context = (
                    f"DORA KNOWLEDGE BASE DIAGNOSTIC INSIGHTS:\n"
                    f"- Detected Symptoms: {', '.join(detected_symptoms)}\n"
                    f"- Top Potential Condition: {primary_disease} (Match Confidence: {int(similarity * 100)}%)\n"
                    f"- Urgency Assessment: {urgency}\n"
                    f"- Recommended Medical Specialist: {specialist}\n"
                    f"- Suggested Lab / Diagnostic Tests: {', '.join(recommended_tests)}\n"
                    f"- Evidence-based Precautions: {'; '.join(precautions)}\n"
                )
        except Exception as e:
            logger.warning(f"DORA engine prediction failed during chat: {e}")

    # 3. Formulate Gemini Clinical System Prompt
    system_instruction = (
        "You are DORA AI (Doctor Online Remote Assistant), a clinically informed, empathetic, and responsible "
        "medical AI assistant integrated into MOTHER.\n"
        "Your mission is to provide clear, helpful, evidence-based healthcare guidance.\n\n"
        "CLINICAL GUIDELINES:\n"
        "1. Structure your answer with clear headers, bullet points, and helpful formatting.\n"
        "2. Explain potential causes clearly without causing undue panic.\n"
        "3. Incorporate evidence-based lifestyle & self-care precautions, suggested diagnostic tests, and the right specialist doctor to consult.\n"
        "4. Highlight any 'Red Flag' symptoms that require immediate in-person medical evaluation.\n"
        "5. Always end with a brief professional medical disclaimer: 'DORA is an AI health companion for educational purposes and cannot replace professional medical diagnosis or in-person evaluation.'"
    )

    if dora_context:
        prompt = (
            f"{dora_context}\n\n"
            f"User Health Inquiry: \"{user_message}\"\n\n"
            f"Please provide a comprehensive, empathetic, and structured medical consultation response grounded in the diagnostic insights above."
        )
    else:
        prompt = (
            f"User Health / Medical Question: \"{user_message}\"\n\n"
            f"Please provide clear, empathetic, and medically accurate guidance, including self-care tips, recommended specialist if applicable, and when to seek medical help."
        )

    # 4. Generate AI Response via Gemini
    ai_reply = None
    try:
        gemini_out = generate_response(prompt, system_instruction=system_instruction, temperature=0.3)
        if gemini_out and not gemini_out.startswith("Gemini error") and not gemini_out.startswith("Gemini API key is not"):
            ai_reply = gemini_out
    except Exception as e:
        logger.warning(f"Gemini generation error in DORA handler: {e}")

    # 5. Fallback Response if Gemini is offline
    if not ai_reply:
        if primary_disease:
            precautions_text = "\n".join([f"• {p}" for p in precautions[:4]])
            tests_text = ", ".join(recommended_tests[:4]) if recommended_tests else "Complete Blood Count (CBC), Routine Health Profile"
            ai_reply = (
                f"🩺 **DORA Health Assessment**\n\n"
                f"Based on your mentioned symptoms (**{', '.join(detected_symptoms)}**):\n\n"
                f"• **Potential Condition**: **{primary_disease}** (Similarity: {int(similarity * 100)}%)\n"
                f"• **Triage Urgency**: {urgency}\n"
                f"• **Recommended Specialist**: Consult a **{specialist}** for professional diagnosis.\n"
                f"• **Recommended Tests**: {tests_text}\n\n"
                f"💡 **Recommended Precautions & Self-Care**:\n{precautions_text}\n\n"
                f"⚠️ *Disclaimer: DORA is an AI health companion for informational purposes and does not replace in-person clinical evaluation.*"
            )
        else:
            ai_reply = (
                f"🩺 **DORA AI Health Assistant**\n\n"
                f"I received your health question: *\"{user_message}\"*\n\n"
                f"To provide more precise medical insights, could you please specify:\n"
                f"1. What exact symptoms you are currently experiencing?\n"
                f"2. How many days have they persisted?\n"
                f"3. Are the symptoms mild, moderate, or severe?\n\n"
                f"You can also use our **DORA Symptom Checker** for instant multi-symptom risk analysis."
            )

    return {
        "type": "dora",
        "content": ai_reply,
        "health_data": {
            "detected_symptoms": detected_symptoms,
            "predicted_disease": primary_disease,
            "similarity": similarity,
            "specialist": specialist,
            "precautions": precautions,
            "recommended_tests": recommended_tests,
            "urgency": urgency,
            "is_emergency": False,
        }
    }
