import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Ensure smooth Vietnamese Unicode printing on Windows console
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from providers.gemini_writing_provider import GeminiWritingProvider
from providers.config import ProviderConfig

async def grade_task1(): 
    api_key = os.getenv("GEMINI_API_KEY") 
    if not api_key: 
        print("❌ Error: GEMINI_API_KEY not found in .env file or environment variable!") 
        return 

    config = ProviderConfig(api_key=api_key, model_name="gemini-2.5-flash") 
    provider = GeminiWritingProvider(config) 

    # 1. The question comes with Ground Truth Data Table & Image Description so that the AI does not have data illusion 
    prompt_text = """
The bar chart below shows the percentage of home ownership across different household types in a North American nation in 1990 and 2010, with projections for 2030.
Summarize the information by selecting and reporting the main features, and make comparisons where relevant.

[CHART GROUND TRUTH DATA TABLE & KEY FEATURES]
- Chart Type: Bar chart (Percentage of home ownership by household type).
- Timeframe: 1990, 2010 (Recorded), 2030 (Projected/Predicted).
- Household Cohorts & Statistics (%): 
* Married-couple household: 1990: ~62%, 2010: ~50%, 2030: 44% (Dominant, consistent downward trend). 
* Single-person household: 1990: 18%, 2010: 25% (+7%), 2030: 30% (Upward trend). 
* Single-parent households: 1990: 14%, 2010: 17%, 2030: 20% (Upward trend). 
* Multi-generational households: 1990: 4%, 2010: 6%, 2030: 6% (Lowest share, rises slightly then stabilizes).
- Key Highlights (Overview requirements): 
* Married couples have the highest proportion throughout, but represent the only cohort with a continuous decline. 
* All other household types increase, with multi-generational families remaining the smallest group.
""" 

    # 2. Candidate's work 
    essay_text = """The bar chart compares the cohorts of families owing house in a North American nation from 1990 and 2010, along, following with a prediction for 2030.
Overall, most catergorized households have become more prelevant, except for married couple families which noticably have been the dominant throughout the time frame, contrasting the multi-generational figures.
Single-parent and single-person show a similar upward trend between 1990 and 2010. The percentage for families with either dad or mom doing parenting rose steadily every reported decade from 14% to 17%. The share of individuals living on their own experienced a growth of 7%, rising from 18% in the first year. Furthermore, the proportion of both cohorts are expected to continue growing, to reach 20% and 30%, respectively.
Households owned by married- couple on the other hand, became less prelevent in 2 recorded decades. From more than 60% down to approxiamtely 50% in the 30-year interval, and its number is predicted to keep falling to 44% in 2030. On the other hand, multi-generational share increased from 4% to 6% in the first 2 years examined, it is then forcasted to reamain unchanged in the final year.""" 

    print("🚀 Sending Writing Task 1 to Gemini AI Examiner Engine...") 

    result = await provider.evaluate( 
        prompt=prompt_text, 
        essay=essay_text, 
        task_type="TASK1" 
    ) 

    print("\n" + "=" * 65) 
    print("📊 IELTS WRITING TASK 1 ASSESSMENT RESULT") 
    print("=" * 65) 
    print(f"🎯 OVERALL BAND SCORE: {result.overall_band}") 
    print("-" * 65) 
    print(f"🔹 Task Achievement (TA)     : {result.task_achievement_score}") 
    print(f"🔹 Coherence & Cohesion (CC) : {result.coherence_cohesion_score}") 
    print(f"🔹 Lexical Resource (LR)     : {result.lexical_resource_score}") 
    print(f"🔹 Grammatical Range (GRA)   : {result.grammatical_range_score}") 
    print("=" * 65) 

    print("\n📝 ERROR FIX DETAILS & CRITERIA ANALYSIS (JSON FEEDBACK):") 
    if hasattr(result, "feedback_detail"): 
        if isinstance(result.feedback_detail, dict): 
            print(json.dumps(result.feedback_detail, indent=2, ensure_ascii=False)) 
        else: 
            print(result.feedback_detail)

if __name__ == "__main__": 
    asyncio.run(grade_task1())
