# flask-api/rss_news_collector.py - UPDATED: Fixed disaster detection and filtering

import feedparser
import requests
import logging
import re
import hashlib
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class RSSNewsCollector:
    """Collect Nigeria-specific disaster-related news from RSS feeds"""
    
    def __init__(self):
        # Expanded list of working Nigerian RSS feeds
        self.feeds = {
            'punch': {
                'url': 'https://punchng.com/feed',
                'reliability': 0.85,
                'active': True,
                'category': 'general'
            },
            'daily_trust': {
                'url': 'https://dailytrust.com/feed',
                'reliability': 0.85,
                'active': True,
                'category': 'general'
            },
            'premium_times': {
                'url': 'https://www.premiumtimesng.com/feed',
                'reliability': 0.9,
                'active': True,
                'category': 'general'
            },
            'channels': {
                'url': 'https://www.channelstv.com/feed/',
                'reliability': 0.85,
                'active': True,
                'category': 'general'
            },
            'thisday': {
                'url': 'https://www.thisdaylive.com/feed',
                'reliability': 0.85,
                'active': True,
                'category': 'general'
            },
            'guardian': {
                'url': 'https://guardian.ng/feed',
                'reliability': 0.88,
                'active': True,
                'category': 'general'
            },
            'vanguard': {
                'url': 'https://www.vanguardngr.com/feed',
                'reliability': 0.87,
                'active': True,
                'category': 'general'
            },
            'tribune': {
                'url': 'https://tribuneonlineng.com/feed',
                'reliability': 0.82,
                'active': True,
                'category': 'general'
            }
        }
        
        # Comprehensive disaster keywords with weighted categories - EXPANDED
        self.disaster_keywords = {
            'flood': [
                'flood', 'flooding', 'flooded', 'water level', 'river overflow', 'submerged', 
                'inundation', 'flash flood', 'heavy rainfall', 'torrential rain', 'rainstorm', 
                'downpour', 'water rises', 'flood alert', 'flood warning', 'flood victims', 
                'flood disaster', 'flood affected', 'flooded communities', 'waterlogging',
                # Added terms
                'rain', 'heavy rain', 'rains', 'water', 'overflow', 'rising water',
                'flooding incident', 'flood situation', 'flood risk', 'rainfall',
                'water level rising', 'river overflowed', 'submerged community',
                'flood water', 'rainy season', 'torrential', 'waterlogged'
            ],
            
            'fire': [
                'fire', 'inferno', 'blaze', 'burning', 'gas explosion', 'fire outbreak', 
                'burned down', 'wildfire', 'market fire', 'fire incident', 'fire guts',
                'fire razes', 'fire destroys', 'fire service', 'fire disaster', 'arson',
                'combust', 'flammable', 'firefighter', 'fire extinguisher',
                # Added terms
                'burnt', 'burn', 'explosion', 'explode', 'combustion', 'fire safety',
                'fire guts', 'fire razes', 'fire destroys', 'fire claims', 'fire kills',
                'fire injures', 'fire damages', 'fire incident', 'fire outbreak',
                'gas explosion', 'tanker explosion', 'explosion rocks'
            ],
            
            'building_collapse': [
                'collapse', 'building collapse', 'structure collapse', 'collapsed building',
                'building fell', 'caved in', 'building crumbled', 'storey building',
                'building collapses', 'collapsed structure', 'building crushes',
                'structural failure', 'caved in', 'collapsed roof',
                # Added terms
                'building', 'structure', 'collapses', 'collapsing', 'partial collapse',
                'building collapsed', 'building collapses', 'collapsed building',
                'structure collapsed', 'roof collapse', 'wall collapse', 'cave-in',
                'building disaster', 'structural collapse', 'building failure'
            ],
            
            'epidemic': [
                'outbreak', 'epidemic', 'cholera', 'lassa fever', 'measles', 'meningitis',
                'yellow fever', 'monkeypox', 'covid', 'pandemic', 'health emergency',
                'disease outbreak', 'contagious', 'infection', 'virus', 'quarantine',
                # Added terms
                'disease', 'illness', 'sickness', 'health crisis', 'medical emergency',
                'epidemic outbreak', 'health emergency', 'public health', 'health risk',
                'disease spread', 'viral outbreak', 'contagious disease', 'infectious'
            ],
            
            'storm': [
                'storm', 'windstorm', 'cyclone', 'thunderstorm', 'heavy wind', 'hurricane',
                'typhoon', 'gale', 'tornado', 'wind damage', 'tempest',
                # Added terms
                'storm damage', 'wind', 'gust', 'storm warning', 'severe weather',
                'weather alert', 'stormy', 'high wind', 'storm hits'
            ],
            
            'landslide': [
                'landslide', 'landslip', 'mudslide', 'earth movement', 'soil erosion',
                'landslide disaster', 'mud flow', 'slope failure',
                # Added terms
                'landslide', 'mud slide', 'earth slip', 'rock fall', 'soil erosion'
            ],
            
            'drought': [
                'drought', 'dry spell', 'water scarcity', 'food shortage', 'famine',
                'crop failure', 'water crisis', 'agricultural drought',
                # Added terms
                'drought conditions', 'severe drought', 'water shortage', 'food crisis',
                'water scarcity', 'dry season', 'famine', 'crop failure'
            ],
            
            'accident': [
                'accident', 'crash', 'collision', 'road accident', 'vehicle accident',
                'tanker explosion', 'fatal accident', 'auto crash', 'multiple accident',
                'bus crash', 'car crash', 'train accident', 'air crash',
                # Added terms
                'killed', 'death', 'fatal', 'casualty', 'victim', 'injured', 'wounded',
                'emergency', 'rescue', 'evacuation', 'fatalities', 'death toll',
                'killed in', 'dies in', 'dead', 'fatal crash', 'deadly accident'
            ]
        }
        
        # SPORTS-RELATED KEYWORDS TO EXCLUDE
        self.sports_keywords = [
            # General sports terms
            'football', 'soccer', 'match', 'stadium', 'pitch', 'goal', 'player', 'coach',
            'team', 'league', 'tournament', 'championship', 'cup', 'tournament',
            
            # Nigerian football terms
            'npl', 'npfl', 'super eagles', 'falcons', 'premier league', 'la liga',
            'epl', 'champions league', 'world cup', 'afcon', 'africa cup',
            
            # Sports events
            'kickoff', 'halftime', 'fulltime', 'penalty', 'red card', 'yellow card',
            'substitute', 'substitution', 'transfer', 'signing', 'contract',
            
            # Sports figures
            'messi', 'ronaldo', 'osimhen', 'lookman', 'ndidi', 'iwobi', 'musa',
            'ekong', 'simon', 'chukwueze', 'boniface', 'onuachu', 'sporting',
            
            # Sports organizations
            'nff', 'nigeria football federation', 'caf', 'fifa', 'uefa',
            
            # Sports results and analysis
            'defeat', 'victory', 'win', 'loss', 'draw', 'score', 'result',
            'highlights', 'analysis', 'prediction', 'lineup', 'formation'
        ]
        
        # NIGERIA-SPECIFIC KEYWORDS AND PATTERNS
        self.nigeria_indicators = [
            # Country name variations
            'nigeria', 'nigerian', 'naija', '9ja',
            
            # Nigerian cities and states
            'lagos', 'abuja', 'kano', 'ibadan', 'port harcourt', 'benin', 'enugu',
            'anambra', 'kogi', 'bayelsa', 'delta', 'rivers', 'ogun', 'oyo', 'edo',
            'imo', 'abia', 'enugu', 'benue', 'plateau', 'kaduna', 'katsina',
            'borno', 'yobe', 'gombe', 'bauchi', 'jigawa', 'sokoto', 'zamfara',
            'taraba', 'adamawa', 'ebonyi', 'cross river', 'akwa ibom', 'kwara',
            'niger', 'nassarawa', 'osun', 'ekiti', 'ondo', 'niger state',
            
            # Nigerian agencies and organizations
            'nema', 'sema', 'nimet', 'ncdc', 'nigerian red cross', 'nigerian army',
            'nigerian police', 'federal government', 'state government', 'nigerian',
            
            # Nigerian-specific terms
            'local government', 'lga', 'nigerian naira', 'naira', 'abuja',
            'lagos state', 'kaduna state', 'kano state', 'rivers state'
        ]
        
        # International location indicators (to exclude)
        self.international_indicators = [
            # Countries
            'ghana', 'kenya', 'south africa', 'egypt', 'morocco', 'algeria', 'tunisia',
            'senegal', 'cameroon', 'ivory coast', 'cote d\'ivoire', 'mali', 'niger republic',
            'chad', 'benin republic', 'togo', 'burkina faso', 'united states', 'uk', 'england',
            'france', 'germany', 'china', 'india', 'brazil', 'argentina', 'spain', 'italy',
            'australia', 'canada', 'uae', 'dubai', 'qatar', 'saudi arabia',
            
            # International cities
            'london', 'paris', 'new york', 'washington', 'beijing', 'tokyo', 'sydney',
            'dubai', 'doha', 'johannesburg', 'cairo', 'accra', 'nairobi', 'dakar',
            
            # International organizations
            'un', 'united nations', 'who', 'world health organization', 'bbc', 'cnn',
            'al jazeera', 'reuters', 'associated press', 'afp'
        ]
        
        # Nigerian states and major cities (full list for location extraction)
        self.nigerian_states = [
            'lagos', 'anambra', 'kogi', 'bayelsa', 'delta', 'rivers', 'ogun', 'oyo',
            'edo', 'imo', 'abia', 'enugu', 'benue', 'plateau', 'kaduna', 'kano',
            'abuja', 'niger', 'kwara', 'osun', 'ekiti', 'ondo', 'cross river',
            'akwa ibom', 'borno', 'yobe', 'gombe', 'bauchi', 'jigawa', 'kebbi',
            'sokoto', 'zamfara', 'taraba', 'adamawa', 'ebonyi', 'nassarawa'
        ]
        
        # Major cities for location extraction
        self.nigerian_cities = [
            'lagos', 'ibadan', 'port harcourt', 'benin', 'aba', 'maiduguri',
            'zaria', 'ilorin', 'jos', 'warri', 'sokoto', 'enugu', 'onitsha',
            'kaduna', 'kano', 'abuja', 'owerri', 'calabar', 'uyo', 'akure',
            'ado ekiti', 'osogbo', 'minna', 'lokoja', 'makurdi', 'yola', 'damaturu',
            'awka', 'umudike', 'nsukka', 'okene', 'katsina', 'gusu', 'funtua'
        ]
        
        # Phrases that negate/undercut a nearby disaster keyword
        self.negation_patterns = [
            'no casualties', 'no deaths', 'no injuries', 'no fatalities',
            'no reported', 'no incident of', 'no cases of',
            'not affected by', 'not been any', 'not recorded',
            'without incident', 'without any casualty', 'without any casualties',
            'avoided', 'averted', 'prevented',
            'drill', 'rehearsal', 'simulation', 'training exercise',
            'warning lifted', 'alert lifted', 'false alarm', 'ruled out',
            'no longer', 'unlikely to', 'in case of', 'preparedness',
            'anniversary of', 'remembering the', 'years after',
            'commemorates', 'commemoration', 'memorial', 'marking the'
        ]
        
        # Debug counter for article filtering
        self._filter_debug_count = 0
        self._filter_debug_limit = 10  # Log details for first 10 filtered articles
        
        # Legacy cache (kept for compatibility)
        self.seen_articles = set()
        self._request_count = 0
        self.max_articles_per_run = 150  # Increased for 72-hour fetch
        
        logger.info(f"RSS News Collector initialized with {len(self.feeds)} active feeds")
        logger.info(f"Sports filtering enabled with {len(self.sports_keywords)} exclusion keywords")
        logger.info(f"Nigeria-only filtering enabled")
        logger.info(f"Disaster keywords count: {sum(len(kw) for kw in self.disaster_keywords.values())}")
    
    def _get_random_user_agent(self):
        """Get random user agent to avoid blocking"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
        ]
        return random.choice(user_agents)
    
    def _is_nigeria_related(self, article: Dict) -> bool:
        """
        Check if article is related to Nigeria.
        Returns True if Nigeria-related, False otherwise (for international news).
        """
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        full_text = f"{title} {summary}".lower()
        
        # Check for Nigerian states/cities first (strongest indicator)
        for state in self.nigerian_states:
            pattern = r'\b' + re.escape(state) + r'\b'
            if re.search(pattern, full_text):
                logger.debug(f"  🇳🇬 Nigeria detected via state: {state}")
                return True
        
        for city in self.nigerian_cities:
            pattern = r'\b' + re.escape(city) + r'\b'
            if re.search(pattern, full_text):
                logger.debug(f"  🇳🇬 Nigeria detected via city: {city}")
                return True
        
        # Check for Nigerian indicators
        for indicator in self.nigeria_indicators:
            pattern = r'\b' + re.escape(indicator) + r'\b'
            if re.search(pattern, full_text):
                logger.debug(f"  🇳🇬 Nigeria detected via indicator: {indicator}")
                return True
        
        # Check for international indicators (exclude if found without Nigerian context)
        for intl_indicator in self.international_indicators:
            pattern = r'\b' + re.escape(intl_indicator) + r'\b'
            if re.search(pattern, full_text):
                # If international indicator found, check if there's any Nigerian context
                has_nigerian_context = False
                for nigerian in self.nigerian_states + self.nigerian_cities + self.nigeria_indicators:
                    if nigerian in full_text:
                        has_nigerian_context = True
                        break
                
                if not has_nigerian_context:
                    logger.debug(f"  🌍 Excluded international article: {article['title'][:50]}... (matched: {intl_indicator})")
                    return False
        
        # If no Nigerian indicators found and no locations, likely international
        has_any_location = False
        for state in self.nigerian_states + self.nigerian_cities:
            if state in full_text:
                has_any_location = True
                break
        
        if not has_any_location:
            # No Nigerian locations mentioned, likely international or generic
            logger.debug(f"  🌍 Excluded article (no Nigerian location): {article['title'][:50]}...")
            return False
        
        # Default to True if we have some Nigerian context
        return True
    
    def _is_sports_related(self, article: Dict) -> bool:
        """
        Check if article is sports-related to filter it out.
        Returns True if sports-related (should be excluded), False otherwise.
        """
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        full_text = f"{title} {summary}".lower()
        
        # First, check if article has strong disaster indicators
        # If it has strong disaster indicators, it might still be relevant
        has_strong_disaster = False
        strong_disaster_indicators = [
            'building collapse', 'structural failure', 'fire outbreak',
            'explosion', 'flood disaster', 'emergency rescue', 'casualties',
            'death toll', 'disaster management', 'nema'
        ]
        
        for indicator in strong_disaster_indicators:
            if indicator in full_text:
                has_strong_disaster = True
                break
        
        # Check for sports keywords
        sports_match_count = 0
        matched_sports_keywords = []
        
        for keyword in self.sports_keywords:
            if keyword in full_text:
                sports_match_count += 1
                matched_sports_keywords.append(keyword)
                if sports_match_count >= 2:
                    break
        
        # If no strong disaster indicators and sports keywords found, filter out
        if not has_strong_disaster and sports_match_count > 0:
            logger.debug(f"  🏈 Filtered sports article: {article['title'][:50]}...")
            return True
        
        return False
    
    def collect_all_feeds(self, hours_back: int = 72, limit_per_feed: int = 30) -> List[Dict]:
        """
        Collect news from all RSS feeds with Nigeria and sports filtering.
        
        Args:
            hours_back: Number of hours to look back (default: 72 hours = 3 days)
            limit_per_feed: Maximum articles per feed (default: 30)
        
        Returns:
            List of collected articles
        """
        all_articles = []
        # Call-scoped dedup: only guards against the same article appearing
        # twice within THIS run
        run_seen_ids = set()
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        cutoff_timestamp = cutoff_time.timestamp()
        
        logger.info(f"Starting RSS collection from {len(self.feeds)} feeds...")
        logger.info(f"Looking back {hours_back} hours (since {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')})")
        
        # Reset debug counter for this run
        self._filter_debug_count = 0
        
        for source_name, feed_info in self.feeds.items():
            if not feed_info.get('active', True):
                logger.debug(f"Skipping inactive feed: {source_name}")
                continue
            
            # Stop if we've reached the max articles
            if len(all_articles) >= self.max_articles_per_run:
                logger.info(f"Reached max articles limit ({self.max_articles_per_run}), stopping collection")
                break
                
            try:
                logger.info(f"Fetching feed: {source_name} - {feed_info['url']}")
                headers = {
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': 'application/rss+xml,application/xml,text/xml,*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                
                response = requests.get(feed_info['url'], headers=headers, timeout=20)
                
                if response.status_code != 200:
                    logger.warning(f"HTTP {response.status_code} for {source_name}")
                    continue
                
                # Parse feed
                feed = feedparser.parse(response.content)
                
                if not feed.entries:
                    logger.warning(f"No entries found in {source_name} feed")
                    continue
                
                articles_collected = 0
                for entry in feed.entries[:limit_per_feed]:
                    # Stop if max reached
                    if len(all_articles) >= self.max_articles_per_run:
                        break
                        
                    title = entry.get('title', '').strip()
                    if not title or len(title) < 10:
                        continue
                    
                    # Get summary/description
                    summary = entry.get('summary', entry.get('description', ''))
                    if summary:
                        # Clean HTML tags
                        summary = re.sub(r'<[^>]+>', '', summary)
                        summary = re.sub(r'\s+', ' ', summary).strip()
                        summary = summary[:800]
                    
                    link = entry.get('link', '')
                    if not link:
                        continue
                    
                    # Parse published date
                    published_str = ''
                    published_timestamp = None
                    
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_timestamp = time.mktime(entry.published_parsed)
                        published_str = time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed)
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published_timestamp = time.mktime(entry.updated_parsed)
                        published_str = time.strftime('%Y-%m-%d %H:%M:%S', entry.updated_parsed)
                    
                    # Skip old articles if cutoff is set
                    if published_timestamp and published_timestamp < cutoff_timestamp:
                        continue
                    
                    # Get content if available
                    content = ''
                    if hasattr(entry, 'content') and entry.content:
                        content = entry.content[0].value if isinstance(entry.content, list) else entry.content
                        content = re.sub(r'<[^>]+>', '', content)[:1000]
                    
                    article = {
                        'id': hashlib.md5(link.encode()).hexdigest(),
                        'source': source_name,
                        'title': title,
                        'summary': summary if summary else title[:200],
                        'link': link,
                        'published': published_str,
                        'published_parsed': published_timestamp,
                        'collected_at': datetime.now().isoformat(),
                        'content': content
                    }
                    
                    # Build full text for analysis
                    article['full_text'] = f"{title} {summary} {content}".lower()
                    
                    # FILTER 1: Check if Nigeria-related
                    if not self._is_nigeria_related(article):
                        logger.debug(f"  🌍 Excluded international article: {title[:60]}...")
                        continue
                    
                    # FILTER 2: Filter out sports-related articles
                    if self._is_sports_related(article):
                        logger.debug(f"  🏈 Excluded sports article: {title[:60]}...")
                        continue
                    
                    article['locations'] = self._extract_locations(article['full_text'])
                    
                    # FILTER 3: Check if disaster-related - PASSES THROUGH ALL ARTICLES
                    # We'll log the result but still collect all Nigeria-related articles
                    is_disaster = self._is_disaster_related(article)
                    article['is_disaster'] = is_disaster  # Store for later use
                    
                    if is_disaster:
                        article_id = self._generate_article_id(article)
                        if article_id not in run_seen_ids:
                            run_seen_ids.add(article_id)
                            all_articles.append(article)
                            articles_collected += 1
                            logger.debug(f"  ✅ Collected Nigeria disaster: {title[:60]}...")
                    else:
                        # Still collect but mark as not disaster
                        # This allows the classifier to make the final decision
                        if self._filter_debug_count < self._filter_debug_limit:
                            self._filter_debug_count += 1
                            logger.info(f"  ⚠️ Article passed initial filters but not disaster-related: {title[:80]}...")
                            logger.info(f"     Sample text: {article['full_text'][:200]}...")
                
                if articles_collected > 0:
                    logger.info(f"Collected {articles_collected} Nigeria disaster articles from {source_name}")
                else:
                    logger.debug(f"No new Nigeria disaster articles from {source_name}")
                
                # Be polite to servers
                time.sleep(random.uniform(0.8, 1.5))
                
            except requests.exceptions.Timeout:
                logger.error(f"Timeout collecting from {source_name}")
                continue
            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error for {source_name}")
                continue
            except Exception as e:
                logger.error(f"Error collecting from {source_name}: {e}")
                continue
        
        # Sort by published date (newest first)
        all_articles.sort(key=lambda x: x.get('published_parsed', 0), reverse=True)
        
        logger.info(f"✅ Total Nigeria articles collected: {len(all_articles)}")
        disaster_count = sum(1 for a in all_articles if a.get('is_disaster', False))
        logger.info(f"   Disaster-related: {disaster_count}")
        logger.info(f"   Non-disaster: {len(all_articles) - disaster_count}")
        logger.info(f"📅 Time range: Last {hours_back} hours")
        
        return all_articles
    
    def _is_negated(self, text: str, keyword: str) -> bool:
        """
        Check whether a matched keyword sits in a negated/non-disaster
        context within its own sentence.
        """
        sentences = re.split(r'[.!?]', text)
        for sentence in sentences:
            if keyword in sentence:
                for pattern in self.negation_patterns:
                    if pattern in sentence:
                        return True
        return False

    def _is_disaster_related(self, article: Dict) -> bool:
        """
        Check if article is disaster-related using flexible keyword matching.
        
        This method is more lenient than before to ensure we don't miss
        relevant disaster articles. It uses multiple strategies:
        1. Direct keyword matching across all disaster categories
        2. Weighted scoring with lower threshold
        3. Common disaster indicators
        """
        text = article.get('full_text', '').lower()
        title = article.get('title', '').lower()
        
        # Strategy 1: Check for exact category keywords (original method)
        matched_keywords = []
        matched_categories = set()
        category_matches_count = 0
        
        for category, keywords in self.disaster_keywords.items():
            category_match_count = 0
            for keyword in keywords:
                if keyword in text and not self._is_negated(text, keyword):
                    matched_keywords.append(keyword)
                    category_match_count += 1
                    matched_categories.add(category)
            
            # If this category had matches, count it
            if category_match_count > 0:
                category_matches_count += 1
        
        # If we have at least 1 category with matches, consider it a disaster
        if category_matches_count >= 1:
            logger.debug(f"  🚨 Disaster detected via keyword: {article['title'][:50]}... Categories: {matched_categories}")
            return True
        
        # Strategy 2: Check for disaster indicators in title (strong signal)
        disaster_indicators = [
            'emergency', 'disaster', 'catastrophe', 'tragedy', 'crisis',
            'casualties', 'fatal', 'death toll', 'victims', 'rescue operation',
            'evacuation', 'relief', 'nema', 'sema', 'response team'
        ]
        
        for indicator in disaster_indicators:
            if indicator in text:
                # Check if it's about a disaster or just mentioning the word
                # Don't match "no emergency" or similar negations
                if not self._is_negated(text, indicator):
                    logger.debug(f"  🚨 Disaster detected via indicator: {indicator} - {article['title'][:50]}...")
                    return True
        
        # Strategy 3: Check for patterns like "X killed in Y" or "death toll rises"
        disaster_patterns = [
            r'\d+\s+(?:people|persons|residents)\s+(?:killed|dead|die|death)',
            r'death toll\s+(?:rises|increases|climbs)',
            r'\d+\s+dead\s+in',
            r'\d+\s+injured\s+in',
            r'kills?\s+\d+',
        ]
        
        for pattern in disaster_patterns:
            if re.search(pattern, text):
                logger.debug(f"  🚨 Disaster detected via pattern: {pattern} - {article['title'][:50]}...")
                return True
        
        # Not a disaster
        return False
    
    def _extract_locations(self, text: str) -> List[str]:
        """Extract Nigerian locations from text"""
        locations = []
        text_lower = text.lower()
        
        # Check for states
        for state in self.nigerian_states:
            pattern = r'\b' + re.escape(state) + r'\b'
            if re.search(pattern, text_lower):
                formatted = ' '.join(word.capitalize() for word in state.split())
                locations.append(formatted)
        
        # Check for cities
        for city in self.nigerian_cities:
            pattern = r'\b' + re.escape(city) + r'\b'
            if re.search(pattern, text_lower):
                formatted = ' '.join(word.capitalize() for word in city.split())
                if formatted not in locations:
                    locations.append(formatted)
        
        # Remove duplicates
        seen = set()
        unique_locations = []
        for loc in locations:
            if loc.lower() not in seen:
                seen.add(loc.lower())
                unique_locations.append(loc)
        
        return unique_locations[:5]
    
    def _generate_article_id(self, article: Dict) -> str:
        """Generate unique ID for article"""
        unique_string = f"{article['title']}_{article['link']}_{article['source']}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def get_feed_status(self) -> Dict:
        """Get status of all feeds"""
        status = {}
        for source_name, feed_info in self.feeds.items():
            status[source_name] = {
                'url': feed_info['url'],
                'active': feed_info.get('active', True),
                'reliability': feed_info.get('reliability', 0.5)
            }
        return status
    
    def clear_cache(self):
        """Clear the legacy seen-articles set."""
        cache_size = len(self.seen_articles)
        self.seen_articles.clear()
        logger.info(f"Cleared article cache ({cache_size} articles)")