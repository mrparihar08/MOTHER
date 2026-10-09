# backend/dora/engine.py
"""
DORA Medical Knowledge Engine & ML Pipeline for MOTHER
"""

import os
import re
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Any

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib

logger = logging.getLogger("DORA-ENGINE")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
DATA_PATH = os.path.join(BASE_DIR, "dataset.csv")

MODEL_PATH = os.path.join(ARTIFACTS_DIR, "disease_model.pkl")
VECTORIZER_PATH = os.path.join(ARTIFACTS_DIR, "tfidf_vectorizer.pkl")
ENCODER_PATH = os.path.join(ARTIFACTS_DIR, "label_encoder.pkl")

# ===========================================
# Clinical Metadata Mapping & Rules
# ===========================================
TYPE_TO_SPECIALIST = {
    "Viral": "Infectious Disease Specialist / General Physician",
    "Bacterial": "General Physician / Internal Medicine",
    "Autoimmune": "Rheumatologist / Immunologist",
    "Genetic": "Medical Geneticist / Specialist Consultant",
    "Parasitic": "Infectious Disease Specialist / Gastroenterologist",
    "Oncologic": "Oncologist",
    "Fungal": "Dermatologist / Mycologist",
    "Neurologic": "Neurologist",
    "Digestive": "Gastroenterologist",
    "Dermatologic": "Dermatologist",
    "Respiratory": "Pulmonologist / Chest Physician",
    "Hematologic": "Hematologist",
    "Nutritional": "Clinical Dietitian / General Physician",
    "Vascular": "Vascular Surgeon / Cardiologist",
    "Urologic": "Urologist / Nephrologist",
    "Endocrine": "Endocrinologist",
    "Nephrologic": "Nephrologist",
    "Metabolic": "Endocrinologist / Diabetologist",
    "Gynecologic": "Gynecologist",
    "Chronic": "General Physician / Specialist",
    "Degenerative": "Neurologist / Orthopedic Surgeon",
    "Allergic": "Allergist / Immunologist",
    "Infectious": "Infectious Disease Specialist",
}

DEFAULT_PRECAUTIONS = {
    "Viral": [
        "Drink plenty of fluids and maintain electrolyte balance.",
        "Take adequate rest to allow your immune system to recover.",
        "Practice good hand hygiene and isolate if contagious.",
        "Consult a doctor if fever persists beyond 3 days."
    ],
    "Bacterial": [
        "Consult a physician for appropriate antibiotic prescription (do not self-medicate).",
        "Complete the full course of any prescribed medication.",
        "Keep the affected area clean and sanitized.",
        "Monitor body temperature and symptom changes daily."
    ],
    "Autoimmune": [
        "Follow an anti-inflammatory, balanced whole-foods diet.",
        "Avoid known stress and environmental triggers.",
        "Maintain regular follow-ups with your rheumatologist/specialist.",
        "Engage in low-impact physical activity as tolerated."
    ],
    "Respiratory": [
        "Avoid exposure to dust, smoke, pollutants, and cold air.",
        "Consider steam inhalation or warm saline gargles for throat relief.",
        "Use a humidifier in dry indoor environments.",
        "Seek immediate emergency care if experiencing breathing difficulty or chest tightness."
    ],
    "Digestive": [
        "Eat small, easily digestible, low-grease meals (BRAT diet: bananas, rice, applesauce, toast).",
        "Stay hydrated with ORS or coconut water.",
        "Avoid spicy, acidic, processed foods and caffeinated beverages.",
        "Seek medical help if severe abdominal pain or blood in stool occurs."
    ],
    "Dermatologic": [
        "Keep the affected skin clean, moisturized, and dry.",
        "Avoid scratching or peeling to prevent secondary bacterial infection.",
        "Use mild, fragrance-free soaps and skin cleansers.",
        "Wear loose-fitting, breathable cotton clothing."
    ],
    "Neurologic": [
        "Rest in a quiet, dimly lit room if experiencing headache or sensory sensitivity.",
        "Track frequency and duration of symptoms in a diary.",
        "Maintain consistent sleep schedules and hydration.",
        "Seek emergency medical attention if confusion, weakness, or speech difficulty occurs."
    ]
}

DEFAULT_TESTS = {
    "Viral": ["Complete Blood Count (CBC)", "Viral Serology / RT-PCR", "C-Reactive Protein (CRP)"],
    "Bacterial": ["Complete Blood Count (CBC)", "Blood / Urine / Sputum Culture", "ESR (Erythrocyte Sedimentation Rate)"],
    "Autoimmune": ["ANA (Antinuclear Antibodies)", "Rheumatoid Factor (RF)", "CRP & ESR", "Comprehensive Metabolic Panel"],
    "Respiratory": ["Chest X-Ray / CT Scan", "Pulse Oximetry (SpO2)", "Spirometry / Pulmonary Function Test"],
    "Digestive": ["Stool Analysis", "Abdominal Ultrasound", "Liver Function Test (LFT)", "Endoscopy (if advised)"],
    "Dermatologic": ["Skin Biopsy / Scraping", "Allergy Patch Test", "Dermoscopy Examination"],
    "Neurologic": ["Brain MRI / CT Scan", "Electroencephalogram (EEG)", "Neurological Reflex Assessment"],
    "Hematologic": ["Complete Blood Count with Peripheral Smear", "Iron Profile / Ferritin", "Coagulation Profile (PT/INR)"],
    "Nephrologic": ["Kidney Function Test (BUN/Creatinine)", "Urinalysis", "Renal Ultrasound"],
    "Endocrine": ["Thyroid Profile (T3, T4, TSH)", "Fasting Blood Sugar & HbA1c", "Serum Cortisol / Hormone Panel"],
}

# ===========================================
# Model & Knowledge Training Engine
# ===========================================
class KnowledgeEngine:
    def __init__(self, data_path: str = DATA_PATH):
        self.data_path = data_path
        self.df = pd.DataFrame()
        self.symptom_list = []
        self.disease_records = []
        self.vectorizer = None
        self.tfidf_matrix = None
        self.model = None
        self.label_encoder = None
        self.load_and_train()

    def clean_text(self, text: Any) -> str:
        if not isinstance(text, str):
            return ""
        return re.sub(r"[^\w\s]", " ", text).strip().lower()

    def load_and_train(self):
        logger.info("🧠 Initializing DORA Medical Knowledge Engine & ML Pipeline for MOTHER...")
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Dataset not found at {self.data_path}")

        self.df = pd.read_csv(self.data_path)
        self.df.columns = [c.strip().replace(" ", "_") for c in self.df.columns]
        self.df = self.df.dropna(subset=["Disease"]).fillna("")

        symptom_cols = [c for c in self.df.columns if "symptom" in c.lower()]
        
        all_syms = set()
        records = []

        for _, row in self.df.iterrows():
            disease = str(row["Disease"]).strip()
            dtype = str(row.get("Type", "General")).strip()
            severity = str(row.get("Severity_Level", "Moderate")).strip()
            
            symptoms = []
            for col in symptom_cols:
                val = str(row.get(col, "")).strip().lower()
                if val and val != "nan":
                    symptoms.append(val)
                    all_syms.add(val)
            
            combined_text = " ".join(symptoms)
            records.append({
                "Disease": disease,
                "Type": dtype,
                "Severity_Level": severity,
                "Symptoms": symptoms,
                "Text": combined_text
            })

        self.disease_records = records
        self.symptom_list = sorted(list(all_syms))
        corpus = [r["Text"] for r in records]

        # Check if pre-trained serialized artifacts exist
        if (
            os.path.exists(MODEL_PATH)
            and os.path.exists(VECTORIZER_PATH)
            and os.path.exists(ENCODER_PATH)
        ):
            try:
                self.model = joblib.load(MODEL_PATH)
                self.vectorizer = joblib.load(VECTORIZER_PATH)
                self.label_encoder = joblib.load(ENCODER_PATH)
                self.tfidf_matrix = self.vectorizer.transform(corpus)
                logger.info(
                    f"✅ DORA Engine loaded serialized artifacts for {len(records)} diseases and {len(self.symptom_list)} distinct symptoms."
                )
                return
            except Exception as load_err:
                logger.warning(
                    f"⚠️ Failed to load serialized artifacts ({load_err}). Retraining DORA pipeline..."
                )

        # Build TF-IDF Vectorizer across all diseases
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

        # Build Classifier for fallback probability estimation
        self.label_encoder = LabelEncoder()
        y_labels = [r["Disease"] for r in records]
        y_encoded = self.label_encoder.fit_transform(y_labels)

        self.model = RandomForestClassifier(n_estimators=120, random_state=42)
        self.model.fit(self.tfidf_matrix, y_encoded)

        # Save artifacts safely
        try:
            joblib.dump(self.model, MODEL_PATH)
            joblib.dump(self.vectorizer, VECTORIZER_PATH)
            joblib.dump(self.label_encoder, ENCODER_PATH)
        except Exception as dump_err:
            logger.warning(f"⚠️ Could not cache serialized models to disk: {dump_err}")

        logger.info(f"✅ DORA Engine initialized with {len(records)} diseases and {len(self.symptom_list)} distinct symptoms.")

    def match_similarity(self, s1: str, s2: str) -> float:
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def predict(self, user_symptoms: List[str], top_k: int = 5) -> Dict[str, Any]:
        clean_inputs = [s.strip().lower() for s in user_symptoms if s.strip()]
        if not clean_inputs:
            return {"error": "No valid symptoms provided."}

        input_text = " ".join(clean_inputs)
        query_vec = self.vectorizer.transform([input_text])

        # 1. Cosine similarity with all disease symptom profiles
        cos_sims = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        scored_candidates = []

        for idx, record in enumerate(self.disease_records):
            cos_score = float(cos_sims[idx])
            disease_syms = record["Symptoms"]

            # 2. Symptom overlap & fuzzy score
            matched_count = 0
            fuzzy_sum = 0.0

            for user_sym in clean_inputs:
                best_match = 0.0
                for d_sym in disease_syms:
                    if user_sym in d_sym or d_sym in user_sym:
                        best_match = max(best_match, 0.95)
                    else:
                        seq_sim = self.match_similarity(user_sym, d_sym)
                        best_match = max(best_match, seq_sim)
                
                fuzzy_sum += best_match
                if best_match >= 0.70:
                    matched_count += 1

            avg_fuzzy = fuzzy_sum / len(clean_inputs) if clean_inputs else 0.0
            jaccard = matched_count / max(1, len(set(disease_syms) | set(clean_inputs)))

            # Hybrid score computation
            # Weights: 45% Cosine TF-IDF, 35% Fuzzy match, 20% Jaccard overlap
            combined_score = (0.45 * cos_score) + (0.35 * avg_fuzzy) + (0.20 * jaccard)

            # Bonus if high match count
            if matched_count >= 2:
                combined_score = min(1.0, combined_score + 0.10)

            if combined_score > 0.15 or matched_count > 0:
                dtype = record["Type"]
                specialist = TYPE_TO_SPECIALIST.get(dtype, "General Physician / Internist")
                precautions = DEFAULT_PRECAUTIONS.get(dtype, DEFAULT_PRECAUTIONS.get("Viral", []))
                lab_tests = DEFAULT_TESTS.get(dtype, ["Complete Blood Count (CBC)", "Routine Health Panel"])
                
                # Triage urgency calculation
                severity_level = record["Severity_Level"]
                urgency = "Routine (Low Risk)"
                if severity_level.lower() == "severe" or any(s in input_text for s in ["chest pain", "shortness of breath", "coma", "hemorrhage", "paralysis"]):
                    urgency = "Urgent / High Priority (Seek Medical Care Promptly)"
                elif severity_level.lower() == "moderate":
                    urgency = "Moderate (Schedule Doctor Visit)"

                scored_candidates.append({
                    "Disease": record["Disease"],
                    "Similarity": round(combined_score, 3),
                    "Type": dtype,
                    "Severity_Level": severity_level,
                    "Urgency": urgency,
                    "Specialist": specialist,
                    "Matched_Symptoms": [s for s in disease_syms if any(u in s or s in u or self.match_similarity(u, s) > 0.65 for u in clean_inputs)],
                    "Key_Symptoms": disease_syms,
                    "Precautions": precautions,
                    "Recommended_Tests": lab_tests
                })

        # Sort descending by similarity
        scored_candidates = sorted(scored_candidates, key=lambda x: x["Similarity"], reverse=True)

        # Fallback to model prediction if no fuzzy match above threshold
        if not scored_candidates:
            y_pred = self.model.predict(query_vec)
            fallback_disease = self.label_encoder.inverse_transform(y_pred)[0]
            
            # Find record for fallback
            matched_rec = next((r for r in self.disease_records if r["Disease"] == fallback_disease), None)
            dtype = matched_rec["Type"] if matched_rec else "General"
            severity = matched_rec["Severity_Level"] if matched_rec else "Moderate"
            
            scored_candidates = [{
                "Disease": fallback_disease,
                "Similarity": 0.50,
                "Type": dtype,
                "Severity_Level": severity,
                "Urgency": "Moderate (Schedule Doctor Visit)",
                "Specialist": TYPE_TO_SPECIALIST.get(dtype, "General Physician"),
                "Matched_Symptoms": clean_inputs,
                "Key_Symptoms": matched_rec["Symptoms"] if matched_rec else [],
                "Precautions": DEFAULT_PRECAUTIONS.get(dtype, DEFAULT_PRECAUTIONS.get("Viral", [])),
                "Recommended_Tests": DEFAULT_TESTS.get(dtype, ["Complete Blood Count (CBC)"])
            }]

        top_predictions = scored_candidates[:top_k]
        primary_disease = top_predictions[0]["Disease"]

        return {
            "input_symptoms": clean_inputs,
            "predicted_disease": primary_disease,
            "primary_details": top_predictions[0],
            "possible_diseases": top_predictions
        }

# Lazy or singleton engine instance
engine = KnowledgeEngine(DATA_PATH)
