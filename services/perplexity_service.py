"""
Perplexity AI Service
Wrapper for Perplexity AI API for research and content analysis
"""

import os
import aiohttp
import logging
from typing import Dict, List, Optional
import json

# Try to load environment variables if dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


class PerplexityService:
    """
    Service for interacting with Perplexity AI API
    Handles product research, audience identification, and content analysis
    """
    
    def __init__(self):
        self.api_key = os.environ.get('PERPLEXITY_API_KEY')
        self.base_url = 'https://api.perplexity.ai/chat/completions'
        
        if not self.api_key:
            logger.warning("PERPLEXITY_API_KEY not set. Perplexity features will be disabled.")
        else:
            logger.info(f"✅ Perplexity API key loaded (length: {len(self.api_key)})")
    
    async def query(self, messages: List[Dict], model: str = 'sonar') -> Optional[str]:
        """
        Make a query to Perplexity AI
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: 'sonar' - lightweight search model)
                   Options: 'sonar', 'sonar-pro', 'sonar-reasoning', 'sonar-reasoning-pro'
        
        Returns:
            Response text or None if error
        """
        
        if not self.api_key:
            logger.error("Perplexity API key not configured")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    headers={
                        'Authorization': f'Bearer {self.api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': model,
                        'messages': messages,
                        'temperature': 0.2,
                        'max_tokens': 2000
                        # Note: Perplexity doesn't support json_object format like OpenAI
                        # Instead, we ask for JSON in the prompt and parse it
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    else:
                        error_text = await response.text()
                        logger.error(f"Perplexity API error {response.status}: {error_text}")
                        return None
        
        except Exception as e:
            logger.error(f"Error calling Perplexity API: {e}")
            return None
    
    async def research_product(self, product_url: str, product_name: str = None) -> Dict:
        """
        Research product and identify target audience + content preferences
        Uses Perplexity to analyze the entire page and extract all product info
        
        Args:
            product_url: URL of the product
            product_name: Optional product name (if URL parsing fails)
        
        Returns:
            {
                'product': {
                    'name': str,
                    'price': float,
                    'description': str,
                    'url': str
                },
                'target_audience': {...},
                'content_preferences': {...}
            }
        """
        
        # Create a query that asks Perplexity to analyze the entire page and extract everything
        query = f"""Analyze this product/service page: {product_url}

Please visit the page and provide a comprehensive analysis as a JSON object with the following structure:
{{
  "product_info": {{
    "name": "Exact product/service name from the page",
    "description": "Detailed product/service description (2-3 sentences explaining what it does)",
    "price": 0.0,
    "price_text": "Price as shown on page (e.g., '$24.99/month', 'Free', 'Contact for pricing')",
    "pricing_model": "one-time/subscription/free/contact"
  }},
  "target_audience": {{
    "primary_buyers": ["specific description 1", "specific description 2", "specific description 3"],
    "description": "Detailed description of who uses this product/service"
  }},
  "demographics": {{
    "age_range": "age range (e.g., '25-55')",
    "income_level": "income level description",
    "geographic_location": ["location 1", "location 2"],
    "interests": ["interest 1", "interest 2"]
  }},
  "content_preferences": {{
    "content_types": ["specific faceless content type 1", "specific faceless content type 2", "specific faceless content type 3"],
    "topics": ["topic 1", "topic 2"]
  }},
  "pain_points": ["pain point 1", "pain point 2", "pain point 3"]
}}

IMPORTANT: 
- Extract the actual product name, description, and price from the page
- If price is subscription-based (e.g., $24.99/month), set price to 24.99 and pricing_model to "subscription"
- If price is annual (e.g., $299/year), convert to monthly (299/12 = 24.92) and set pricing_model to "subscription"
- Be specific about target audience - avoid generic terms like "buyers" or "customers"
- For content_types: Focus on FACELESS content types that this audience ACTUALLY watches on YouTube. Think about what they consume for entertainment - compilations, reactions, wins/losses, strategy content, big moments, etc. The goal is to discover what they actually watch, not what makes logical sense.
- Return ONLY valid JSON, no other text."""
        
        messages = [
            {
                'role': 'system',
                'content': '''You are an expert market research analyst specializing in YouTube content strategy and audience identification.

You MUST visit the provided URL and analyze the actual page content. Extract the real product name, description, and pricing from the page itself.

You MUST respond with valid JSON only, following the exact structure requested.

When analyzing products/services:
1. VISIT the URL and read the actual page content
2. Extract the EXACT product/service name from the page
3. Extract a DETAILED description (2-3 sentences) explaining what the product/service does
4. Extract the PRICE as shown on the page (including subscription pricing like $24.99/month)
5. Identify the SPECIFIC target audience based on what the page actually says
6. Determine relevant FACELESS content types that this audience ACTUALLY watches (not what they should watch)

CRITICAL for content_types:
- Focus on FACELESS content formats (no face cam, no talking head, no personal vlogs)
- Discover what this audience ACTUALLY watches - not what logically makes sense, but what they actually consume
- Think entertainment, compilations, reactions, wins/losses, big moments, strategy tips, highlights
- Let Perplexity research what this specific audience actually watches - don't assume based on the product type

Provide:
- Specific, detailed target audience descriptions (not generic terms like "buyers" or "customers")
- Relevant demographics based on the actual product/service
- FACELESS content types that the target audience actually watches for entertainment on YouTube
- Real insights about the audience's needs and interests

Be specific and contextual. For example:
- Medical billing service → "people with medical bills", "patients", "families dealing with healthcare costs"
- Tech product → "tech enthusiasts", "early adopters", "professionals in [specific field]"
- Financial service → "people seeking financial help", "small business owners", "individuals with debt"

Always base your analysis on what you ACTUALLY SEE on the page, not assumptions.
Return ONLY valid JSON, no explanatory text.'''
            },
            {
                'role': 'user',
                'content': query
            }
        ]
        
        response = await self.query(messages)
        
        if not response:
            return {
                'success': False,
                'error': 'Failed to get response from Perplexity'
            }
        
        # Parse JSON response - now includes product_info
        parsed = self._parse_json_response_with_product_info(response, product_url, product_name)
        
        return {
            'success': True,
            'product_url': product_url,
            'product_name': parsed.get('product_info', {}).get('name', product_name),
            'product_info': parsed.get('product_info', {}),
            'raw_response': response,
            'target_audience': parsed.get('audience', {}),
            'content_preferences': parsed.get('content_types', {}),
            'perplexity_queries': [query]
        }
    
    async def identify_audience(self, product_data: Dict) -> Dict:
        """
        Deep audience analysis from product data
        
        Args:
            product_data: Product information dict
        
        Returns:
            Audience profile with demographics and content preferences
        """
        
        product_name = product_data.get('name', 'this product')
        
        query = f"Provide detailed demographics for people who buy {product_name}. Include age range, gender, interests, geographic location, income level, and what specific FACELESS YouTube content types they actually watch. Research what this audience actually consumes - compilations, reactions, wins/losses, big moments, entertainment content."
        
        messages = [
            {
                'role': 'system',
                'content': '''You are a demographic analyst specializing in YouTube audience behavior. 

When listing content types:
- Focus on FACELESS content formats (no face cam, no personal presence)
- Research what this audience ACTUALLY watches - discover their real viewing habits
- Think compilations, reactions, wins/losses, big moments, entertainment content
- Don't assume based on product type - research what they actually consume

Provide structured, detailed audience profiles with realistic content consumption patterns based on research.'''
            },
            {
                'role': 'user',
                'content': query
            }
        ]
        
        response = await self.query(messages)
        
        if not response:
            return {'success': False, 'error': 'Failed to get response'}
        
        parsed = self._parse_demographics_response(response)
        
        return {
            'success': True,
            'primary_audience': parsed.get('demographics', {}),
            'content_types': parsed.get('content_types', []),
            'confidence': 0.85  # Default confidence
        }
    
    async def find_content_types(self, audience_description: str) -> List[str]:
        """
        Find what content types an audience watches
        
        Args:
            audience_description: Description of the target audience
        
        Returns:
            List of content types
        """
        
        query = f"What specific FACELESS YouTube content types do {audience_description} actually watch? Research what this audience actually consumes - think compilations, reactions, wins/losses, big moments, entertainment content. List the actual content formats they watch."
        
        messages = [
            {
                'role': 'system',
                'content': '''You are a content analyst specializing in faceless YouTube content. 

Focus on:
- FACELESS content formats (no face cam, no talking head, no personal presence)
- What this specific audience ACTUALLY watches - research their actual viewing habits
- Think about compilations, reactions, wins/losses, big moments, entertainment content
- Content that can be automated or scripted without personal presence

The goal is to discover what they actually consume, not what makes logical sense. Research real viewing patterns for this audience.'''
            },
            {
                'role': 'user',
                'content': query
            }
        ]
        
        response = await self.query(messages)
        
        if not response:
            return []
        
        # Extract content types from response
        content_types = self._extract_content_types(response)
        
        return content_types
    
    async def analyze_rpm_niches(self) -> Dict:
        """
        Research highest RPM YouTube niches for cash cow campaigns
        
        Returns:
            Recommended niches with RPM estimates
        """
        
        query = "What are the highest RPM YouTube niches in 2025? List top niches with estimated RPM ranges and content types that perform well."
        
        messages = [
            {
                'role': 'system',
                'content': 'You are a YouTube monetization expert. Provide specific niches with RPM data.'
            },
            {
                'role': 'user',
                'content': query
            }
        ]
        
        response = await self.query(messages)
        
        if not response:
            return {'success': False, 'error': 'Failed to get response'}
        
        parsed = self._parse_rpm_niches(response)
        
        return {
            'success': True,
            'recommended_niches': parsed.get('niches', []),
            'top_performers': parsed.get('top_content_types', [])
        }
    
    async def generate_channel_discovery_queries(self, research_data: Dict) -> List[Dict]:
        """
        Generate Channel Discovery search queries from research data
        
        Args:
            research_data: Product/audience research results
        
        Returns:
            List of query dicts for Channel Discovery:
            [
                {
                    'keywords': [str],
                    'niche_category': str,
                    'expected_rpm_range': {'min': float, 'max': float}
                }
            ]
        """
        
        # Extract content types and topics from research
        content_types = research_data.get('content_preferences', {}).get('content_types', [])
        topics = research_data.get('content_preferences', {}).get('topics', [])
        
        # Generate query for AI to understand Channel Discovery format
        query = f"""
        Based on these content types: {', '.join(content_types[:5])}
        And topics: {', '.join(topics[:5])}
        
        Generate YouTube Channel Discovery search queries that would find channels creating this content.
        Format as keywords that Channel Discovery can search for.
        Also suggest which high RPM niche category this fits (Finance, Marketing, Tech, etc.)
        """
        
        messages = [
            {
                'role': 'system',
                'content': """You understand YouTube Channel Discovery works with keyword searches.
                It has niche categories: Finance ($25-103 RPM), Marketing ($20-41 RPM), Crypto ($14-36 RPM), 
                Tech & AI ($20-45 RPM), Side Hustle ($15-44 RPM), etc.
                Generate search queries that would find relevant channels."""
            },
            {
                'role': 'user',
                'content': query
            }
        ]
        
        response = await self.query(messages)
        
        if not response:
            return []
        
        # Parse into Channel Discovery format
        queries = self._parse_channel_discovery_queries(response, content_types)
        
        return queries
    
    def _parse_audience_response(self, response: str) -> Dict:
        """Parse Perplexity response about audience and content (legacy method)"""
        # Try JSON first, fallback to text parsing
        try:
            return self._parse_json_response(response, None)
        except:
            return self._parse_audience_response_improved(response, None)
    
    def _parse_json_response_with_product_info(self, response: str, product_url: str, product_name: str = None) -> Dict:
        """Parse JSON response that includes product_info along with audience data"""
        import json
        
        try:
            # Try to extract JSON from response (might be wrapped in markdown code blocks)
            response_clean = response.strip()
            
            # Remove markdown code blocks if present
            if response_clean.startswith('```'):
                json_start = response_clean.find('{')
                json_end = response_clean.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    response_clean = response_clean[json_start:json_end]
            elif response_clean.startswith('{'):
                json_end = response_clean.rfind('}') + 1
                if json_end > 0:
                    response_clean = response_clean[:json_end]
            
            # Parse JSON
            data = json.loads(response_clean)
            
            # Extract product_info
            product_info = data.get('product_info', {})
            product_name_from_ai = product_info.get('name', product_name or 'Unknown Product')
            product_description = product_info.get('description', '')
            price_text = product_info.get('price_text', '')
            pricing_model = product_info.get('pricing_model', 'one-time')
            
            # Extract and convert price
            price = product_info.get('price', 0.0)
            if price == 0.0 and price_text:
                # Try to extract price from price_text
                import re
                price_match = re.search(r'[\$£€¥]?\s*([\d,]+\.?\d*)', price_text.replace(',', ''))
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        # If it's annual, convert to monthly
                        if 'year' in price_text.lower() or 'yr' in price_text.lower():
                            price = price / 12
                            pricing_model = 'subscription'
                        elif 'month' in price_text.lower() or 'mo' in price_text.lower():
                            pricing_model = 'subscription'
                    except ValueError:
                        pass
            
            # Format product info
            formatted_product_info = {
                'name': product_name_from_ai,
                'description': product_description or product_name_from_ai,
                'price': price if price > 0 else None,
                'price_formatted': f'${price:.2f}' if price > 0 else None,
                'price_text': price_text,
                'pricing_model': pricing_model,
                'url': product_url
            }
            
            # Extract audience and content (same as before)
            target_audience = data.get('target_audience', {})
            demographics = data.get('demographics', {})
            content_preferences = data.get('content_preferences', {})
            pain_points = data.get('pain_points', [])
            
            # Parse audience (use existing logic)
            parsed_audience = self._parse_audience_from_json(target_audience, content_preferences, product_name_from_ai)
            
            return {
                'product_info': formatted_product_info,
                'audience': parsed_audience.get('audience', {}),
                'content_types': parsed_audience.get('content_types', {})
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response with product info, falling back: {e}")
            # Fallback to basic parsing
            parsed = self._parse_json_response(response, product_name)
            return {
                'product_info': {
                    'name': product_name or 'Unknown Product',
                    'description': product_name or '',
                    'price': None,
                    'price_formatted': None,
                    'price_text': '',
                    'pricing_model': 'unknown',
                    'url': product_url
                },
                'audience': parsed.get('audience', {}),
                'content_types': parsed.get('content_types', {})
            }
        except Exception as e:
            logger.error(f"Error parsing JSON response with product info: {e}")
            # Fallback
            parsed = self._parse_json_response(response, product_name)
            return {
                'product_info': {
                    'name': product_name or 'Unknown Product',
                    'description': product_name or '',
                    'price': None,
                    'price_formatted': None,
                    'price_text': '',
                    'pricing_model': 'unknown',
                    'url': product_url
                },
                'audience': parsed.get('audience', {}),
                'content_types': parsed.get('content_types', {})
            }
    
    def _parse_audience_from_json(self, target_audience: Dict, content_preferences: Dict, product_name: str = None) -> Dict:
        """Helper to parse audience data from JSON structure"""
        # Extract structured data
        primary_buyers_raw = target_audience.get('primary_buyers', [])
        audience_description = target_audience.get('description', '')
        
        # Use existing parsing logic
        return self._parse_audience_data(primary_buyers_raw, audience_description, content_preferences, product_name)
    
    def _parse_audience_data(self, primary_buyers_raw: list, audience_description: str, content_preferences: Dict, product_name: str = None) -> Dict:
        """Parse audience data from raw arrays"""
        import re
        # Clean up primary_buyers (same logic as before)
        primary_buyers = []
        for buyer in primary_buyers_raw:
            if isinstance(buyer, str):
                buyer = buyer.strip().lstrip('-•*').strip()
                if len(buyer) > 70:
                    match = re.match(r'^([^,\.]{10,70})(?:[,\\.]|$)', buyer)
                    if match:
                        buyer = match.group(1).strip()
                    if len(buyer) > 60:
                        last_space_idx = buyer.rfind(' ', 15, 60)
                        if last_space_idx > 15:
                            buyer = buyer[:last_space_idx].strip()
                
                if buyer and len(buyer) > 5:
                    words = buyer.split()
                    if words:
                        last_word = words[-1].lower()
                        if len(last_word) <= 2 and last_word in ['de', 'or', 'an', 'in', 'on', 'at', 'to', 'of', 'is', 'as', 'it']:
                            buyer = ' '.join(words[:-1]).strip()
                    
                    buyer_lower = buyer.lower()
                    incomplete_endings = [' de', ' or', ' an', ' in', ' on', ' at', ' to', ' of', ' is', ' as', ' it']
                    for ending in incomplete_endings:
                        if buyer_lower.endswith(ending):
                            buyer = buyer[:-len(ending)].strip()
                            break
                    
                    if buyer and len(buyer) > 5:
                        words = buyer.split()
                        if words and len(words[-1]) <= 2:
                            buyer = ' '.join(words[:-1]).strip() if len(words) > 1 else buyer[:50]
                        if buyer and len(buyer) > 5:
                            primary_buyers.append(buyer)
        
        # Fallback if no buyers
        if not primary_buyers and product_name:
            product_lower = product_name.lower()
            if any(kw in product_lower for kw in ['medical', 'billing', 'health', 'healthcare']):
                primary_buyers = ['people with medical bills', 'patients', 'families dealing with healthcare costs']
            else:
                primary_buyers = ['target customers', 'people who need this product']
        
        # Clean content types
        content_types_raw = content_preferences.get('content_types', [])
        content_types = []
        seen = set()
        for ct in content_types_raw:
            if isinstance(ct, str):
                ct = ct.strip().lstrip('-•*').strip()
                ct = re.sub(r'\*\*([^*]+)\*\*', r'\1', ct)
                ct = re.sub(r'\*([^*]+)\*', r'\1', ct)
                if len(ct) > 55:
                    match = re.match(r'^([^,\.]{5,55})(?:[,\\.]|\s+(?:explaining|on|about|for|that|which|showing|featuring)|$)', ct, re.IGNORECASE)
                    if match:
                        ct = match.group(1).strip()
                    if len(ct) > 50:
                        last_space_idx = ct.rfind(' ', 0, 50)
                        if last_space_idx > 5:
                            ct = ct[:last_space_idx].strip()
                
                ct = ct.strip()
                if ct and len(ct) > 3:
                    words = ct.split()
                    if words:
                        last_word = words[-1].lower()
                        if len(last_word) <= 2 and last_word in ['de', 'or', 'an', 'in', 'on', 'at', 'to', 'of', 'is', 'as', 'it']:
                            ct = ' '.join(words[:-1]).strip()
                    
                    ct_lower = ct.lower()
                    if ct and len(ct) > 3 and ct_lower not in seen:
                        seen.add(ct_lower)
                        content_types.append(ct)
        
        return {
            'audience': {
                'primary_buyers': primary_buyers[:5] if primary_buyers else ['target customers'],
                'description': audience_description[:500] if audience_description else ''
            },
            'content_types': {
                'content_types': content_types[:10] if content_types else ['educational content'],
                'topics': content_preferences.get('topics', [])[:10]
            }
        }
    
    def _parse_json_response(self, response: str, product_name: str = None) -> Dict:
        """Parse JSON response from Perplexity - much more reliable than text parsing"""
        import json
        
        try:
            # Try to extract JSON from response (might be wrapped in markdown code blocks)
            response_clean = response.strip()
            
            # Remove markdown code blocks if present
            if response_clean.startswith('```'):
                # Find JSON block
                json_start = response_clean.find('{')
                json_end = response_clean.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    response_clean = response_clean[json_start:json_end]
            elif response_clean.startswith('{'):
                # Already JSON, just get the JSON part
                json_end = response_clean.rfind('}') + 1
                if json_end > 0:
                    response_clean = response_clean[:json_end]
            
            # Parse JSON
            data = json.loads(response_clean)
            
            # Extract structured data
            target_audience = data.get('target_audience', {})
            demographics = data.get('demographics', {})
            content_preferences = data.get('content_preferences', {})
            pain_points = data.get('pain_points', [])
            
            # Format for return
            primary_buyers_raw = target_audience.get('primary_buyers', [])
            audience_description = target_audience.get('description', '')
            
            # Clean up primary_buyers - extract concise descriptions from long strings (UNIVERSAL)
            import re
            primary_buyers = []
            for buyer in primary_buyers_raw:
                if isinstance(buyer, str):
                    # Remove leading dashes/bullets and clean up
                    buyer = buyer.strip().lstrip('-•*').strip()
                    
                    # Universal extraction strategy - works for any product type
                    if len(buyer) > 70:
                        # Strategy 1: Extract up to first comma or period (complete phrase)
                        match = re.match(r'^([^,\.]{10,70})(?:[,\\.]|$)', buyer)
                        if match:
                            buyer = match.group(1).strip()
                        
                        # Strategy 2: If still too long, find last complete word before 60 chars
                        if len(buyer) > 60:
                            # Find the last space before position 60 (but not too early)
                            last_space_idx = buyer.rfind(' ', 15, 60)  # Look between char 15-60
                            if last_space_idx > 15:
                                buyer = buyer[:last_space_idx].strip()
                            else:
                                # Try a wider range
                                last_space_idx = buyer.rfind(' ', 10, 60)
                                if last_space_idx > 10:
                                    buyer = buyer[:last_space_idx].strip()
                                else:
                                    # Last resort: find any space before 55
                                    last_space_idx = buyer.rfind(' ', 0, 55)
                                    if last_space_idx > 5:
                                        buyer = buyer[:last_space_idx].strip()
                                    else:
                                        # Really no good break point, take first 50 and we'll clean later
                                        buyer = buyer[:50].strip()
                        
                        # Final check: ensure we end at word boundary (not mid-word)
                        # Remove any trailing incomplete word fragments
                        if buyer:
                            # Find last complete word
                            words = buyer.split()
                            if words:
                                # Check if last word looks incomplete (very short or ends oddly)
                                last_word = words[-1]
                                if len(last_word) <= 2 or (len(last_word) <= 4 and not last_word[-1].isalnum()):
                                    # Remove last word if it looks incomplete
                                    buyer = ' '.join(words[:-1]).strip() if len(words) > 1 else buyer[:45].strip()
                                elif len(buyer) > 60:
                                    # Still too long, remove last word
                                    buyer = ' '.join(words[:-1]).strip() if len(words) > 1 else buyer[:55].strip()
                    
                    # Final cleanup - ensure it's meaningful and complete
                    if buyer and len(buyer) > 5:
                        buyer = buyer.strip()
                        
                        # Remove trailing incomplete words/fragments (universal cleanup)
                        # Check for incomplete words at the end (2-3 letter fragments)
                        words = buyer.split()
                        if words:
                            last_word = words[-1].lower()
                            # Remove if last word is a fragment (very short and common)
                            if len(last_word) <= 2 and last_word in ['de', 'or', 'an', 'in', 'on', 'at', 'to', 'of', 'is', 'as', 'it']:
                                buyer = ' '.join(words[:-1]).strip()
                            
                            # Also check if last word is incomplete (ends with common incomplete patterns)
                            if last_word and len(last_word) <= 3 and not last_word.endswith(('ed', 'ing', 'ly', 'er', 'al')):
                                # Might be incomplete, but only remove if it's clearly a fragment
                                if last_word in ['de', 'or', 'an', 'in', 'on', 'at', 'to', 'of', 'is', 'as', 'it', 'we', 'he', 'be', 'do', 'go', 'up', 'no', 'so']:
                                    buyer = ' '.join(words[:-1]).strip()
                        
                        # Final validation - ensure it's a complete, meaningful phrase
                        # Check for any trailing incomplete fragments (more comprehensive)
                        buyer_lower = buyer.lower()
                        incomplete_endings = [' de', ' or', ' an', ' in', ' on', ' at', ' to', ' of', ' is', ' as', ' it', ' we', ' he', ' be', ' do', ' go', ' up', ' no', ' so', ' de', ' or', ' an']
                        
                        # Remove trailing incomplete words
                        for ending in incomplete_endings:
                            if buyer_lower.endswith(ending):
                                buyer = buyer[:-len(ending)].strip()
                                break
                        
                        # Final check - ensure we have a complete, meaningful phrase
                        if buyer and len(buyer) > 5:
                            # Make sure it doesn't end with a single letter or fragment
                            words = buyer.split()
                            if words and len(words[-1]) <= 2:
                                buyer = ' '.join(words[:-1]).strip()
                            
                            if buyer and len(buyer) > 5:
                                primary_buyers.append(buyer)
            
            # If no primary buyers, try to infer from description
            if not primary_buyers and audience_description:
                # Extract key phrases from description
                import re
                patterns = [
                    r'(?:people|individuals|users|patients|customers)\s+(?:with|who|that|seeking|dealing|facing)',
                    r'(?:seniors|adults|families|homeowners|business owners|professionals)',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, audience_description.lower())
                    if matches:
                        primary_buyers.extend(matches[:3])
            
            # Fallback to product-based inference if still empty (UNIVERSAL - works for any product)
            if not primary_buyers and product_name:
                product_lower = product_name.lower()
                # Universal keyword-based inference - covers most product categories
                if any(kw in product_lower for kw in ['medical', 'billing', 'health', 'healthcare', 'patient', 'hospital']):
                    primary_buyers = ['people with medical bills', 'patients', 'families dealing with healthcare costs']
                elif any(kw in product_lower for kw in ['financial', 'money', 'save', 'debt', 'credit', 'loan', 'investment']):
                    primary_buyers = ['people seeking financial help', 'individuals looking to save money', 'people managing finances']
                elif any(kw in product_lower for kw in ['tech', 'software', 'app', 'digital', 'online', 'saas']):
                    primary_buyers = ['tech enthusiasts', 'professionals', 'early adopters', 'business owners']
                elif any(kw in product_lower for kw in ['education', 'learn', 'course', 'training', 'school']):
                    primary_buyers = ['students', 'learners', 'professionals seeking skills', 'people looking to learn']
                elif any(kw in product_lower for kw in ['fitness', 'workout', 'exercise', 'gym']):
                    primary_buyers = ['fitness enthusiasts', 'people looking to get in shape', 'health-conscious individuals']
                elif any(kw in product_lower for kw in ['business', 'entrepreneur', 'startup', 'company']):
                    primary_buyers = ['business owners', 'entrepreneurs', 'small business operators']
                else:
                    # Generic fallback - extract from product name itself
                    # Try to identify the problem/solution the product addresses
                    if any(kw in product_lower for kw in ['error', 'fix', 'solve', 'help', 'save']):
                        primary_buyers = ['people facing this problem', 'individuals who need this solution', 'customers seeking help']
                    else:
                        primary_buyers = ['target customers', 'people who need this product', 'potential users']
            
            content_types_raw = content_preferences.get('content_types', [])
            topics = content_preferences.get('topics', [])
            
            # Clean up content_types - remove duplicates and truncate long strings (UNIVERSAL)
            content_types = []
            seen = set()
            for ct in content_types_raw:
                if isinstance(ct, str):
                    # Remove markdown formatting and clean up
                    ct = ct.strip().lstrip('-•*').strip()
                    # Remove markdown bold/italic
                    ct = re.sub(r'\*\*([^*]+)\*\*', r'\1', ct)  # Remove **bold**
                    ct = re.sub(r'\*([^*]+)\*', r'\1', ct)  # Remove *italic*
                    
                    # Universal extraction - works for any content type
                    if len(ct) > 55:
                        # Strategy 1: Extract up to first comma, period, or explanation word
                        match = re.match(r'^([^,\.]{5,55})(?:[,\\.]|\s+(?:explaining|on|about|for|that|which|showing|featuring)|$)', ct, re.IGNORECASE)
                        if match:
                            ct = match.group(1).strip()
                        
                        # Strategy 2: If still too long, find last complete word before 50 chars
                        if len(ct) > 50:
                            last_space_idx = ct.rfind(' ', 0, 50)
                            if last_space_idx > 5:
                                ct = ct[:last_space_idx].strip()
                            else:
                                ct = ct[:45].strip()
                        
                        # Final check: ensure word boundary
                        if ct and ct[-1] not in '.,!?; ':
                            ct = ct.rsplit(' ', 1)[0] if ' ' in ct and len(ct) > 15 else ct[:40]
                    
                    # Remove trailing fragments and ensure meaningful (UNIVERSAL)
                    ct = ct.strip()
                    if ct and len(ct) > 3:
                        # Remove trailing incomplete words/fragments
                        words = ct.split()
                        if words:
                            last_word = words[-1].lower()
                            # Remove if last word is a fragment
                            if len(last_word) <= 2 and last_word in ['de', 'or', 'an', 'in', 'on', 'at', 'to', 'of', 'is', 'as', 'it', 'we', 'he', 'be', 'do', 'go', 'up', 'no', 'so']:
                                ct = ' '.join(words[:-1]).strip()
                            # Also check for incomplete endings
                            ct_lower = ct.lower()
                            incomplete_endings = [' de', ' or', ' and', ' the', ' a', ' an', ' in', ' on', ' at', ' to', ' of', ' is', ' as', ' it']
                            for ending in incomplete_endings:
                                if ct_lower.endswith(ending):
                                    ct = ct[:-len(ending)].strip()
                                    break
                        
                        # Final validation - ensure complete phrase
                        if ct and len(ct) > 3:
                            words = ct.split()
                            if words and len(words[-1]) <= 2:
                                ct = ' '.join(words[:-1]).strip()
                            
                            # Add if not duplicate (case-insensitive) and meaningful
                            if ct and len(ct) > 3:
                                ct_lower = ct.lower()
                                if ct_lower not in seen:
                                    seen.add(ct_lower)
                                    content_types.append(ct)
            
            # Fallback content types if empty (UNIVERSAL - works for any product)
            if not content_types and product_name:
                product_lower = product_name.lower()
                # Universal content type inference based on product category
                if any(kw in product_lower for kw in ['medical', 'billing', 'health', 'healthcare']):
                    content_types = ['healthcare cost guides', 'how-to review medical bills', 'financial education', 'insurance explainers']
                elif any(kw in product_lower for kw in ['financial', 'money', 'save', 'debt', 'credit']):
                    content_types = ['financial education', 'money-saving tips', 'how-to guides', 'financial advice']
                elif any(kw in product_lower for kw in ['tech', 'software', 'app', 'digital']):
                    content_types = ['tech reviews', 'product tutorials', 'how-to guides', 'software demos']
                elif any(kw in product_lower for kw in ['education', 'learn', 'course', 'training']):
                    content_types = ['educational content', 'tutorials', 'learning guides', 'skill-building videos']
                elif any(kw in product_lower for kw in ['fitness', 'workout', 'exercise', 'gym']):
                    content_types = ['fitness tutorials', 'workout guides', 'health tips', 'exercise routines']
                elif any(kw in product_lower for kw in ['business', 'entrepreneur', 'startup']):
                    content_types = ['business advice', 'entrepreneurship guides', 'startup tips', 'business strategies']
                elif any(kw in product_lower for kw in ['error', 'fix', 'solve', 'help']):
                    content_types = ['how-to guides', 'problem-solving tutorials', 'educational content', 'solution explainers']
                else:
                    # Generic fallback for any product
                    content_types = ['educational content', 'how-to tutorials', 'product guides', 'informational videos']
            
            return {
                'audience': {
                    'primary_buyers': primary_buyers[:5] if primary_buyers else ['target customers'],
                    'description': audience_description[:500] if audience_description else ''
                },
                'content_types': {
                    'content_types': content_types[:10] if content_types else ['educational content'],
                    'topics': topics[:10] if topics else []
                }
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response, falling back to text parsing: {e}")
            # Fallback to text parsing if JSON fails
            return self._parse_audience_response_improved(response, product_name)
        except Exception as e:
            logger.error(f"Error parsing JSON response: {e}")
            # Fallback to text parsing
            return self._parse_audience_response_improved(response, product_name)
    
    def _parse_audience_response_improved(self, response: str, product_name: str = None) -> Dict:
        """Improved parsing that extracts actual audience and content from Perplexity response"""
        
        response_lower = response.lower()
        lines = response.split('\n')
        
        # Extract target audience section
        primary_buyers = []
        audience_description = ""
        
        # Look for "Target Audience" or "Audience" section
        in_audience_section = False
        audience_keywords_found = []
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Detect audience section
            if any(keyword in line_lower for keyword in ['target audience', 'audience:', 'who would', 'primary users', 'demographics']):
                in_audience_section = True
                continue
            
            # Extract audience descriptions from the section
            if in_audience_section:
                # Look for specific audience types (not generic)
                # Skip generic terms like "buyers", "customers", "enthusiasts" unless they're qualified
                if len(line.strip()) > 10:  # Non-empty line
                    # Extract phrases that describe the audience
                    # Look for patterns like "people with...", "individuals who...", "those who..."
                    import re
                    patterns = [
                        r'(?:people|individuals|users|patients|customers|consumers|viewers|those)\s+(?:with|who|that|seeking|dealing|facing|interested|looking)',
                        r'(?:seniors|adults|families|homeowners|business owners|professionals|students)',
                        r'(?:people|individuals)\s+in\s+[^,\.]+',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, line_lower, re.IGNORECASE)
                        if matches:
                            # Extract the full phrase
                            for match in matches:
                                idx = line_lower.find(match)
                                if idx >= 0:
                                    # Get context around match (up to 100 chars)
                                    start = max(0, idx - 20)
                                    end = min(len(line), idx + len(match) + 80)
                                    phrase = line[start:end].strip()
                                    if phrase and phrase not in audience_keywords_found:
                                        audience_keywords_found.append(phrase)
                    
                    # If line contains audience description, add it
                    if any(word in line_lower for word in ['people', 'individuals', 'users', 'customers', 'patients', 'seniors', 'families']):
                        if 'target audience' not in line_lower and 'audience:' not in line_lower:
                            audience_description += line.strip() + " "
            
            # Stop at next major section
            if in_audience_section and any(keyword in line_lower for keyword in ['content', 'demographics', 'pain points', '2.', '3.', '4.']):
                if i > 0:  # Don't break on first line
                    break
        
        # Extract content types section
        content_types = []
        in_content_section = False
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Detect content section
            if any(keyword in line_lower for keyword in ['content', 'youtube', 'video types', 'content types', 'content preferences']):
                in_content_section = True
                continue
            
            # Extract content types
            if in_content_section:
                # Look for specific content type mentions
                content_patterns = [
                    r'(?:how[-\s]?to|tutorial|guide|review|explainer|news|commentary|educational|documentary)',
                    r'(?:video|content|channel|series)\s+(?:about|on|for)',
                ]
                
                import re
                for pattern in content_patterns:
                    matches = re.findall(pattern, line_lower, re.IGNORECASE)
                    if matches:
                        # Extract the content type phrase
                        for match in matches:
                            idx = line_lower.find(match)
                            if idx >= 0:
                                # Get surrounding context
                                start = max(0, idx - 30)
                                end = min(len(line), idx + len(match) + 50)
                                phrase = line[start:end].strip()
                                # Clean up and capitalize
                                phrase = phrase.strip('.,;:').strip()
                                if phrase and len(phrase) > 5 and phrase not in content_types:
                                    content_types.append(phrase)
            
            # Stop at next major section or after getting enough content types
            if in_content_section and (any(keyword in line_lower for keyword in ['pain points', 'demographics', '4.', '5.']) or len(content_types) >= 5):
                break
        
        # If we didn't find specific audience, try to extract from the full response
        if not audience_keywords_found:
            # Look for any descriptive phrases about who uses the product
            sentences = response.split('.')
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(word in sentence_lower for word in ['people', 'individuals', 'users', 'customers', 'patients']):
                    if any(word in sentence_lower for word in ['with', 'who', 'that', 'seeking', 'dealing']):
                        # Extract the key phrase
                        import re
                        match = re.search(r'([^\.]+(?:people|individuals|users|customers|patients)[^\.]+)', sentence, re.IGNORECASE)
                        if match:
                            phrase = match.group(1).strip()
                            if len(phrase) > 15 and phrase not in audience_keywords_found:
                                audience_keywords_found.append(phrase[:100])  # Limit length
        
        # If still no good audience, use product name to infer
        if not audience_keywords_found and product_name:
            product_lower = product_name.lower()
            # Infer audience based on product keywords
            if 'medical' in product_lower or 'billing' in product_lower or 'health' in product_lower:
                audience_keywords_found = ['people with medical bills', 'patients', 'families dealing with healthcare costs']
            elif 'financial' in product_lower or 'money' in product_lower or 'save' in product_lower:
                audience_keywords_found = ['people seeking financial help', 'individuals looking to save money']
            elif 'tech' in product_lower or 'software' in product_lower:
                audience_keywords_found = ['tech enthusiasts', 'professionals', 'early adopters']
        
        # Fallback to generic if nothing found (but better than before)
        if not audience_keywords_found:
            audience_keywords_found = ['target customers']
        
        # Clean up content types - remove duplicates and generic ones
        content_types = [ct for ct in content_types if len(ct) > 5]
        content_types = list(dict.fromkeys(content_types))  # Remove duplicates while preserving order
        
        # If no content types found, infer from product
        if not content_types:
            if product_name:
                product_lower = product_name.lower()
                if 'medical' in product_lower or 'billing' in product_lower:
                    content_types = ['healthcare cost guides', 'how-to review medical bills', 'financial education', 'insurance explainers']
                elif 'financial' in product_lower or 'money' in product_lower:
                    content_types = ['financial education', 'money-saving tips', 'how-to guides']
                else:
                    content_types = ['educational content', 'how-to tutorials', 'product guides']
            else:
                content_types = ['educational content', 'tutorials']
        
        return {
            'audience': {
                'primary_buyers': audience_keywords_found[:5],
                'description': audience_description[:500] if audience_description else response[:500]
            },
            'content_types': {
                'content_types': content_types[:10],
                'topics': []  # Can be extracted separately if needed
            }
        }
    
    def _parse_demographics_response(self, response: str) -> Dict:
        """Parse demographics from Perplexity response"""
        
        demographics = {
            'age_range': '25-55',  # Default
            'gender': 'mixed',
            'interests': [],
            'geo': ['US', 'UK', 'CA'],
            'income_level': 'middle_to_high'
        }
        
        response_lower = response.lower()
        
        # Extract age range
        import re
        age_match = re.search(r'(\d+)[-\s]+(\d+)', response)
        if age_match:
            demographics['age_range'] = f"{age_match.group(1)}-{age_match.group(2)}"
        
        # Extract interests
        interest_keywords = ['tech', 'finance', 'collectibles', 'antiques', 'design', 'investment']
        for keyword in interest_keywords:
            if keyword in response_lower:
                demographics['interests'].append(keyword)
        
        return {
            'demographics': demographics,
            'content_types': self._extract_content_types(response)
        }
    
    def _extract_content_types(self, response: str) -> List[str]:
        """Extract content types from response text - extracts whatever content types are mentioned"""
        
        import re
        content_types = []
        
        # Try to extract from numbered/bulleted lists first
        list_patterns = [
            r'(?:^|\n)\s*(?:\d+\.|\-|\*|\•)\s*([^\n]{5,80})',  # Numbered or bulleted lists
            r'content types?[:\s]+([^\n]+)',  # "Content types: ..."
            r'types?[:\s]+([^\n]+)',  # "Types: ..."
        ]
        
        for pattern in list_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                # Split by comma, semicolon, or newline
                items = re.split(r'[,;]\s*|\n', match.strip())
                for item in items:
                    item = item.strip().lstrip('-•*').strip()
                    # Remove markdown formatting
                    item = re.sub(r'\*\*([^*]+)\*\*', r'\1', item)
                    item = re.sub(r'\*([^*]+)\*', r'\1', item)
                    # Clean up
                    if len(item) > 3 and len(item) < 80:
                        content_types.append(item)
        
        # If no list found, try to extract from sentences mentioning "content"
        if not content_types:
            # Look for patterns like "content types include X, Y, Z" or "they watch X, Y, Z"
            sentence_patterns = [
                r'(?:content types?|videos?|content|formats?|types?)\s+(?:include|are|include:|are:)\s+([^\.]+)',
                r'(?:watch|consume|enjoy|view)\s+([^\.]+)',
            ]
            
            for pattern in sentence_patterns:
                matches = re.findall(pattern, response, re.IGNORECASE)
                for match in matches:
                    items = re.split(r'[,;]\s+and\s+|\s+and\s+|,\s*', match.strip())
                    for item in items:
                        item = item.strip().lstrip('-•*').strip()
                        item = re.sub(r'\*\*([^*]+)\*\*', r'\1', item)
                        item = re.sub(r'\*([^*]+)\*', r'\1', item)
                        if len(item) > 3 and len(item) < 80:
                            content_types.append(item)
        
        # Remove duplicates (case-insensitive) and return
        seen = set()
        unique_types = []
        for ct in content_types:
            ct_lower = ct.lower()
            if ct_lower not in seen and len(ct) > 3:
                seen.add(ct_lower)
                unique_types.append(ct)
        
        return unique_types[:10]
    
    def _parse_rpm_niches(self, response: str) -> Dict:
        """Parse RPM niche data from response"""
        
        niches = []
        
        # Known high RPM niches (use as fallback)
        known_niches = {
            'Finance': {'rpm': 25, 'content_types': ['stock analysis', 'market news', 'investment advice']},
            'Marketing': {'rpm': 20, 'content_types': ['business strategies', 'growth tips', 'case studies']},
            'Crypto': {'rpm': 14, 'content_types': ['crypto news', 'blockchain', 'trading']},
            'Tech & AI': {'rpm': 20, 'content_types': ['tech reviews', 'AI news', 'productivity']},
            'Side Hustle': {'rpm': 15, 'content_types': ['online income', 'passive income', 'business ideas']}
        }
        
        response_lower = response.lower()
        
        # Try to extract from response
        for niche_name, niche_data in known_niches.items():
            if niche_name.lower() in response_lower or any(ct in response_lower for ct in niche_data['content_types']):
                niches.append({
                    'niche': niche_name.lower(),
                    'estimated_rpm': niche_data['rpm'],
                    'content_types': niche_data['content_types'],
                    'discovery_keywords': [f'{niche_name.lower()} channels', f'{niche_name.lower()} content']
                })
        
        # If no niches found, return defaults
        if not niches:
            niches = [
                {
                    'niche': name.lower(),
                    'estimated_rpm': data['rpm'],
                    'content_types': data['content_types'],
                    'discovery_keywords': [f'{name.lower()} channels']
                }
                for name, data in known_niches.items()
            ]
        
        return {
            'niches': niches[:5],
            'top_content_types': ['educational', 'news', 'analysis', 'tutorials']
        }
    
    def _parse_channel_discovery_queries(self, response: str, content_types: List[str]) -> List[Dict]:
        """Parse Channel Discovery queries from AI response"""
        
        queries = []
        
        # Map content types to niche categories
        niche_mapping = {
            'finance': {'keywords': ['finance', 'stock market', 'investing'], 'rpm': {'min': 25, 'max': 103}},
            'marketing': {'keywords': ['marketing', 'business growth', 'entrepreneurship'], 'rpm': {'min': 20, 'max': 41}},
            'tech': {'keywords': ['tech', 'ai', 'technology'], 'rpm': {'min': 20, 'max': 45}},
            'crypto': {'keywords': ['crypto', 'blockchain', 'bitcoin'], 'rpm': {'min': 14, 'max': 36}}
        }
        
        # Generate queries from content types
        for content_type in content_types[:5]:
            # Determine niche category
            niche_category = 'tech'  # Default
            for niche, data in niche_mapping.items():
                if any(kw in content_type.lower() for kw in data['keywords']):
                    niche_category = niche
                    break
            
            queries.append({
                'keywords': [content_type, f'{content_type} channels', f'{content_type} videos'],
                'niche_category': niche_category.title(),
                'expected_rpm_range': niche_mapping.get(niche_category, {'min': 10, 'max': 30})['rpm']
            })
        
        return queries[:5]  # Limit to 5 queries


# Singleton
perplexity_service = PerplexityService()

