import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from providers.gemini_writing_provider import GeminiWritingProvider
from providers.config import ProviderConfig

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Load environment variables from .env if present
load_dotenv()

async def grade_task2(): 
    # 1. Configure API Key (Get from environment variable or fill in directly) 
    api_key = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE") 
    config = ProviderConfig(api_key=api_key, model_name="gemini-2.5-flash") 
    provider = GeminiWritingProvider(config) 

    # 2. Your Task 2 topic and essay 
    prompt_text = ( 
        "In the future, more people will choose to go on vacation in their own country " 
        "and not travel abroad on holiday. Do you agree or disagree?" 
    ) 

    essay_text = """Convenience of modern transportation shortens the distance between places and people embark on their travel more often than it has ever been, whether traveling domestically or aboard becomes another dilemma when people plan a trip. A short joy domestic travel seems optimistic for the masses. However, exotic culture and various weather which traveling aboard offers will never be found in travel at home. It is disagreed that more people will choose to spend their holidays at home instead of abroad.

Compared with domestic traveling, oversea travel seems irreplaceable in terms of exotic culture experience which is only available at the place of origin, for example, the folk music and operas will exclusively present locally, such distinctive culture shows are barely found in domestic travel. Therefore, a home trip will not be a substitution of foreign traveling.

Apart from culture, the differences in weather will not be observed in a home travel, for instance, tropical weather drastically differs from dessert weather which results in diversification of plants and animals. Experience in various weather and environment undoubtedly brings brand-new recognition of the world, such recognition cannot be achieved easily in home traveling, thus traveling aboard will be the only option for those who travel to retain more recognition of the world. 

In conclusion, the extraordinary cultural experience and diversification of environment under various weather undeniably adding joy we have ever experienced at home. For such reasons, it is crystal clear that travel abroad will remain trending and replacing domestic traveling to travel abroad will not be realized.""" 

    print("🚀 Sending article to AI Examiner Engine (Sprint 4 Resilient Engine)...") 

    result = await provider.evaluate( 
        prompt=prompt_text, 
        essay=essay_text, 
        task_type="TASK2" 
    ) 

    print("\n" + "=" * 60) 
    print(f"📊 IELTS WRITING TASK 2 ASSESSMENT RESULTS") 
    print("=" * 60) 
    print(f"🎯 OVERALL BAND SCORE: {result.overall_band}") 
    print("-" * 60) 
    print(f"🔹 Task Response (TR) : {result.task_achievement_score}") 
    print(f"🔹 Coherence & Cohesion (CC) : {result.coherence_cohesion_score}") 
    print(f"🔹 Lexical Resource (LR) : {result.lexical_resource_score}") 
    print(f"🔹 Grammatical Range (GRA) : {result.grammatical_range_score}") 
    print("=" * 60) 

    print("\n📝 ERROR FIX DETAILS & CRITERIA ANALYSIS:") 
    if hasattr(result, "feedback_detail"): 
        if isinstance(result.feedback_detail, dict): 
            print(json.dumps(result.feedback_detail, indent=2, ensure_ascii=False)) 
        else: 
            print(result.feedback_detail)

if __name__ == "__main__": 
    asyncio.run(grade_task2())
