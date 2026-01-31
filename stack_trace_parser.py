"""
Stack Trace Parser - V1.0
Extracts file paths, line numbers, and method names from exception stack traces
Supports multiple languages: C#, Python, Java, JavaScript, etc.
"""

import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class StackTraceParser:
    """
    Parses stack traces to extract useful information:
    - File paths
    - Line numbers
    - Method/function names
    - Exception types
    """
    
    # Regular expressions for different stack trace formats
    PATTERNS = {
        # C# stack trace pattern
        # Example: at MyNamespace.MyClass.MyMethod(String param) in C:\path\to\file.cs:line 123
        'csharp': re.compile(
            r'at\s+(?P<namespace>[\w.]+)\.(?P<method>[\w<>]+)\([^)]*\)\s+in\s+(?P<file>[^:]+):line\s+(?P<line>\d+)',
            re.MULTILINE
        ),
        
        # Python stack trace pattern
        # Example: File "C:\path\to\file.py", line 123, in my_function
        'python': re.compile(
            r'File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+),\s+in\s+(?P<method>\w+)',
            re.MULTILINE
        ),
        
        # Java stack trace pattern
        # Example: at com.example.MyClass.myMethod(MyClass.java:123)
        'java': re.compile(
            r'at\s+(?P<package>[\w.]+)\.(?P<method>\w+)\((?P<file>[\w.]+):(?P<line>\d+)\)',
            re.MULTILINE
        ),
        
        # JavaScript stack trace pattern
        # Example: at myFunction (C:\path\to\file.js:123:45)
        'javascript': re.compile(
            r'at\s+(?P<method>\w+)\s+\((?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+)\)',
            re.MULTILINE
        ),
        
        # Generic file path with line number
        # Example: C:\path\to\file.cs(123)
        'generic': re.compile(
            r'(?P<file>[A-Za-z]:[^\s:()]+\.(?:cs|py|java|js|ts|cpp|c|h|vb|php|rb|go))\(?:(?P<line>\d+)\)?',
            re.MULTILINE | re.IGNORECASE
        )
    }
    
    def __init__(self):
        pass
    
    def parse_stack_trace(self, stack_trace: str) -> Dict[str, Any]:
        """
        Parse stack trace and extract all useful information
        
        Args:
            stack_trace: Raw stack trace string
        
        Returns:
            Dictionary with parsed information:
            - frames: List of stack frames with file, line, method
            - exception_type: Type of exception
            - error_message: Error message
            - language: Detected language
        """
        if not stack_trace:
            return {
                'frames': [],
                'exception_type': None,
                'error_message': None,
                'language': None
            }
        
        # Try each pattern to find matches
        all_frames = []
        detected_language = None
        
        for lang, pattern in self.PATTERNS.items():
            matches = pattern.finditer(stack_trace)
            frames = []
            
            for match in matches:
                frame = {
                    'file_path': match.group('file') if 'file' in match.groupdict() else None,
                    'line_number': int(match.group('line')) if 'line' in match.groupdict() and match.group('line') else None,
                    'method_name': match.group('method') if 'method' in match.groupdict() else None,
                    'namespace': match.group('namespace') if 'namespace' in match.groupdict() else None,
                    'package': match.group('package') if 'package' in match.groupdict() else None,
                    'language': lang
                }
                frames.append(frame)
            
            if frames:
                all_frames.extend(frames)
                if not detected_language:
                    detected_language = lang
        
        # Extract exception type and message
        exception_info = self._extract_exception_info(stack_trace)
        
        # Deduplicate frames (same file+line may appear multiple times)
        unique_frames = self._deduplicate_frames(all_frames)
        
        result = {
            'frames': unique_frames,
            'exception_type': exception_info['exception_type'],
            'error_message': exception_info['error_message'],
            'language': detected_language,
            'total_frames': len(unique_frames)
        }
        
        logger.info(f"Parsed stack trace: {len(unique_frames)} frames, language: {detected_language}")
        
        return result
    
    def _extract_exception_info(self, stack_trace: str) -> Dict[str, str]:
        """Extract exception type and error message from stack trace"""
        exception_type = None
        error_message = None
        
        lines = stack_trace.split('\n')
        
        for line in lines[:5]:  # Check first 5 lines for exception info
            line = line.strip()
            
            # C# exception format: ExceptionType: Message
            if ': ' in line and 'Exception' in line:
                parts = line.split(': ', 1)
                if 'Exception' in parts[0]:
                    exception_type = parts[0].strip()
                    error_message = parts[1].strip() if len(parts) > 1 else None
                    break
            
            # Python exception format: ExceptionType: Message
            if line.endswith('Error') or line.endswith('Exception'):
                exception_type = line
                # Try to get message from next line
                idx = lines.index(line)
                if idx + 1 < len(lines):
                    next_line = lines[idx + 1].strip()
                    if next_line and not next_line.startswith('at ') and not next_line.startswith('File '):
                        error_message = next_line
                break
        
        return {
            'exception_type': exception_type,
            'error_message': error_message
        }
    
    def _deduplicate_frames(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate frames based on file path and line number"""
        seen = set()
        unique_frames = []
        
        for frame in frames:
            file_path = frame.get('file_path', '')
            line_number = frame.get('line_number', 0)
            
            # Create unique key
            key = f"{file_path}:{line_number}"
            
            if key not in seen:
                seen.add(key)
                unique_frames.append(frame)
        
        return unique_frames
    
    def extract_file_paths(self, stack_trace: str) -> List[str]:
        """
        Extract just the file paths from stack trace
        Useful for quick file retrieval
        """
        parsed = self.parse_stack_trace(stack_trace)
        
        file_paths = []
        for frame in parsed['frames']:
            if frame['file_path']:
                file_paths.append(frame['file_path'])
        
        return list(set(file_paths))  # Remove duplicates
    
    def get_primary_error_location(self, stack_trace: str) -> Optional[Dict[str, Any]]:
        """
        Get the primary error location (usually the first frame)
        This is where the exception actually occurred
        """
        parsed = self.parse_stack_trace(stack_trace)
        
        if parsed['frames']:
            return parsed['frames'][0]
        
        return None
    
    def format_for_code_retrieval(self, stack_trace: str) -> str:
        """
        Format stack trace information into a query suitable for code retrieval
        """
        parsed = self.parse_stack_trace(stack_trace)
        
        query_parts = []
        
        # Add exception type
        if parsed['exception_type']:
            query_parts.append(parsed['exception_type'])
        
        # Add error message
        if parsed['error_message']:
            query_parts.append(parsed['error_message'])
        
        # Add method names from top frames
        for frame in parsed['frames'][:3]:  # Top 3 frames
            if frame['method_name']:
                query_parts.append(frame['method_name'])
            if frame['namespace']:
                query_parts.append(frame['namespace'])
        
        return ' '.join(query_parts)


class CodeLocationExtractor:
    """
    Advanced extractor that combines stack trace parsing with code context
    """
    
    def __init__(self):
        self.parser = StackTraceParser()
    
    def extract_error_context(self, exception_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract comprehensive error context from exception data
        
        Args:
            exception_data: Dictionary with exception information
                - stack_trace: Stack trace string
                - exception_type: Exception type
                - message: Error message
                - inner_exception: Inner exception details
        
        Returns:
            Dictionary with error context:
            - primary_location: Main error location
            - related_locations: Other relevant locations in stack
            - search_query: Optimized query for code retrieval
            - error_signature: Unique signature for grouping
        """
        stack_trace = exception_data.get('stack_trace', '')
        
        # Parse stack trace
        parsed = self.parser.parse_stack_trace(stack_trace)
        
        # Get primary location
        primary_location = parsed['frames'][0] if parsed['frames'] else None
        
        # Get related locations (next 2-3 frames)
        related_locations = parsed['frames'][1:4] if len(parsed['frames']) > 1 else []
        
        # Create optimized search query
        search_query = self._create_search_query(exception_data, parsed)
        
        # Create error signature for grouping
        error_signature = self._create_error_signature(exception_data, primary_location)
        
        return {
            'primary_location': primary_location,
            'related_locations': related_locations,
            'search_query': search_query,
            'error_signature': error_signature,
            'language': parsed['language'],
            'total_frames': parsed['total_frames']
        }
    
    def _create_search_query(self, exception_data: Dict[str, Any], parsed: Dict[str, Any]) -> str:
        """Create optimized search query for code retrieval"""
        query_parts = []
        
        # Exception type (highest priority)
        exc_type = exception_data.get('exception_type', parsed.get('exception_type'))
        if exc_type:
            query_parts.append(exc_type)
        
        # Primary method/function
        if parsed['frames']:
            primary_frame = parsed['frames'][0]
            if primary_frame.get('method_name'):
                query_parts.append(primary_frame['method_name'])
            if primary_frame.get('namespace'):
                # Extract just the class name (last part of namespace)
                namespace = primary_frame['namespace']
                if '.' in namespace:
                    class_name = namespace.split('.')[-1]
                    query_parts.append(class_name)
        
        # Key terms from error message
        error_message = exception_data.get('message', parsed.get('error_message', ''))
        if error_message:
            # Extract key technical terms (avoid common words)
            technical_terms = self._extract_technical_terms(error_message)
            query_parts.extend(technical_terms[:3])  # Top 3 technical terms
        
        # Inner exception type
        inner_exc_type = exception_data.get('inner_exception_type')
        if inner_exc_type:
            query_parts.append(inner_exc_type)
        
        return ' '.join(query_parts)
    
    def _extract_technical_terms(self, text: str) -> List[str]:
        """Extract technical terms from error message"""
        # Common technical patterns
        patterns = [
            r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',  # PascalCase
            r'\b[a-z]+_[a-z_]+\b',  # snake_case
            r'\b[A-Z]{2,}\b',  # UPPERCASE acronyms
            r'\b\w+Exception\b',  # Exception names
            r'\b\w+Error\b',  # Error names
        ]
        
        terms = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            terms.extend(matches)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            if term.lower() not in seen and len(term) > 3:
                seen.add(term.lower())
                unique_terms.append(term)
        
        return unique_terms
    
    def _create_error_signature(self, exception_data: Dict[str, Any], 
                                primary_location: Optional[Dict[str, Any]]) -> str:
        """Create unique signature for error grouping"""
        import hashlib
        
        components = []
        
        # Exception type
        components.append(str(exception_data.get('exception_type', '')))
        
        # File path (if available)
        if primary_location and primary_location.get('file_path'):
            # Use just filename, not full path
            file_path = primary_location['file_path']
            filename = file_path.split('\\')[-1].split('/')[-1]
            components.append(filename)
        
        # Method name
        if primary_location and primary_location.get('method_name'):
            components.append(primary_location['method_name'])
        
        # Create hash
        signature = '|'.join(components)
        return hashlib.md5(signature.encode()).hexdigest()[:16]


if __name__ == "__main__":
    # Test the stack trace parser
    
    # C# stack trace example
    csharp_stack = """
    System.NullReferenceException: Object reference not set to an instance of an object.
       at ClaimGeneration.ProcessClaim(String claimId) in C:\Source\repos\code\ClaimGeneration\ClaimProcessor.cs:line 234
       at ClaimService.ValidateClaim(Claim claim) in C:\Source\repos\code\ClaimService\ClaimValidator.cs:line 89
       at ClaimHandler.Handle(ClaimRequest request) in C:\Source\repos\code\ClaimHandler\RequestHandler.cs:line 45
    """
    
    parser = StackTraceParser()
    result = parser.parse_stack_trace(csharp_stack)
    
    print("✅ Stack Trace Parser Test")
    print(f"\nException Type: {result['exception_type']}")
    print(f"Language: {result['language']}")
    print(f"Total Frames: {result['total_frames']}")
    print(f"\nFrames:")
    for i, frame in enumerate(result['frames'], 1):
        print(f"  {i}. {frame['file_path']}:{frame['line_number']} - {frame['method_name']}")
