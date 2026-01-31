"""
Code Analyzer - V1.0
Analyzes code snippets with LLM to determine root causes and resolutions
Integrates with Code Repository Manager and Stack Trace Parser
"""

import logging
from typing import Dict, List, Any, Optional
from enhanced_llm_api import EnhancedLLMAPI

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """
    Analyzes code snippets to determine root causes of exceptions
    Uses LLM to understand code context and suggest fixes
    """
    
    def __init__(self, llm_api: EnhancedLLMAPI):
        self.llm_api = llm_api
    
    def analyze_exception_with_code(
        self,
        exception_data: Dict[str, Any],
        code_snippets: List[Dict[str, Any]],
        kb_context: str = ""
    ) -> Dict[str, Any]:
        """
        Analyze exception with actual code context
        
        Args:
            exception_data: Exception information (type, message, stack trace)
            code_snippets: List of relevant code snippets from repository
            kb_context: Knowledge base context (if available)
        
        Returns:
            Enhanced analysis with code-based insights
        """
        logger.info("="*80)
        logger.info("CODE-BASED ANALYSIS - START")
        logger.info("="*80)
        logger.info(f"Exception: {exception_data.get('exception_type', 'Unknown')}")
        logger.info(f"Code snippets provided: {len(code_snippets)}")
        
        # Build enhanced prompt with code context
        prompt = self._build_code_analysis_prompt(exception_data, code_snippets, kb_context)
        
        # Check prompt size (stay under 120k tokens to leave room for response)
        prompt_size = len(prompt.split())
        if prompt_size > 30000:  # ~120k tokens / 4
            logger.warning(f"Prompt size large ({prompt_size} words), trimming code snippets...")
            prompt = self._trim_prompt(prompt, max_words=25000)
        
        logger.info(f"Prompt size: {prompt_size} words (~{prompt_size * 4} tokens)")
        
        # Get LLM analysis
        logger.info("Requesting LLM analysis...")
        raw_response = self.llm_api.generate_response(prompt, max_length=1500)
        
        logger.info(f"LLM response received ({len(raw_response)} chars)")
        
        # Parse response
        analysis = self._parse_code_analysis_response(raw_response)
        
        # Add metadata
        analysis['code_snippets_analyzed'] = len(code_snippets)
        analysis['has_code_context'] = len(code_snippets) > 0
        analysis['analysis_type'] = 'code_based' if code_snippets else 'standard'
        
        logger.info("="*80)
        logger.info("CODE-BASED ANALYSIS - COMPLETE")
        logger.info(f"Resolution: {analysis.get('resolution', 'UNDEFINED')}")
        logger.info(f"Confidence: {analysis.get('confidence_score', 0)}%")
        logger.info("="*80)
        
        return analysis
    
    def _build_code_analysis_prompt(
        self,
        exception_data: Dict[str, Any],
        code_snippets: List[Dict[str, Any]],
        kb_context: str
    ) -> str:
        """Build comprehensive prompt with code context"""
        
        # Start with exception details
        prompt_parts = [
            "You are analyzing a software exception with access to the actual source code.",
            "Analyze the code to determine the EXACT root cause and suggest a precise resolution.",
            "",
            "EXCEPTION DETAILS:",
            f"- Type: {exception_data.get('exception_type', 'Unknown')}",
            f"- Message: {exception_data.get('message', 'N/A')}",
            f"- Inner Exception: {exception_data.get('inner_exception_type', 'N/A')}",
            f"- Inner Message: {exception_data.get('inner_exception_message', 'N/A')}",
            f"- Error Code: {exception_data.get('error_code', 'N/A')}",
            "",
        ]
        
        # Add stack trace
        stack_trace = exception_data.get('stack_trace', '')
        if stack_trace:
            prompt_parts.extend([
                "STACK TRACE:",
                stack_trace[:1000],  # Limit stack trace length
                "",
            ])
        
        # Add code snippets (MOST IMPORTANT PART)
        if code_snippets:
            prompt_parts.extend([
                "="*80,
                "RELEVANT SOURCE CODE (from your actual repository):",
                "="*80,
            ])
            
            for i, snippet in enumerate(code_snippets[:5], 1):  # Limit to top 5
                file_path = snippet.get('file_path', 'Unknown')
                line_start = snippet.get('line_start', 0)
                line_end = snippet.get('line_end', 0)
                content = snippet.get('content', '')
                target_line = snippet.get('target_line')
                match_type = snippet.get('match_type', 'direct')
                
                prompt_parts.extend([
                    f"\n--- CODE SNIPPET {i} ({match_type} match) ---",
                    f"File: {file_path}",
                    f"Lines: {line_start}-{line_end}",
                ])
                
                if target_line:
                    prompt_parts.append(f"⚠️ ERROR OCCURRED AT LINE: {target_line}")
                
                prompt_parts.extend([
                    "",
                    content[:2000],  # Limit each snippet to ~2000 chars
                    f"--- END SNIPPET {i} ---",
                    "",
                ])
        else:
            prompt_parts.extend([
                "⚠️ Note: No source code available for analysis.",
                "Analysis will be based on exception details and KB context only.",
                "",
            ])
        
        # Add KB context if available
        if kb_context and kb_context != "No similar cases found in knowledge base (First occurrence or unique pattern).":
            prompt_parts.extend([
                "="*80,
                "KNOWLEDGE BASE CONTEXT:",
                "="*80,
                kb_context[:1500],  # Limit KB context
                "",
            ])
        
        # Add instructions
        prompt_parts.extend([
            "="*80,
            "ANALYSIS INSTRUCTIONS:",
            "="*80,
            "1. Examine the source code to identify the EXACT cause",
            "2. Look for:",
            "   - Null reference issues (objects not initialized)",
            "   - Missing error handling (try-catch blocks)",
            "   - Logic errors (incorrect conditions, loops)",
            "   - Data validation issues",
            "   - Configuration problems",
            "   - Database connection issues",
            "   - API integration errors",
            "",
            "3. Determine Resolution:",
            "   - PURGE: If this is a transient/duplicate/non-actionable error",
            "   - REPROCESS: If error can be fixed by retrying with correct data",
            "   - INVESTIGATE: If requires code changes or dev investigation",
            "",
            "4. Provide SPECIFIC, CODE-BASED root cause (not generic descriptions)",
            "",
            "RESPONSE FORMAT (JSON ONLY, no markdown):",
            "{",
            '  "Resolution": "PURGE or REPROCESS or INVESTIGATE",',
            '  "Root_Cause": "Detailed root cause with code reference (multi-line format: Summary, Explanation, Key Identifiers, Action)",',
            '  "Reasoning": "Why this resolution based on code analysis",',
            '  "Suggested_Action": "Specific action (reference code line if possible)",',
            '  "Code_Issue_Found": "Yes/No - was issue found in code",',
            '  "Affected_Code_File": "File path where issue is",',
            '  "Suggested_Fix": "Code-level fix if applicable",',
            '  "Confidence": 85,',
            '  "Similar_Patterns": "Based on KB context"',
            "}",
            "<END>"
        ])
        
        return '\n'.join(prompt_parts)
    
    def _trim_prompt(self, prompt: str, max_words: int) -> str:
        """Trim prompt to fit within token limits"""
        words = prompt.split()
        
        if len(words) <= max_words:
            return prompt
        
        # Strategy: Keep exception details and instructions, trim code snippets
        lines = prompt.split('\n')
        
        # Find code snippet sections
        essential_lines = []
        code_snippet_lines = []
        in_code_section = False
        
        for line in lines:
            if '--- CODE SNIPPET' in line:
                in_code_section = True
            elif '--- END SNIPPET' in line:
                in_code_section = False
                continue
            
            if in_code_section:
                code_snippet_lines.append(line)
            else:
                essential_lines.append(line)
        
        # Keep essential parts and trim code
        essential_text = '\n'.join(essential_lines)
        essential_words = len(essential_text.split())
        
        # Calculate how many words we can use for code
        words_for_code = max_words - essential_words
        
        if words_for_code > 0:
            code_text = '\n'.join(code_snippet_lines)
            code_words = code_text.split()[:words_for_code]
            code_text = ' '.join(code_words)
            
            return essential_text + '\n\n' + code_text
        else:
            return essential_text
    
    def _parse_code_analysis_response(self, raw_response: str) -> Dict[str, Any]:
        """Parse LLM response into structured format"""
        import json
        
        # Use existing validation from enhanced_llm_api
        validated = self.llm_api._validate_structured_response(raw_response)
        
        # Add code-specific fields if present in response
        try:
            # Try to extract additional fields if LLM provided them
            response_json = json.loads(raw_response) if raw_response.startswith('{') else {}
            
            validated['code_issue_found'] = response_json.get('Code_Issue_Found', 'Unknown')
            validated['affected_code_file'] = response_json.get('Affected_Code_File', 'Unknown')
            validated['suggested_fix'] = response_json.get('Suggested_Fix', 'Not provided')
            
        except:
            # If parsing fails, use defaults
            validated['code_issue_found'] = 'Unknown'
            validated['affected_code_file'] = 'Unknown'
            validated['suggested_fix'] = 'Not provided'
        
        return validated
    
    def create_code_context_summary(self, code_snippets: List[Dict[str, Any]]) -> str:
        """Create a summary of code context for display"""
        if not code_snippets:
            return "No code context available"
        
        summary_parts = [
            f"Analyzed {len(code_snippets)} code file(s):",
        ]
        
        for i, snippet in enumerate(code_snippets[:3], 1):  # Top 3
            file_path = snippet.get('file_path', 'Unknown')
            # Extract just filename
            filename = file_path.split('\\')[-1].split('/')[-1]
            
            match_type = snippet.get('match_type', 'direct')
            line_info = f"lines {snippet.get('line_start', 0)}-{snippet.get('line_end', 0)}"
            
            summary_parts.append(f"  {i}. {filename} ({line_info}) - {match_type} match")
        
        if len(code_snippets) > 3:
            summary_parts.append(f"  ... and {len(code_snippets) - 3} more")
        
        return '\n'.join(summary_parts)


class CodeBasedResolutionEnhancer:
    """
    Enhances resolution confidence and accuracy when code is available
    """
    
    def __init__(self):
        pass
    
    def enhance_confidence_with_code(
        self,
        base_confidence: int,
        code_analysis: Dict[str, Any]
    ) -> int:
        """
        Boost confidence when we have actual code context
        
        Args:
            base_confidence: Original confidence from KB/LLM
            code_analysis: Code analysis results
        
        Returns:
            Enhanced confidence score
        """
        enhanced = base_confidence
        
        # Boost if code issue was found
        if code_analysis.get('code_issue_found') == 'Yes':
            enhanced += 10
            logger.info(f"Confidence boost: +10 (code issue identified)")
        
        # Boost if we have code snippets
        snippets_count = code_analysis.get('code_snippets_analyzed', 0)
        if snippets_count > 0:
            boost = min(snippets_count * 3, 15)  # Up to +15
            enhanced += boost
            logger.info(f"Confidence boost: +{boost} (code context available)")
        
        # Boost if we have a specific fix suggestion
        if code_analysis.get('suggested_fix') and code_analysis['suggested_fix'] != 'Not provided':
            enhanced += 5
            logger.info(f"Confidence boost: +5 (specific fix suggested)")
        
        # Cap at 95% (leave room for uncertainty)
        enhanced = min(enhanced, 95)
        
        return enhanced
    
    def determine_requires_review(
        self,
        confidence: int,
        code_analysis: Dict[str, Any],
        threshold: int = 70
    ) -> bool:
        """
        Determine if exception requires review based on confidence and code analysis
        """
        # Standard confidence check
        if confidence < threshold:
            return True
        
        # Even with high confidence, require review if no code issue found
        if code_analysis.get('code_issue_found') == 'No' and confidence < 85:
            return True
        
        # Require review for INVESTIGATE resolutions
        if code_analysis.get('resolution') == 'INVESTIGATE':
            return True
        
        return False


if __name__ == "__main__":
    # Test code analyzer
    print("✅ Code Analyzer module loaded successfully!")
    print("Ready to analyze exceptions with actual source code context")
