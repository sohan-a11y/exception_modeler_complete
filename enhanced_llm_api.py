
# [2025-11-19] Enhanced LLM API with KB Resolution Override
# Purpose: Ensure KB resolution is used when similarity >= 70%

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForCausalLM
import logging
from typing import Dict, Any, List
import requests
import os
import torch

logger = logging.getLogger(__name__)

class EnhancedLLMAPI:
    """
    Enhanced LLM API supporting multiple providers:
    - Local models (T5, Phi-3, Mistral, Llama, etc.)
    - API-based models (Groq, Together AI, HuggingFace, Ollama)
    """

    def __init__(self, model_config: Dict[str, Any]):
        self.model_config = model_config
        self.model_name   = model_config['name']
        self.model_type   = model_config.get('type', 'local')
        self.provider     = model_config.get('provider', 'local')
        self.max_length   = model_config.get('max_length', 4096)

        self.device    = "cuda" if torch.cuda.is_available() else "cpu"
        self.model     = None
        self.tokenizer = None

        if self.model_type == 'local':
            self._load_local_model()
        elif self.model_type == 'api':
            self._setup_api()

        # --- Problem 2: Warm-up call to avoid first-inference hiccup ---
        try:
            _ = self.generate_response("{}", max_length=16)  # tiny deterministic prompt
            logger.info("LLM warm-up completed.")
        except Exception as e:
            logger.warning(f"Warm-up failed (continuing): {e}")  # warm-up failure should not block
        # ----------------------------------------------------------------

        logger.info(f"✅ Enhanced LLM API initialized: {self.model_name} ({self.model_type})")

    def _load_local_model(self):
        """Load local transformer model"""
        try:
            logger.info(f"Loading local model: {self.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            # Determine model architecture
            if any(x in self.model_name.lower() for x in ["t5", "flan"]):
                self.model = AutoModelForSeq2SeqLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:  # Causal LM (GPT, Phi, Mistral, Llama, etc.)
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    trust_remote_code=True  # For Phi-3 and similar models
                )
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"✅ Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"❌ Error loading model: {str(e)}")
            raise

    def _setup_api(self):
        """Setup API connection"""
        try:
            if self.provider == 'groq':
                from groq import Groq
                api_key = os.getenv("GROQ_API_KEY")
                if not api_key:
                    raise ValueError("GROQ_API_KEY not set")
                self.client = Groq(api_key=api_key)
            elif self.provider == 'together':
                api_key = os.getenv("TOGETHER_API_KEY")
                if not api_key:
                    raise ValueError("TOGETHER_API_KEY not set")
                self.api_key      = api_key
                self.api_endpoint = "https://api.together.xyz/v1/chat/completions"
            elif self.provider == 'huggingface':
                api_key = os.getenv("HUGGINGFACE_API_KEY")
                if not api_key:
                    raise ValueError("HUGGINGFACE_API_KEY not set")
                self.api_key      = api_key
                self.api_endpoint = f"https://api-inference.huggingface.co/models/{self.model_name}"
            elif self.provider == 'ollama':
                self.api_endpoint = "http://localhost:11434/api/generate"
                logger.info(f"✅ Ollama setup complete - endpoint: {self.api_endpoint}")
            logger.info(f"✅ API setup complete for {self.provider}")
        except Exception as e:
            logger.error(f"❌ Error setting up API: {str(e)}")
            raise

    def generate_response(self, prompt: str, max_length: int = None) -> str:
        """Generate response using local or API model"""
        max_length = max_length or self.max_length
        if self.model_type == 'local':
            return self._generate_local(prompt, max_length)
        elif self.model_type == 'api':
            return self._generate_api(prompt, max_length)

    def _generate_local(self, prompt: str, max_length: int) -> str:
        """Deterministic local generation"""
        try:
            inputs = self.tokenizer(
                prompt, return_tensors="pt", max_length=4096, truncation=True, padding=True
            ).to(self.device)

            with torch.no_grad():
                if any(x in self.model_name.lower() for x in ["t5", "flan"]):
                    outputs = self.model.generate(
                        **inputs,
                        max_length=max_length,
                        num_beams=1,     # deterministic
                        do_sample=False, # deterministic
                        temperature=0.0  # deterministic
                    )
                else:
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_length,
                        num_beams=1,     # deterministic
                        do_sample=False, # deterministic
                        temperature=0.0, # deterministic
                        pad_token_id=self.tokenizer.eos_token_id,
                    )
            text = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            return text
        except Exception as e:
            logger.error(f"Error generating local response: {str(e)}")
            # Safe fallback: return minimal valid JSON (prevents downstream nulls)
            return '{"Resolution":"REPROCESS","Root_Cause":"Model error","Reasoning":"Local gen failed","Suggested_Action":"Retry","Confidence":60,"Similar_Patterns":"None"}'

    def _generate_api(self, prompt: str, max_length: int) -> str:
        """Deterministic API generation"""
        try:
            if self.provider == 'groq':
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_length,
                    temperature=0.0,  # deterministic
                    top_p=1.0
                )
                return response.choices[0].message.content

            elif self.provider == 'together':
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_length,
                    "temperature": 0.0,  # deterministic
                    "top_p": 1.0
                }
                response = requests.post(self.api_endpoint, headers=headers, json=data, timeout=60)
                response.raise_for_status()
                return response.json()['choices'][0]['message']['content']

            elif self.provider == 'huggingface':
                headers = {"Authorization": f"Bearer {self.api_key}"}
                data = {
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": max_length,
                        "temperature": 0.0,  # deterministic
                        "top_p": 1.0,
                        "return_full_text": False
                    }
                }
                response = requests.post(self.api_endpoint, headers=headers, json=data, timeout=60)
                response.raise_for_status()
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get('generated_text', str(result))
                return str(result)

            elif self.provider == 'ollama':
                headers = {"Content-Type": "application/json"}
                data = {
                    "model": self.model_name,  # e.g., "llama3.2:3b"
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.0,      # deterministic
                        "top_p": 1.0,            # deterministic
                        "mirostat": 0,           # deterministic
                        "seed": 42,              # reproducible
                        "repeat_penalty": 1.1,
                        "num_predict": max_length,
                        "stop": ["<END>"]        # stop at explicit marker in prompt
                    }
                }
                response = requests.post(self.api_endpoint, headers=headers, json=data, timeout=120)
                response.raise_for_status()
                result = response.json()
                return result.get('response', '{"Resolution":"REPROCESS","Root_Cause":"API error","Reasoning":"No response","Suggested_Action":"Retry","Confidence":55,"Similar_Patterns":"None"}')

        except Exception as e:
            logger.error(f"Error generating API response: {str(e)}")
            return f"API Error: {str(e)}"

    # [2025-11-19] Enhanced JSON validator with resolution sanitization
    # Purpose: Ensure single valid resolution and handle KB override
    # [2025-11-21] Added backward compatibility for ESCALATE→INVESTIGATE
    # [2025-11-21] Enhanced confidence calculation for KB-matched resolutions
    def _validate_structured_response(self, text: str, kb_resolution: str = None, kb_similarity: float = 0.0) -> dict:
        """
        Load JSON safely; ensure required keys; provide uppercase Resolution and default values.
        """
        # [2025-11-19] Enhanced validation to prevent invalid resolution formats like 'PURGE|REPROCESS|INVESTIGATE'
        # Purpose: Ensure only single valid resolution value (PURGE, REPROCESS, or INVESTIGATE)
        import json
        try:
            data        = json.loads(text)
            # [2025-11-19] Changed default from REPROCESS to UNDEFINED
            # Purpose: Show UNDEFINED when resolution is not available
            resolution  = str(data.get("Resolution", data.get("resolution", ""))).upper() or "UNDEFINED"
            
            # [2025-11-19] Sanitize resolution to ensure single valid value
            # Purpose: Fix issue where LLM returns multiple resolutions separated by pipes
            resolution = resolution.strip()
            
            # If resolution contains multiple values (pipe-separated), extract the first valid one
            if '|' in resolution or ' ' in resolution:
                # Split by pipe or space and find first valid resolution
                parts = resolution.replace('|', ' ').replace('THE', '').replace('MESSAGE', '').replace('TO', '').replace('DEV', '').replace('TEAM', '').replace('FOR', '').replace('ANALYSIS', '').split()
                for part in parts:
                    part_clean = part.strip()
                   
                    # Purpose: Accept ESCALATE and auto-convert to INVESTIGATE
                    if part_clean in ['PURGE', 'REPROCESS', 'INVESTIGATE', 'ESCALATE']:
                        resolution = 'INVESTIGATE' if part_clean == 'ESCALATE' else part_clean
                        logger.warning(f"Sanitized multi-value resolution to: {resolution}")
                        break
                else:
                    # No valid resolution found, default to UNDEFINED
                    resolution = "UNDEFINED"
                    logger.warning(f"Invalid resolution format detected, defaulting to UNDEFINED")
                       
            # Purpose: Ensure all ESCALATE values are converted to INVESTIGATE
            if resolution == 'ESCALATE':
                logger.info(f"Converting legacy ESCALATE to INVESTIGATE")
                resolution = 'INVESTIGATE'
            
            # [2025-11-24] Extract confidence early to prevent NameError in KB boost logic
            # Date: 2025-11-24
            # Reason: confidence variable was referenced before being defined (lines 266-273)
            # Purpose: Extract confidence from JSON before using it in KB similarity boost
            conf_raw = data.get("Confidence", data.get("confidence", 65))
            try:
                confidence = int(conf_raw)
            except Exception:
                confidence = 65
            
            # [2025-12-03] FIX 5: Strengthened KB resolution override with detailed logging
            # Date: 2025-12-03 15:14 UTC-06:00
            # Reason: Ensure KB resolution ALWAYS overrides LLM when available
            # Purpose: Final safety net - even if LLM returns wrong resolution, KB wins
            if kb_resolution and kb_resolution in ['PURGE', 'REPROCESS', 'INVESTIGATE']:
                if resolution != kb_resolution:
                    logger.warning(f"⚠️ LLM resolution '{resolution}' differs from KB resolution '{kb_resolution}'")
                    logger.info(f"🔄 Overriding LLM resolution with KB resolution: {kb_resolution}")
                    resolution = kb_resolution
                else:
                    logger.info(f"✅ LLM resolution '{resolution}' matches KB resolution - no override needed")
                
                # [2025-12-03] Boost confidence based on KB similarity with logging
                original_confidence = confidence
                if kb_similarity >= 0.95:
                    confidence = max(confidence, 90)
                    logger.info(f"🚀 Confidence boost: {original_confidence}% → {confidence}% (KB similarity: {kb_similarity:.1%})")
                elif kb_similarity >= 0.85:
                    confidence = max(confidence, 80)
                    logger.info(f"🚀 Confidence boost: {original_confidence}% → {confidence}% (KB similarity: {kb_similarity:.1%})")
                elif kb_similarity >= 0.70:
                    confidence = max(confidence, 70)
                    logger.info(f"🚀 Confidence boost: {original_confidence}% → {confidence}% (KB similarity: {kb_similarity:.1%})")
            elif kb_resolution:
                logger.error(f"❌ KB resolution '{kb_resolution}' is not in standard format! This should not happen.")
                logger.error(f"❌ Using LLM resolution '{resolution}' as fallback")
            
            # [2025-12-03] Final validation with comprehensive logging
            # Date: 2025-12-03 15:14 UTC-06:00
            if resolution not in ['PURGE', 'REPROCESS', 'INVESTIGATE', 'UNDEFINED']:
                logger.error(f"❌ Invalid resolution '{resolution}' after all processing!")
                logger.error(f"❌ This indicates a serious issue in the pipeline")
                logger.error(f"❌ KB resolution was: {kb_resolution}")
                logger.error(f"❌ LLM raw response: {text[:200]}...")
                logger.warning(f"⚠️ Defaulting to UNDEFINED as last resort")
                resolution = "UNDEFINED"
            
            root_cause  = str(data.get("Root_Cause", data.get("root_cause", ""))) or "Not provided"
            reasoning   = str(data.get("Reasoning", data.get("reasoning", ""))) or "Not provided"
            action      = str(data.get("Suggested_Action", data.get("suggested_action", ""))) or "Not provided"
            patterns    = str(data.get("Similar_Patterns", data.get("similar_patterns", ""))) or "None identified"
            return {
                "resolution":       resolution,
                "root_cause":       root_cause,
                "reasoning":        reasoning,
                "suggested_action": action,
                "confidence":       confidence,
                "similar_patterns": patterns
            }
        except Exception as e:
            # [2025-11-19] Changed default from REPROCESS to UNDEFINED
            return {
                "resolution":       kb_resolution if kb_resolution else "UNDEFINED",
                "root_cause":       "Not provided",
                "reasoning":        "Not provided",
                "suggested_action": "Not provided",
                "confidence":       65,
                "similar_patterns": "None identified",
                "requires_review":  True,
                "_error":          f"validator_failed: {e}"
            }

    # [2025-11-19] Enhanced analysis with KB resolution override
    # Purpose: Extract KB resolution and override LLM when similarity >= 70%
    # [2025-11-21] Added backward compatibility for ESCALATE→INVESTIGATE   
    def analyze_with_enhanced_prompt(self, exception_data: Dict[str, Any],
                                     kb_context: str = "",
                                     use_deep_analysis: bool = False,
                                     similar_cases: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        ULTRA-STABLE analysis: prompt returns ONLY JSON; we validate and return a dict.
        """
        # [2025-12-03] FIX 3: Simplified KB resolution extraction + Top 5 logging
        # Date: 2025-12-03 15:14 UTC-06:00
        # Reason: Previous logic was complex and could fail with non-standard KB resolutions
        # Purpose: KB now stores only standard resolutions (PURGE/REPROCESS/INVESTIGATE), so extraction is simple
        # Impact: Eliminates root cause of UNDEFINED resolutions from KB matches
        kb_resolution = None
        kb_root_cause = None
        kb_action = None
        max_similarity = 0.0
        
        logger.info(f"="*80)
        logger.info(f"KB RESOLUTION EXTRACTION - START")
        logger.info(f"="*80)
        
        if similar_cases:
            max_similarity = max([case.get('similarity', 0) for case in similar_cases])
            logger.info(f"🔍 KB Matching - Found {len(similar_cases)} similar cases")
            logger.info(f"📊 Max similarity: {max_similarity:.1%}")
            
            # [2025-12-03] NEW: Log top 5 similar cases for transparency
            # Date: 2025-12-03 15:14 UTC-06:00
            # Purpose: Show user what KB cases were found and their similarity scores
            logger.info(f"\n📊 TOP {min(5, len(similar_cases))} SIMILAR CASES FROM KB:")
            for i, case in enumerate(similar_cases[:5], 1):
                case_meta = case.get('metadata', {})
                case_sim = case.get('similarity', 0)
                case_res = case_meta.get('resolution', 'N/A')
                case_type = case_meta.get('exception_type', 'N/A')
                logger.info(f"  {i}. Similarity: {case_sim:.1%} | Resolution: {case_res} | Type: {case_type[:50]}...")
            logger.info("")
            
            if max_similarity >= 0.70:
                # Get the best match from KB
                best_match = max(similar_cases, key=lambda x: x.get('similarity', 0))
                kb_metadata = best_match.get('metadata', {})
                
                # [2025-12-03] FIX 3: Simple extraction - KB resolutions are already normalized
                kb_resolution = kb_metadata.get('resolution', None)
                logger.info(f"📋 KB Resolution (raw from storage): '{kb_resolution}'")
                
                # Validate it's a standard resolution
                if kb_resolution in ['PURGE', 'REPROCESS', 'INVESTIGATE']:
                    logger.info(f"✅ KB resolution is valid: {kb_resolution} (similarity: {max_similarity:.1%})")
                else:
                    logger.error(f"❌ KB resolution '{kb_resolution}' is NOT standard! This should not happen after normalization fix.")
                    kb_resolution = None
                
                # [2025-12-03] Extract Root_Cause and Action from KB with logging
                # Date: 2025-12-03 15:14 UTC-06:00
                kb_root_cause = (
                    kb_metadata.get('root_cause') or 
                    kb_metadata.get('Root_Cause') or 
                    kb_metadata.get('Summary') or 
                    kb_metadata.get('summary') or 
                    ''
                )
                kb_action = (
                    kb_metadata.get('action') or 
                    kb_metadata.get('Action') or 
                    kb_metadata.get('Suggested Step') or 
                    kb_metadata.get('suggested_step') or 
                    kb_metadata.get('Suggested_Action') or 
                    kb_metadata.get('suggested_action') or 
                    ''
                )
                
                logger.info(f"📝 KB Root Cause: {kb_root_cause[:80] if kb_root_cause else 'N/A'}...")
                logger.info(f"📝 KB Action: {kb_action[:80] if kb_action else 'N/A'}...")
                logger.info(f"✅ KB data extraction complete - Will use KB resolution: {kb_resolution}")
            else:
                logger.warning(f"⚠️ KB similarity {max_similarity:.1%} is below 70% threshold")
                logger.warning(f"⚠️ KB resolution will NOT be used - LLM will generate resolution")
        else:
            logger.info(f"🔍 No similar cases found in KB")
        
        logger.info(f"="*80)
        logger.info(f"KB RESOLUTION EXTRACTION - END")
        logger.info(f"="*80)
        
        analysis_type = "deep_constructive" if use_deep_analysis else "constructive"

        # [2025-12-03] FIX 4: Improved LLM prompt - less strict, clearer instructions
        # Date: 2025-12-03 15:14 UTC-06:00
        # Reason: Previous prompt had contradictions ("use verbatim" vs "must be PURGE/REPROCESS/INVESTIGATE")
        # Purpose: Make prompt clearer and less strict while ensuring valid JSON output
        # Impact: LLM understands KB resolutions are already normalized
        
        logger.info(f"="*80)
        logger.info(f"LLM PROMPT GENERATION - START")
        logger.info(f"="*80)
        logger.info(f"🤖 Analysis type: {analysis_type}")
        logger.info(f"📊 KB resolution available: {kb_resolution if kb_resolution else 'No'}")
        logger.info(f"📊 KB similarity: {max_similarity:.1%}")
        
        prompt = f"""
Return ONLY valid JSON (no prose, no markdown, no code blocks).
Use exactly these keys: Resolution, Root_Cause, Reasoning, Suggested_Action, Confidence, Similar_Patterns.

Rules:
- If KB similarity ≥ 70%, the KB Resolution is already in standard format (PURGE/REPROCESS/INVESTIGATE). Use it exactly as provided.
- If KB similarity < 70%, analyze the exception and choose: PURGE, REPROCESS, or INVESTIGATE.
- Confidence must be an integer in [0,100]. Use 80-95 for high KB matches.
- Root_Cause should be detailed with this format:
  Summary: [brief summary]
  Explanation: [detailed explanation]
  Key Identifiers:
  - [identifier 1]
  - [identifier 2]
  - [identifier 3] 
  - [identifier 4]            
  Action: [recommended action]

EXCEPTION:
- ID: {exception_data.get('exception_id','Unknown')}
- Module: {exception_data.get('module','Unknown')}
- Type: {exception_data.get('exception_type','')}
- Message: {exception_data.get('message','N/A')}
- InnerExceptionType: {exception_data.get('inner_exception_type','N/A')}
- InnerExceptionMessage: {exception_data.get('inner_exception_message','N/A')}
- ErrorCode: {exception_data.get('error_code','N/A')}
- StackTrace: {exception_data.get('stack_trace','N/A')}

KB_CONTEXT:
{kb_context if kb_context else "No similar cases found in knowledge base"}

RESPONSE FORMAT (JSON ONLY):
{{
  "Resolution": "PURGE or REPROCESS or INVESTIGATE",
  "Root_Cause": "Summary: [summary]\\nExplanation: [explanation]\\nKey Identifiers:\\n- [identifier]\\nAction: [action]",
  "Reasoning": "Brief explanation of why this resolution was chosen",
  "Suggested_Action": "Specific action to take",
  "Confidence": 85,
  "Similar_Patterns": "None identified"
}}

IMPORTANT: 
1. Resolution must be one of: PURGE, REPROCESS, or INVESTIGATE (single word only).
2. If KB provided a resolution, use it exactly - it's already validated.
3. Root_Cause must be a single JSON string with embedded newlines (\\n).
4. Return ONLY the JSON object, nothing else.
<END>
"""
        logger.info(f"📝 Prompt generated ({len(prompt)} chars)")
        logger.info(f"="*80)
        logger.info(f"LLM PROMPT GENERATION - END")
        logger.info(f"="*80)
        # [2025-12-03] Generate LLM response with logging
        # Date: 2025-12-03 15:14 UTC-06:00
        logger.info(f"="*80)
        logger.info(f"LLM RESPONSE GENERATION - START")
        logger.info(f"="*80)
        
        raw = self.generate_response(prompt, max_length=1200)
        
        logger.info(f"📥 LLM Raw Response ({len(raw)} chars):")
        logger.info(f"-"*80)
        logger.info(raw[:500] + ("..." if len(raw) > 500 else ""))
        logger.info(f"-"*80)
        logger.info(f"="*80)
        logger.info(f"LLM RESPONSE GENERATION - END")
        logger.info(f"="*80)
        
        # [2025-12-03] FIX 5: Pass KB resolution to validator with logging
        # Date: 2025-12-03 15:14 UTC-06:00
        logger.info(f"="*80)
        logger.info(f"RESPONSE VALIDATION - START")
        logger.info(f"="*80)
        logger.info(f"🔍 Validating LLM response...")
        logger.info(f"📊 KB resolution to use if needed: {kb_resolution}")
        logger.info(f"📊 KB similarity: {max_similarity:.1%}")
        
        parsed = self._validate_structured_response(raw, kb_resolution=kb_resolution, kb_similarity=max_similarity if similar_cases else 0.0)
        
        # [2025-12-03] NEW: Log what LLM chose vs what we're using
        # Date: 2025-12-03 15:14 UTC-06:00
        # Purpose: Show transparency in resolution selection process
        llm_chosen_resolution = parsed.get('resolution', 'UNDEFINED')
        logger.info(f"\n🤖 LLM CHOSE: {llm_chosen_resolution}")
        if kb_resolution and kb_resolution != llm_chosen_resolution:
            logger.info(f"🔄 OVERRIDING with KB resolution: {kb_resolution}")
            logger.info(f"✅ FINAL RESOLUTION: {kb_resolution}")
        else:
            logger.info(f"✅ FINAL RESOLUTION: {llm_chosen_resolution}")
        logger.info("")
        
        logger.info(f"✅ Validation complete")
        logger.info(f"📝 Parsed confidence: {parsed.get('confidence', 0)}")
        logger.info(f"="*80)
        logger.info(f"RESPONSE VALIDATION - END")
        logger.info(f"="*80)
        

        # [2025-12-02] ENHANCED: Intelligent merge of KB + LLM with coherence check
        # Date: 2025-12-02
        # Reason: Root_Cause, Resolution, Suggested_Action must be in sync and coherent
        # Purpose: Use KB when available (similarity >= 70%), enhance with LLM format, ensure no blanks
        
        # Get LLM's generated analysis (based on KB context)
        llm_root_cause = parsed.get("root_cause", "Not provided")
        llm_action = parsed.get("suggested_action", "Not provided")
        
        # STRATEGY: When KB match exists (similarity >= 70%), prioritize KB data
        # But use LLM to expand KB summary into proper multi-line format
        
        # [2025-12-02] FIXED: Use KB data when similarity >= 70%, even if resolution is non-standard
        # 1. ROOT CAUSE: Intelligent selection with format enhancement
        if max_similarity >= 0.70 and (kb_root_cause or kb_resolution):
            # KB match exists (similarity >= 70%) - prioritize KB data
            if kb_root_cause:
                # KB has root cause data - check format quality
                kb_has_full_format = '\n' in kb_root_cause and 'Explanation:' in kb_root_cause and 'Action:' in kb_root_cause
                llm_has_full_format = '\n' in llm_root_cause and 'Summary:' in llm_root_cause and 'Action:' in llm_root_cause
                
                if kb_has_full_format:
                    # KB has complete multi-line format - use it directly
                    final_root_cause = kb_root_cause
                    logger.info(f"✅ Using KB root cause (complete format, similarity: {max_similarity:.1%})")
                elif llm_has_full_format and len(llm_root_cause) > len(kb_root_cause):
                    # LLM expanded KB summary into full format - use LLM's expansion
                    final_root_cause = llm_root_cause
                    logger.info(f"✅ Using LLM root cause (expanded KB data into full format, {len(llm_root_cause)} chars)")
                else:
                    # Fallback to KB (even if summary only)
                    final_root_cause = kb_root_cause
                    logger.info(f"✅ Using KB root cause (KB match, similarity: {max_similarity:.1%})")
            elif llm_root_cause != "Not provided":
                # KB match exists but no root cause in KB - use LLM
                final_root_cause = llm_root_cause
                logger.info(f"✅ Using LLM root cause (KB match but no KB root cause)")
            else:
                # Should not happen - KB match but no data
                final_root_cause = "Not provided"
                logger.error(f"❌ KB match (similarity: {max_similarity:.1%}) but no root cause data available")
        elif llm_root_cause != "Not provided":
            # No KB match or KB not available - use LLM
            final_root_cause = llm_root_cause
            logger.info(f"✅ Using LLM root cause (no KB match or KB unavailable)")
        else:
            # Fallback - should not happen
            final_root_cause = kb_root_cause if kb_root_cause else "Not provided"
            logger.warning(f"⚠️ Using fallback root cause")
        
        # 2. REASONING: Always show KB Match format when KB similarity >= 70%
        if kb_resolution and max_similarity >= 0.70:
            final_reasoning = f"KB Match (similarity: {max_similarity:.1%})"
        else:
            final_reasoning = parsed.get("reasoning", "Not provided")
        
        # 3. SUGGESTED ACTION: Ensure coherence with Resolution
        # Priority: KB action > LLM action > fallback based on resolution
        if kb_action:
            final_action = kb_action
        elif llm_action != "Not provided":
            final_action = llm_action
        else:
            # Fallback: Generate action based on resolution to ensure coherence
            resolution = parsed.get("resolution", "UNDEFINED")
            if resolution == "PURGE":
                final_action = "Message Can be purged"
            elif resolution == "REPROCESS":
                final_action = "Reprocess the message with corrected data"
            elif resolution == "INVESTIGATE":
                final_action = "Escalate to dev team for investigation"
            else:
                final_action = "Review and determine appropriate action"
            logger.info(f"✅ Generated fallback action based on resolution: {resolution}")
        
        # 4. COHERENCE CHECK: Ensure Root_Cause, Resolution, Suggested_Action are aligned
        # If Root_Cause mentions "purge" but Resolution is "REPROCESS", log warning
        resolution = parsed.get("resolution", "UNDEFINED")
        if "purge" in final_root_cause.lower() and resolution != "PURGE":
            logger.warning(f"⚠️ Coherence issue: Root cause mentions purge but resolution is {resolution}")
        if "reprocess" in final_root_cause.lower() and resolution != "REPROCESS":
            logger.warning(f"⚠️ Coherence issue: Root cause mentions reprocess but resolution is {resolution}")
        
        return {
            "resolution":         resolution,
            "root_cause":         final_root_cause,
            "reasoning":          final_reasoning,
            "suggested_action":   final_action,
            "confidence_score":   parsed.get("confidence", 65),
            "similar_past_cases": parsed.get("similar_patterns", "None identified"),
            "analysis_type":      analysis_type,
            "requires_review":    parsed.get("requires_review", False)
        }

    def classify_exception(self, exception_data: Dict[str, Any]) -> str:
        """Enhanced exception classification (deterministic generation used)"""
        prompt = f"""Classify this software exception precisely:
EXCEPTION:
- Type: {exception_data.get('exception_type', '')}
- Message: {exception_data.get('message', 'N/A')[:300]}
- Error Code: {exception_data.get('error_code', 'N/A')}
- Severity: {exception_data.get('severity', 'Unknown')}
CATEGORIES:
1. DatabaseError (connection, query, constraint, deadlock)
2. NetworkError (timeout, connection refused, DNS)
3. ValidationError (data validation, format mismatch)
4. ConfigurationError (missing config, invalid settings)
5. PermissionError (access denied, authentication)
6. TimeoutError (operation timeout, expired)
7. NullReferenceError (null pointer, missing data)
8. ConcurrencyError (thread conflicts, race conditions, concurrency)
9. IntegrationError (API failures, external services)
10. BusinessLogicError (logic failures, rule violations, missing, not present)
11. EntityException (underlying provider failed on open)
12. UnknownError
Respond with ONLY the category name:"""
        response = self.generate_response(prompt, max_length=512)
        return response.strip()

    def _infer_confidence(self, result: Dict[str, Any], exception_data: Dict[str, Any], kb_context: str) -> int:
        """Existing confidence inference (kept for compatibility)"""
        confidence = 65  # baseline
        if kb_context and len(kb_context) > 100:
            confidence += 15
        # [2025-11-21] Removed INVESTIGATE penalty - all resolutions should be treated equally
        # Date: 2025-11-21
        # Reason: INVESTIGATE is a valid resolution type and should not be penalized
        # Purpose: Fair confidence scoring across PURGE, REPROCESS, and INVESTIGATE
        if result.get('resolution') in ['PURGE', 'REPROCESS', 'INVESTIGATE']:
            confidence += 10
        if len(result.get('root_cause', '')) > 100:
            confidence += 8
        if exception_data.get('error_code') and str(exception_data['error_code']).strip():
            confidence += 7
        if exception_data.get('frequency', 1) > 2:
            confidence += 5
        return min(98, max(40, confidence))

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        info = {
            'model_name': self.model_name,
            'model_type': self.model_type,
            'provider':   self.provider,
            'max_length': self.max_length
        }
        if self.model_type == 'local' and self.model:
            info['device']     = self.device
            info['parameters'] = sum(p.numel() for p in self.model.parameters())
        return info
