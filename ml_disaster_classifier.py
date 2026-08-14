# flask-api/ml_disaster_classifier.py - UPDATED: Fixed urgency classification

import logging
import re
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple
import json

logger = logging.getLogger(__name__)

class MLDisasterClassifier:
    """
    Machine Learning classifier for disaster news using BERT
    Handles sentiment analysis, disaster type classification, and urgency detection
    """
    
    def __init__(self):
        self.bert_model = None
        self.tokenizer = None
        
        # Disaster categories
        self.disaster_categories = [
            'flood',
            'fire', 
            'storm',
            'landslide',
            'drought',
            'epidemic',
            'building_collapse',
            'accident',
            'general_disaster'
        ]
        
        # Urgency levels
        self.urgency_map = {
            'building_collapse': 'critical',
            'flood': 'high',
            'fire': 'high',
            'epidemic': 'high',
            'storm': 'medium',
            'landslide': 'high',
            'drought': 'medium',
            'accident': 'medium',
            'general_disaster': 'low'  # ← Changed from 'low' to 'medium'? Actually this is fine
        }
        
        # Nigerian states for location validation
        self.nigerian_states = [
            'lagos', 'anambra', 'kogi', 'bayelsa', 'delta', 'rivers', 'ogun', 'oyo',
            'edo', 'imo', 'abia', 'enugu', 'benue', 'plateau', 'kaduna', 'kano',
            'abuja', 'niger', 'kwara', 'osun', 'ekiti', 'ondo', 'cross river',
            'akwa ibom', 'borno', 'yobe', 'gombe', 'bauchi', 'jigawa', 'katsina',
            'kebbi', 'sokoto', 'zamfara', 'taraba', 'adamawa', 'ebonyi', 'nassarawa'
        ]
        
        # Nigerian cities
        self.nigerian_cities = [
            'lagos', 'ibadan', 'port harcourt', 'benin', 'benin city', 'aba', 'maiduguri',
            'zaria', 'ilorin', 'jos', 'warri', 'sokoto', 'enugu', 'onitsha',
            'kaduna', 'kano', 'abuja', 'owerri', 'calabar', 'uyo', 'akure',
            'yola', 'makurdi', 'lokoja', 'minna', 'katsina', 'gusau', 'dutse',
            'damaturu', 'bauchi', 'gombe', 'jalingo', 'lafia', 'ado ekiti',
            'osogbo', 'ogbomoso', 'oyo', 'ilesa', 'ife', 'okene', 'auchi',
            'sapele', 'ughelli', 'asaba', 'nnewi', 'awka', 'umuahia',
            'abakaliki', 'abeokuta'
        ]

        # Nigerian LGAs / local areas
        self.nigerian_lgas = [
            'ikeja', 'surulere', 'eti-osa', 'eti osa', 'apapa', 'badagry',
            'onitsha north', 'onitsha south', 'oshimili north', 'oshimili south',
            'yenagoa', 'brass', 'nembe', 'ekeremor', 'patani', 'burutu',
            'warri south', 'warri north', 'warri south-west',
            'port harcourt city', 'obio/akpor', 'obio akpor', 'degema',
            'bonny', 'okrika', 'idah', 'ibaji', 'ajaokuta', 'guma', 'agatu',
            'buruku', 'katsina-ala', 'katsina ala', 'gboko', 'otukpo',
            'akwanga', 'keffi', 'abaji', 'gwagwalada', 'kuje', 'bwari', 'kwali'
        ]

        # Named landmarks
        self.nigerian_landmarks = [
            'third mainland bridge', 'lekki-ikoyi link bridge', 'lekki ikoyi link bridge',
            'ogun river', 'niger river', 'benue river', 'lake chad',
            'kainji lake', 'jebba lake', 'lagos lagoon', 'lekki lagoon'
        ]

        # Nigeria-specific indicators
        self.nigeria_indicators = [
            'nigeria', 'nigerian', 'naija', 'nema', 'sema', 'lagos state',
            'abuja', 'federal government', 'state government'
        ]
        
        # Phrases that negate/undercut a nearby disaster or urgency keyword
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
            'memorial', 'commemorate', 'marking the'
        ]
        
        # Load ML models
        self._load_bert_model()
        self._load_keyword_classifier()
    
    def _load_bert_model(self):
        """Load pre-trained BERT model for sentiment analysis"""
        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
            
            # Use a sentiment analysis model
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                device=-1  # Use CPU
            )
            
            # Load tokenizer for text processing
            self.tokenizer = AutoTokenizer.from_pretrained(
                "nlptown/bert-base-multilingual-uncased-sentiment"
            )
            
            logger.info("✅ BERT sentiment model loaded successfully")
            
        except ImportError:
            logger.warning("⚠️ Transformers not installed. Using fallback classifier.")
            self.sentiment_pipeline = None
        except Exception as e:
            logger.error(f"❌ Failed to load BERT model: {e}")
            self.sentiment_pipeline = None
    
    def _load_keyword_classifier(self):
        """Load keyword-based classifier as fallback"""
        self.keyword_weights = {
            'flood': {
                'keywords': ['flood', 'flooding', 'flooded', 'water level', 'river overflow', 
                           'submerged', 'inundation', 'flash flood', 'heavy rainfall'],
                'weight': 1.0
            },
            'fire': {
                'keywords': ['fire', 'inferno', 'blaze', 'burning', 'gas explosion', 
                           'fire outbreak', 'burned down', 'wildfire'],
                'weight': 1.0
            },
            'building_collapse': {
                'keywords': ['building collapse', 'structure collapse', 'collapsed building', 
                           'building fell', 'caved in'],
                'weight': 1.2
            },
            'epidemic': {
                'keywords': ['outbreak', 'epidemic', 'cholera', 'lassa fever', 'measles',
                           'meningitis', 'yellow fever', 'monkeypox', 'covid'],
                'weight': 1.0
            },
            'storm': {
                'keywords': ['storm', 'windstorm', 'cyclone', 'thunderstorm', 'heavy wind',
                           'hurricane', 'typhoon'],
                'weight': 0.9
            },
            'landslide': {
                'keywords': ['landslide', 'landslip', 'mudslide', 'earth movement', 
                           'soil erosion'],
                'weight': 1.0
            },
            'drought': {
                'keywords': ['drought', 'dry spell', 'water scarcity', 'food shortage',
                           'famine', 'crop failure'],
                'weight': 0.8
            },
            'accident': {
                'keywords': ['accident', 'crash', 'collision', 'road accident', 
                           'vehicle accident'],
                'weight': 0.7
            }
        }
        
        # Sentiment keywords
        self.sentiment_keywords = {
            'positive': ['rescue', 'saved', 'recovered', 'safe', 'evacuated', 'aid', 'relief'],
            'negative': ['death', 'killed', 'died', 'casualty', 'injured', 'trapped', 'missing',
                        'destroyed', 'collapsed', 'damage'],
            'neutral': ['reported', 'said', 'according', 'stated', 'announced']
        }
    
    def _is_article_nigeria_related(self, text: str) -> bool:
        """Check if article is actually about Nigeria."""
        text_lower = text.lower()
        
        for state in self.nigerian_states:
            pattern = r'\b' + re.escape(state) + r'\b'
            if re.search(pattern, text_lower):
                return True
        
        for city in self.nigerian_cities:
            pattern = r'\b' + re.escape(city) + r'\b'
            if re.search(pattern, text_lower):
                return True

        for place in self.nigerian_lgas + self.nigerian_landmarks:
            pattern = r'\b' + re.escape(place) + r'\b'
            if re.search(pattern, text_lower):
                return True

        for indicator in self.nigeria_indicators:
            pattern = r'\b' + re.escape(indicator) + r'\b'
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _is_negated(self, text: str, keyword: str) -> bool:
        """Check whether a matched keyword sits in a negated/non-disaster context."""
        text_lower = text.lower()
        sentences = re.split(r'[.!?]', text_lower)

        for sentence in sentences:
            if keyword in sentence:
                for pattern in self.negation_patterns:
                    if pattern in sentence:
                        return True
        return False

    def classify_article(self, article: Dict) -> Dict:
        """Main classification method - analyzes article and returns ML results"""
        title = article.get('title', '') or ''
        body = f"{article.get('summary', '')} {article.get('content', '')}"
        full_text = f"{title} {body}"
        
        is_nigeria_related = self._is_article_nigeria_related(full_text)
        
        bert_sentiment = self._get_bert_sentiment(full_text)
        keyword_results = self._keyword_classify(title, body)
        keyword_sentiment = self._keyword_sentiment(full_text)
        
        disaster_type = keyword_results.get('primary_type', 'general_disaster')
        confidence = keyword_results.get('confidence', 50)
        all_types = keyword_results.get('all_types', [])
        keywords_matched = keyword_results.get('keywords_matched', {})
        
        if bert_sentiment:
            if bert_sentiment.get('sentiment') == 'positive':
                confidence = min(95, confidence + 5)
            elif bert_sentiment.get('sentiment') == 'negative':
                confidence = min(95, confidence + 10)
            sentiment_result = bert_sentiment
        else:
            sentiment_result = keyword_sentiment
        
        key_numbers = self._extract_key_numbers(full_text)
        severity_score = self._calculate_severity(full_text, disaster_type, sentiment_result, key_numbers)
        urgency = self._determine_urgency(disaster_type, full_text, keyword_results, key_numbers)
        
        affected_areas = []
        if is_nigeria_related:
            affected_areas = self._extract_affected_areas(full_text)
        
        return {
            'disaster_type': disaster_type,
            'confidence': confidence,
            'urgency': urgency,
            'sentiment': sentiment_result,
            'severity_score': severity_score,
            'needs_attention': urgency in ['high', 'critical'],
            'affected_areas': affected_areas,
            'key_numbers': key_numbers,
            'all_types': all_types,
            'keywords_matched': keywords_matched,
            'is_nigeria_related': is_nigeria_related
        }
    
    def _get_bert_sentiment(self, text: str) -> Dict:
        """Get sentiment using BERT model"""
        if not self.sentiment_pipeline:
            return None
        
        try:
            text = text[:512]
            result = self.sentiment_pipeline(text)[0]
            label = result['label']
            score = result['score']
            
            star_match = re.search(r'(\d+)', label)
            stars = int(star_match.group(1)) if star_match else 3
            
            if stars >= 4:
                sentiment = 'positive'
            elif stars <= 2:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'
            
            return {
                'sentiment': sentiment,
                'confidence': score * 100,
                'stars': stars,
                'label': label,
                'method': 'bert'
            }
            
        except Exception as e:
            logger.error(f"BERT sentiment error: {e}")
            return None
    
    def _keyword_classify(self, title: str, body: str = '') -> Dict:
        """Classify using keyword-based approach."""
        title_lower = title.lower()
        body_lower = body.lower()
        combined_lower = f"{title_lower} {body_lower}"

        TITLE_WEIGHT = 2.0
        BODY_WEIGHT = 1.0

        scores = {}
        keywords_matched = {}
        match_strength = {}

        for disaster_type, data in self.keyword_weights.items():
            score = 0.0
            matched = []

            for keyword in data['keywords']:
                if keyword in combined_lower and self._is_negated(combined_lower, keyword):
                    continue

                title_hits = title_lower.count(keyword)
                body_hits = body_lower.count(keyword)

                if title_hits == 0 and body_hits == 0:
                    continue

                weighted_hits = (title_hits * TITLE_WEIGHT) + min(body_hits, 3) * BODY_WEIGHT
                score += data['weight'] * weighted_hits
                matched.append(keyword)

            scores[disaster_type] = score
            keywords_matched[disaster_type] = matched
            match_strength[disaster_type] = len(matched)

        if max(scores.values()) > 0:
            primary_type = max(scores, key=scores.get)
            max_score = scores[primary_type]
            total_score = sum(scores.values())
            dominance = max_score / total_score if total_score > 0 else 0

            confidence = dominance * 100
            distinct_matches = match_strength[primary_type]
            if distinct_matches == 1:
                confidence = min(confidence, 55)
            elif distinct_matches == 2:
                confidence = min(confidence, 75)

            confidence = int(min(95, max(30, confidence)))
        else:
            primary_type = 'general_disaster'
            confidence = 30
        
        all_types = [t for t, s in scores.items() if s > 0]
        
        return {
            'primary_type': primary_type,
            'confidence': confidence,
            'all_types': all_types,
            'scores': scores,
            'keywords_matched': keywords_matched
        }
    
    def _keyword_sentiment(self, text: str) -> Dict:
        """Sentiment analysis using keywords (fallback)"""
        text_lower = text.lower()
        
        positive_count = sum(1 for kw in self.sentiment_keywords['positive'] if kw in text_lower)
        negative_count = sum(1 for kw in self.sentiment_keywords['negative'] if kw in text_lower)
        neutral_count = sum(1 for kw in self.sentiment_keywords['neutral'] if kw in text_lower)
        
        total = positive_count + negative_count + neutral_count
        
        if total == 0:
            return {
                'sentiment': 'neutral',
                'confidence': 50,
                'stars': 3,
                'method': 'keyword'
            }
        
        if positive_count > negative_count:
            sentiment = 'positive'
            confidence = int((positive_count / total) * 100)
            stars = 4
        elif negative_count > positive_count:
            sentiment = 'negative'
            confidence = int((negative_count / total) * 100)
            stars = 2
        else:
            sentiment = 'neutral'
            confidence = 50
            stars = 3
        
        return {
            'sentiment': sentiment,
            'confidence': confidence,
            'stars': stars,
            'method': 'keyword'
        }
    
    def _determine_urgency(self, disaster_type: str, text: str, keyword_results: Dict,
                            key_numbers: Dict = None) -> str:
        """Determine urgency level based on multiple factors"""
        
        key_numbers = key_numbers or {}

        # Base urgency from disaster type
        base_urgency = self.urgency_map.get(disaster_type, 'medium')
        
        text_lower = text.lower()
        
        # CRITICAL FIX: Only escalate to critical if we have actual disaster evidence
        # First, check if this is actually a disaster article at all
        has_disaster_keywords = any(
            keyword in text_lower 
            for keywords in self.keyword_weights.values() 
            for keyword in keywords['keywords']
        )
        
        # If no disaster keywords, never escalate beyond 'low'
        if not has_disaster_keywords:
            logger.debug(f"No disaster keywords found, setting urgency to 'low'")
            return 'low'
        
        # Scale-based escalation: only if we have actual casualty/impact counts
        # AND the article has disaster keywords
        if has_disaster_keywords:
            if key_numbers.get('deaths', 0) >= 1:
                return 'critical'
            if key_numbers.get('injured', 0) >= 5 or key_numbers.get('trapped', 0) >= 1:
                return 'critical'
            if key_numbers.get('displaced', 0) >= 50 or key_numbers.get('affected', 0) >= 50:
                return 'high'
        
        # Check for critical keywords - BUT ONLY if disaster keywords are present
        if has_disaster_keywords:
            critical_indicators = [
                'trapped', 'rescue', 'emergency', 'urgent', 'immediate help',
                'casualty', 'fatal', 'death', 'collapsed', 'buried'
            ]
            
            for indicator in critical_indicators:
                if indicator in text_lower and not self._is_negated(text_lower, indicator):
                    return 'critical'
        
        # Check for high urgency keywords (same negation guard)
        if has_disaster_keywords:
            high_indicators = [
                'evacuate', 'evacuation', 'injured', 'displaced', 'flooded',
                'fire outbreak', 'explosion', 'outbreak'
            ]
            
            for indicator in high_indicators:
                if indicator in text_lower and not self._is_negated(text_lower, indicator):
                    return 'high'
        
        # Check if multiple disaster types (worsens situation)
        if len(keyword_results.get('all_types', [])) > 1 and has_disaster_keywords:
            if base_urgency == 'medium':
                return 'high'
        
        # For 'general_disaster' with low confidence, return 'low'
        if disaster_type == 'general_disaster' and keyword_results.get('confidence', 0) < 40:
            return 'low'
        
        return base_urgency
    
    def _calculate_severity(self, text: str, disaster_type: str, sentiment: Dict,
                             key_numbers: Dict = None) -> int:
        """Calculate severity score (0-100)"""
        text_lower = text.lower()
        key_numbers = key_numbers or {}
        
        # Base severity by disaster type
        type_severity = {
            'building_collapse': 90,
            'flood': 70,
            'fire': 75,
            'epidemic': 80,
            'landslide': 70,
            'storm': 60,
            'drought': 50,
            'accident': 65,
            'general_disaster': 40
        }
        severity = type_severity.get(disaster_type, 50)
        
        # Adjust based on sentiment (negative sentiment increases severity)
        if sentiment.get('sentiment') == 'negative':
            severity = min(100, severity + 15)
        elif sentiment.get('sentiment') == 'positive':
            severity = max(0, severity - 10)
        
        # Scale-aware adjustment
        deaths = key_numbers.get('deaths', 0)
        injured = key_numbers.get('injured', 0)
        displaced = key_numbers.get('displaced', 0) + key_numbers.get('affected', 0)

        if deaths > 0:
            severity = min(100, severity + 15 + min(20, deaths * 2))
        elif any(word in text_lower for word in ['death', 'killed', 'fatal']):
            severity = min(100, severity + 10)

        if injured > 0:
            severity = min(100, severity + min(15, injured))
        elif any(word in text_lower for word in ['injured', 'wounded', 'hurt']):
            severity = min(100, severity + 5)

        if displaced >= 100:
            severity = min(100, severity + 15)
        elif displaced >= 10:
            severity = min(100, severity + 8)
        elif any(word in text_lower for word in ['many', 'hundreds', 'thousands']):
            severity = min(100, severity + 10)

        if any(word in text_lower for word in ['trapped', 'rescue']):
            severity = min(100, severity + 15)
        
        return min(100, max(0, severity))
    
    def _extract_affected_areas(self, text: str) -> List[str]:
        """Extract affected areas from text - ONLY for Nigeria-related articles"""
        text_lower = text.lower()
        areas = []
        
        has_nigeria_context = self._is_article_nigeria_related(text)

        if not has_nigeria_context:
            logger.debug("No Nigeria context found, skipping location extraction")
            return []
        
        for state in self.nigerian_states:
            pattern = r'\b' + re.escape(state) + r'\b'
            if re.search(pattern, text_lower):
                if self._is_location_in_disaster_context(text, state):
                    areas.append(state.title())
        
        for city in self.nigerian_cities:
            pattern = r'\b' + re.escape(city) + r'\b'
            if re.search(pattern, text_lower):
                if city not in [a.lower() for a in areas]:
                    if self._is_location_in_disaster_context(text, city):
                        areas.append(city.title())

        for lga in self.nigerian_lgas:
            pattern = r'\b' + re.escape(lga) + r'\b'
            if re.search(pattern, text_lower):
                if lga not in [a.lower() for a in areas]:
                    if self._is_location_in_disaster_context(text, lga):
                        areas.append(lga.title())

        for landmark in self.nigerian_landmarks:
            pattern = r'\b' + re.escape(landmark) + r'\b'
            if re.search(pattern, text_lower):
                if landmark not in [a.lower() for a in areas]:
                    if self._is_location_in_disaster_context(text, landmark):
                        areas.append(landmark.title())

        seen = set()
        unique_areas = []
        for area in areas:
            if area.lower() not in seen:
                seen.add(area.lower())
                unique_areas.append(area)
        
        logger.debug(f"Extracted affected areas: {unique_areas}")
        return unique_areas[:5]
    
    def _is_location_in_disaster_context(self, text: str, location: str) -> bool:
        """Check if a location mention is actually in a disaster-related context."""
        text_lower = text.lower()
        location_lower = location.lower()
        
        disaster_context_keywords = [
            'flood', 'flooding', 'flooded', 'submerged', 'inundation',
            'water level', 'river overflow', 'waterlogging',
            'fire', 'blaze', 'inferno', 'burning', 'burned down', 'wildfire',
            'arson', 'gas explosion', 'fire outbreak', 'fire guts', 'fire razes',
            'collapse', 'collapsed', 'building collapse', 'caved in',
            'structural failure', 'accident', 'crash', 'collision',
            'tanker explosion',
            'casualty', 'casualties', 'death', 'killed', 'died', 'fatal',
            'injured', 'wounded', 'trapped', 'rescue', 'rescued',
            'emergency', 'evacuation', 'evacuate', 'disaster', 'crisis',
            'victims', 'damage', 'destroyed', 'outbreak', 'epidemic',
            'storm', 'windstorm', 'tornado', 'landslide', 'landslip',
            'mudslide', 'mud flow', 'drought', 'famine', 'water scarcity',
            'explosion', 'exploded'
        ]

        sentences = re.split(r'[.!?]', text_lower)
        location_sentence_indices = [
            i for i, sentence in enumerate(sentences) if location_lower in sentence
        ]

        for idx in location_sentence_indices:
            window = sentences[max(0, idx - 1):idx + 2]
            for sentence in window:
                for keyword in disaster_context_keywords:
                    if keyword in sentence:
                        return True

        return False
    
    def _extract_key_numbers(self, text: str) -> Dict:
        """Extract key numbers from text (casualties, displaced, etc.)"""
        text_lower = text.lower()
        numbers = {}
        
        # FIRST: Check if this is actually a disaster article
        disaster_keywords = []
        for kw_list in self.keyword_weights.values():
            disaster_keywords.extend(kw_list['keywords'])
        
        has_disaster_keyword = any(kw in text_lower for kw in disaster_keywords)
        
        # If no disaster keywords, return empty dict (don't extract numbers)
        if not has_disaster_keyword:
            return {}
        
        connector = r'\s*(?:people\s+|persons\s+)?(?:were\s+|are\s+|have\s+been\s+)?(?:confirmed\s+|reportedly\s+)?'
        patterns = {
            'deaths': r'(\d+)' + connector + r'(?:dead|died|killed|fatalit(?:y|ies))',
            'injured': r'(\d+)' + connector + r'(?:injured|wounded|hurt)',
            'trapped': r'(\d+)' + connector + r'(?:trapped|stranded|buried)',
            'displaced': r'(\d+)' + connector + r'(?:displaced|homeless|evacuated)',
            'affected': r'(\d+)' + connector + r'(?:affected|impacted)',
            'rescued': r'(\d+)' + connector + r'(?:rescued|saved)',
            'houses': r'(\d+)\s*(?:houses?|homes?|buildings?)',
            'families': r'(\d+)\s*(?:families?|households?)'
        }
        
        for key, pattern in patterns.items():
            matches = re.findall(pattern, text_lower)
            if matches:
                numbers[key] = max(int(m) for m in matches)
        
        return numbers
    
    def batch_classify(self, articles: List[Dict]) -> List[Dict]:
        """Classify multiple articles in batch"""
        for article in articles:
            try:
                article['ml_analysis'] = self.classify_article(article)
            except Exception as e:
                logger.error(f"Error classifying article: {e}")
                article['ml_analysis'] = {
                    'disaster_type': 'general_disaster',
                    'confidence': 50,
                    'urgency': 'low',
                    'severity_score': 30,
                    'sentiment': {'sentiment': 'neutral', 'confidence': 50, 'method': 'fallback'},
                    'needs_attention': False,
                    'affected_areas': article.get('locations', []),
                    'key_numbers': {},
                    'is_nigeria_related': False
                }
        
        articles.sort(key=lambda x: x.get('ml_analysis', {}).get('severity_score', 0), reverse=True)
        return articles
    
    def get_alert_recommendation(self, ml_result: Dict) -> Dict:
        """Generate alert recommendation based on ML analysis"""
        urgency = ml_result.get('urgency', 'low')
        severity = ml_result.get('severity_score', 0)
        disaster_type = ml_result.get('disaster_type', 'general_disaster')
        
        if urgency == 'critical' or severity > 85:
            return {
                'should_alert': True,
                'alert_level': 'critical',
                'reason': f"Critical urgency - {disaster_type.replace('_', ' ')} event",
                'recommended_action': f"⚠️ CRITICAL: Immediate response required for {disaster_type.replace('_', ' ')}."
            }
        elif urgency == 'high' or severity > 70:
            return {
                'should_alert': True,
                'alert_level': 'warning',
                'reason': f"High urgency - {disaster_type.replace('_', ' ')} event",
                'recommended_action': f"🚨 URGENT: Deploy resources for {disaster_type.replace('_', ' ')} within 1 hour."
            }
        else:
            return {
                'should_alert': False,
                'alert_level': 'info',
                'reason': "Monitoring only",
                'recommended_action': f"ℹ️ Informational: Monitor {disaster_type.replace('_', ' ')} situation."
            }