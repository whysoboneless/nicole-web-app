"""
Product Research Service
Researches products using Perplexity AI and web scraping
Extracts product info, identifies target audience, and recommends content strategies
"""

import aiohttp
import logging
from typing import Dict, Optional
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse

# Use relative import for same-package imports
try:
    from .perplexity_service import perplexity_service
except ImportError:
    # Fallback for absolute import
    try:
        from services.perplexity_service import perplexity_service
    except ImportError:
        # Final fallback for different package structure
        from nicole_web_suite_template.services.perplexity_service import perplexity_service

logger = logging.getLogger(__name__)


class ProductResearchService:
    """
    Service for researching products and identifying target audiences
    """
    
    def __init__(self):
        self.perplexity = perplexity_service
    
    async def research_product(self, product_url: str) -> Dict:
        """
        Research product from URL
        
        Args:
            product_url: URL of the product page
        
        Returns:
            {
                'product': {...},
                'target_audience': {...},
                'content_preferences': {...},
                'recommended_strategy': {...}
            }
        """
        
        try:
            logger.info(f"🔍 Researching product with Perplexity: {product_url}")
            
            # Use Perplexity to analyze the entire page and extract everything
            # Perplexity will visit the page and extract: product name, description, price, target audience, content types
            perplexity_research = await self.perplexity.research_product(product_url)
            
            if not perplexity_research.get('success'):
                logger.warning("Perplexity research failed, using fallback data")
                return {
                    'success': False,
                    'error': perplexity_research.get('error', 'Failed to research product')
                }
            
            # Extract product info from Perplexity response
            product_info = perplexity_research.get('product_info', {})
            product_data = {
                'name': product_info.get('name', 'Unknown Product'),
                'description': product_info.get('description', ''),
                'price': product_info.get('price'),
                'price_formatted': product_info.get('price_formatted'),
                'price_text': product_info.get('price_text', ''),
                'pricing_model': product_info.get('pricing_model', 'unknown'),
                'image_url': product_info.get('image_url', ''),  # Product image
                'url': product_url
            }
            
            # If no image from Perplexity, try scraping
            if not product_data.get('image_url'):
                scrape_data = await self._scrape_product_page(product_url)
                if scrape_data.get('image_url'):
                    product_data['image_url'] = scrape_data['image_url']
                    logger.info(f"Got product image from scraping: {product_data['image_url'][:100]}...")
            
            logger.info(f"✅ Perplexity extracted: name='{product_data.get('name')}', price={product_data.get('price')}, description length={len(product_data.get('description', ''))}")
            
            # Step 3: Identify content strategy
            recommended_strategy = await self._generate_content_strategy(
                product_data,
                perplexity_research
            )
            
            return {
                'success': True,
                'product': product_data,
                'target_audience': perplexity_research.get('target_audience', {}),
                'content_preferences': perplexity_research.get('content_preferences', {}),
                'recommended_strategy': recommended_strategy,
                'research_date': None  # Will be set by caller
            }
            
        except Exception as e:
            logger.error(f"Error researching product: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _scrape_product_page(self, url: str) -> Dict:
        """Scrape basic product info from URL"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Extract product name (common patterns)
                        name = None
                        for selector in ['h1', '.product-title', '.product-name', '[itemprop="name"]', 'title']:
                            element = soup.select_one(selector)
                            if element:
                                name = element.get_text().strip()
                                break
                        
                        if not name:
                            name = soup.find('title')
                            if name:
                                name = name.get_text().strip()
                        
                        # Extract description (enhanced with more selectors)
                        description = None
                        # Try meta description first
                        meta_desc = soup.find('meta', {'name': 'description'}) or \
                                   soup.find('meta', {'property': 'og:description'})
                        if meta_desc:
                            description = meta_desc.get('content', '').strip()
                        
                        # If no meta description, try other selectors
                        if not description or len(description) < 20:
                            desc_selectors = [
                                '.product-description', '[itemprop="description"]',
                                '.description', '.product-details', '.product-info',
                                '.summary', '.intro', '.overview',
                                '#description', '#product-description',
                                '.hero-description', '.lead-text', '.value-prop',
                                '[class*="description"]', '[class*="intro"]',
                                'main p', '.content p', 'section p'
                            ]
                            for selector in desc_selectors:
                                try:
                                    element = soup.select_one(selector)
                                    if element:
                                        desc_text = element.get_text().strip()
                                        # Clean up whitespace
                                        desc_text = ' '.join(desc_text.split())
                                        if len(desc_text) > 20:  # Only use if meaningful
                                            description = desc_text[:500]  # Limit length
                                            break
                                except:
                                    continue
                        
                        # If still no description, try to get first meaningful paragraph
                        if not description or len(description) < 20:
                            # Try to find paragraphs in main content areas
                            main_content = soup.find('main') or soup.find('article') or soup.find('body')
                            if main_content:
                                paragraphs = main_content.find_all('p')
                                for p in paragraphs:
                                    desc_text = p.get_text().strip()
                                    desc_text = ' '.join(desc_text.split())
                                    # Skip very short paragraphs or navigation text
                                    if len(desc_text) > 50 and len(desc_text) < 1000:
                                        # Check if it looks like a product description (not navigation)
                                        if not any(skip in desc_text.lower() for skip in ['cookie', 'privacy', 'terms', 'menu', 'navigation']):
                                            description = desc_text[:500]
                                            break
                        
                        # Extract price (enhanced with more selectors and subscription pricing)
                        price = None
                        price_text = None
                        # Try multiple selectors for price
                        price_selectors = [
                            '.price', '[itemprop="price"]', '.product-price', 
                            '.price-current', '.current-price', '.sale-price',
                            '[data-price]', '.cost', '.amount', '.pricing',
                            '#price', '#product-price', '.product-cost',
                            '.subscription-price', '.monthly-price', '.plan-price',
                            '[class*="price"]', '[class*="cost"]', '[id*="price"]'
                        ]
                        for selector in price_selectors:
                            try:
                                element = soup.select_one(selector)
                                if element:
                                    price_text = element.get_text().strip()
                                    # Enhanced regex to handle subscription pricing: $24.99/month, $99/year, etc.
                                    # Look for patterns like $99.99, $99.99/month, $99.99/year, etc.
                                    price_match = re.search(r'[\$£€¥]?\s*([\d,]+\.?\d*)\s*(?:/month|/mo|/year|/yr|/week|/wk|/day)?', price_text.replace(',', ''), re.IGNORECASE)
                                    if price_match:
                                        try:
                                            price = float(price_match.group(1))
                                            # If it's annual pricing, convert to monthly for comparison
                                            if '/year' in price_text.lower() or '/yr' in price_text.lower():
                                                price = price / 12
                                            elif '/week' in price_text.lower() or '/wk' in price_text.lower():
                                                price = price * 4.33  # Approximate monthly
                                            elif '/day' in price_text.lower():
                                                price = price * 30  # Approximate monthly
                                            break
                                        except ValueError:
                                            continue
                            except:
                                continue
                        
                        # If still no price, search all text for price patterns
                        if not price:
                            # Search for common price patterns in the entire page
                            page_text = soup.get_text()
                            # Look for $XX.XX/month or $XX.XX/month patterns
                            price_patterns = [
                                r'\$(\d+\.?\d*)\s*/month',
                                r'\$(\d+\.?\d*)\s*/mo',
                                r'\$(\d+\.?\d*)\s*/year',
                                r'\$(\d+\.?\d*)\s*/yr',
                                r'(\d+\.?\d*)\s*dollars?\s*/month',
                                r'(\d+\.?\d*)\s*USD\s*/month'
                            ]
                            for pattern in price_patterns:
                                match = re.search(pattern, page_text, re.IGNORECASE)
                                if match:
                                    try:
                                        price = float(match.group(1))
                                        if '/year' in match.group(0).lower() or '/yr' in match.group(0).lower():
                                            price = price / 12
                                        break
                                    except ValueError:
                                        continue
                        
                        # If still no price, try to find price in meta tags
                        if not price:
                            price_meta = soup.find('meta', {'property': 'product:price:amount'}) or \
                                         soup.find('meta', {'name': 'price'})
                            if price_meta:
                                price_text = price_meta.get('content', '')
                                price_match = re.search(r'([\d,]+\.?\d*)', price_text.replace(',', ''))
                                if price_match:
                                    try:
                                        price = float(price_match.group(1))
                                    except ValueError:
                                        pass
                        
                        # Extract product image
                        image_url = None
                        # Try multiple selectors for product images
                        image_selectors = [
                            'meta[property="og:image"]',
                            'meta[name="twitter:image"]',
                            'img[itemprop="image"]',
                            '.product-image img',
                            '.product-photo img',
                            'img[class*="product"]',
                            'img[class*="hero"]',
                            'img[alt*="product"]',
                            'main img',
                            'article img'
                        ]
                        
                        for selector in image_selectors:
                            try:
                                element = soup.select_one(selector)
                                if element:
                                    if element.name == 'meta':
                                        image_url = element.get('content', '')
                                    else:
                                        image_url = element.get('src', '') or element.get('data-src', '')
                                    
                                    # Convert relative URLs to absolute
                                    if image_url and not image_url.startswith('http'):
                                        from urllib.parse import urljoin
                                        image_url = urljoin(url, image_url)
                                    
                                    if image_url and len(image_url) > 10:
                                        logger.info(f"Found product image: {image_url[:100]}...")
                                        break
                            except:
                                continue
                        
                        # Extract category from URL or page
                        category = None
                        url_parts = urlparse(url)
                        path_parts = url_parts.path.split('/')
                        if len(path_parts) > 1:
                            category = path_parts[1].replace('-', ' ').title()
                        
                        # If no description found, use product name as description (for services)
                        if not description or len(description) < 20:
                            if name and name != 'Unknown Product':
                                description = name  # Use product name as description fallback
                        
                        return {
                            'name': name or 'Unknown Product',
                            'description': description or '',
                            'price': price,
                            'price_formatted': f'${price:.2f}' if price else None,
                            'image_url': image_url or '',  # Add extracted image URL
                            'category': category,
                            'url': url
                        }
                    else:
                        logger.warning(f"Failed to scrape {url}: HTTP {response.status}")
                        return {
                            'name': 'Unknown Product',
                            'description': '',
                            'price': None,
                            'price_formatted': None,
                            'image_url': '',
                            'category': None,
                            'url': url
                        }
        
        except Exception as e:
            logger.error(f"Error scraping product page: {e}")
            return {
                'name': 'Unknown Product',
                'description': '',
                'price': None,
                'price_formatted': None,
                'image_url': '',
                'category': None,
                'url': url
            }
    
    async def _generate_content_strategy(self, product_data: Dict, research_data: Dict) -> Dict:
        """Generate recommended content strategy from research"""
        
        content_types = research_data.get('content_preferences', {}).get('content_types', [])
        primary_buyers = research_data.get('target_audience', {}).get('primary_buyers', [])
        
        # Determine niche adaptation
        product_name = product_data.get('name', '').lower()
        category = product_data.get('category', '').lower()
        
        # Find closest matching niche
        niche_adaptation = None
        if 'collectible' in product_name or 'antique' in product_name or 'vintage' in product_name:
            niche_adaptation = 'collectibles'
        elif 'tech' in product_name or 'electronic' in product_name:
            niche_adaptation = 'tech'
        elif 'finance' in product_name or 'investment' in product_name:
            niche_adaptation = 'finance'
        else:
            niche_adaptation = 'general'
        
        return {
            'content_types': content_types[:5] if content_types else ['product reviews', 'tutorials'],
            'niche_adaptation': f"Use existing {niche_adaptation} niche with custom focus on {product_data.get('name', 'product')}",
            'recommended_content_styles': self._suggest_content_styles(content_types),
            'target_series': self._suggest_series(content_types),
            'target_themes': [product_data.get('name', 'Product')]
        }
    
    def _suggest_content_styles(self, content_types: list) -> list:
        """Suggest content styles based on content types"""
        
        style_mapping = {
            'buying guides': 'top_10_countdown',
            'tutorials': 'educational_documentary',
            'reviews': 'product_review',
            'comparisons': 'top_10_countdown',
            'market trends': 'news_commentary',
            'investment advice': 'news_commentary',
            'restoration': 'documentary_educational',
            'maintenance': 'tutorial_educational'
        }
        
        suggested = []
        for content_type in content_types:
            content_lower = content_type.lower()
            for keyword, style in style_mapping.items():
                if keyword in content_lower:
                    if style not in suggested:
                        suggested.append(style)
        
        return suggested[:3] if suggested else ['top_10_countdown']
    
    def _suggest_series(self, content_types: list) -> list:
        """Suggest series names based on content types"""
        
        series_suggestions = []
        
        if any('guide' in ct.lower() for ct in content_types):
            series_suggestions.append('Buying Guides')
        if any('review' in ct.lower() for ct in content_types):
            series_suggestions.append('Product Reviews')
        if any('tutorial' in ct.lower() for ct in content_types):
            series_suggestions.append('How-To Tutorials')
        if any('trend' in ct.lower() or 'market' in ct.lower() for ct in content_types):
            series_suggestions.append('Market Analysis')
        
        return series_suggestions[:3] if series_suggestions else ['Product Content']


# Singleton
product_research_service = ProductResearchService()

