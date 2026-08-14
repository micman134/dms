# flask-api/app.py - UPDATED WITH BETTER ALERT DETECTION

import os
import logging
import hashlib
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Import ML classifier
from ml_disaster_classifier import MLDisasterClassifier

# Import RSS collector
from rss_news_collector import RSSNewsCollector



# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# INITIALIZE ML CLASSIFIER, RSS COLLECTOR, AND DATABASE
# ============================================================

# Initialize ML classifier
ml_classifier = MLDisasterClassifier()

# Initialize RSS collector
rss_collector = RSSNewsCollector()

# ============================================================
# BACKGROUND STORAGE HELPER
# ============================================================
# Articles are shown to the caller as soon as they're collected +
# classified. Saving them to MySQL happens afterwards in a background
# thread so a slow/unavailable DB never delays the API response.

def _build_db_article(article, ml_result=None):
    """Map a collected+classified article onto the news_articles schema"""
    feed_info = rss_collector.feeds.get(article.get('source'), {})
    ml_result = ml_result or {}

    return {
        'id': article.get('id'),
        'source': article.get('source'),
        'source_url': feed_info.get('url'),
        'reliability': feed_info.get('reliability', 0.8),
        'title': article.get('title', ''),
        'summary': article.get('summary', ''),
        'content': article.get('content', ''),
        'link': article.get('link'),
        'published_parsed': article.get('published_parsed'),
        'author': article.get('author', ''),
        'tags': [ml_result.get('urgency')] if ml_result.get('urgency') else [],
        'relevance_score': ml_result.get('severity_score', 0),
        'disaster_types': [ml_result.get('disaster_type')] if ml_result.get('disaster_type') else [],
        'locations_mentioned': article.get('locations', [])
    }


def _store_articles_background(articles):
    """Runs in a background thread - persists articles to MySQL"""
    try:
        db_articles = [
            _build_db_article(article, article.get('ml_analysis'))
            for article in articles
        ]
        inserted, skipped = db.insert_news_articles_bulk(db_articles)
        logger.info(f"💾 DB store complete: {inserted} inserted, {skipped} skipped/duplicates")
    except Exception as e:
        logger.error(f"Background DB store failed: {e}")


def store_articles_async(articles):
    """Fire-and-forget: kick off DB storage without blocking the response"""
    thread = threading.Thread(target=_store_articles_background, args=(articles,), daemon=True)
    thread.start()

# ============================================================
# HEALTH CHECK ENDPOINT
# ============================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    bert_loaded = ml_classifier.sentiment_pipeline is not None
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'ml_classifier': 'loaded' if bert_loaded else 'fallback_mode',
        'bert_status': 'active' if bert_loaded else 'inactive'
    })

# ============================================================
# STATS ENDPOINT
# ============================================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    try:
        articles = rss_collector.collect_all_feeds(hours_back=24, limit_per_feed=10)
        
        stats = {
            'total_articles': len(articles),
            'by_urgency': {
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0
            },
            'by_type': {},
            'sources_active': len(rss_collector.feeds)
        }
        
        for article in articles[:20]:
            try:
                ml_article = {
                    'title': article['title'],
                    'summary': article['summary'],
                    'content': article.get('content', '')
                }
                ml_result = ml_classifier.classify_article(ml_article)
                
                urgency = ml_result.get('urgency', 'low')
                if urgency in stats['by_urgency']:
                    stats['by_urgency'][urgency] += 1
                
                dtype = ml_result.get('disaster_type', 'general_disaster')
                stats['by_type'][dtype] = stats['by_type'].get(dtype, 0) + 1
                
            except Exception as e:
                logger.error(f"Stats classification error: {e}")
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ML CLASSIFICATION ENDPOINTS
# ============================================================

@app.route('/api/ml/classify', methods=['POST'])
def classify_text():
    """Classify a single text using ML"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        article = {
            'title': data.get('title', text[:100]),
            'summary': text[:500],
            'content': text,
            'source': data.get('source', 'api'),
            'published': datetime.now().isoformat()
        }
        
        result = ml_classifier.classify_article(article)
        
        return jsonify({
            'success': True,
            'classification': result
        })
        
    except Exception as e:
        logger.error(f"Error classifying text: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# RSS NEWS ENDPOINTS
# ============================================================

@app.route('/api/news/disaster', methods=['GET'])
def get_disaster_news():
    """Get disaster-related news (with ML classification)"""
    try:
        hours = request.args.get('hours', 48, type=int)
        limit = request.args.get('limit', 30, type=int)
        
        logger.info(f"Fetching disaster news from last {hours} hours...")
        
        articles = rss_collector.collect_all_feeds(hours_back=hours, limit_per_feed=limit)
        
        logger.info(f"Collected {len(articles)} articles, classifying...")
        
        classified_articles = []
        for i, article in enumerate(articles[:limit]):
            try:
                ml_article = {
                    'title': article['title'],
                    'summary': article['summary'],
                    'content': article.get('content', '')
                }
                ml_result = ml_classifier.classify_article(ml_article)
                article['ml_analysis'] = ml_result
                classified_articles.append(article)
                
                urgency = ml_result.get('urgency', 'low')
                logger.debug(f"  Article {i+1}: {ml_result['disaster_type']} - {urgency}")
                
            except Exception as e:
                logger.error(f"ML error for article {i}: {e}")
                article['ml_analysis'] = {
                    'disaster_type': 'general_disaster',
                    'confidence': 50,
                    'urgency': 'low',
                    'severity_score': 30,
                    'sentiment': {'sentiment': 'neutral', 'confidence': 50, 'method': 'fallback'},
                    'needs_attention': False,
                    'affected_areas': article.get('locations', []),
                    'key_numbers': {}
                }
                classified_articles.append(article)
        
        logger.info(f"Total classified articles: {len(classified_articles)}")
        
        # Display first: kick off DB storage in the background, don't wait on it
        store_articles_async(classified_articles)
        
        return jsonify({
            'success': True,
            'count': len(classified_articles),
            'articles': classified_articles
        })
        
    except Exception as e:
        logger.error(f"Error getting disaster news: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/news/alerts', methods=['GET'])
def get_news_alerts():
    """Get news that require immediate alerts (critical/high urgency)"""
    try:
        hours = request.args.get('hours', 48, type=int)
        
        logger.info(f"=== FETCHING ALERTS (last {hours} hours) ===")
        
        articles = rss_collector.collect_all_feeds(hours_back=hours, limit_per_feed=30)
        
        logger.info(f"Total articles collected: {len(articles)}")
        
        alerts = []
        alert_count = 0
        
        for i, article in enumerate(articles):
            try:
                ml_article = {
                    'title': article['title'],
                    'summary': article['summary'],
                    'content': article.get('content', '')
                }
                ml_result = ml_classifier.classify_article(ml_article)
                article['ml_analysis'] = ml_result
                
                urgency = ml_result.get('urgency', 'low')
                severity = ml_result.get('severity_score', 0)
                needs_attention = ml_result.get('needs_attention', False)
                disaster_type = ml_result.get('disaster_type', 'unknown')
                
                # Debug log
                logger.info(f"Article {i+1}: Urgency={urgency}, Severity={severity}, Type={disaster_type}")
                logger.info(f"  Title: {article['title'][:80]}...")
                
                # Keep high and critical urgency articles
                if urgency in ['high', 'critical']:
                    alerts.append(article)
                    alert_count += 1
                    logger.info(f"  🚨 ALERT #{alert_count}: {urgency.upper()} - {disaster_type}")
                    logger.info(f"     Title: {article['title'][:100]}")
                    
            except Exception as e:
                logger.error(f"ML error for alert check on article {i}: {e}")
        
        logger.info(f"=== ALERTS FOUND: {len(alerts)} out of {len(articles)} articles ===")
        
        # Display first: kick off DB storage in the background, don't wait on it
        store_articles_async(alerts)
        
        return jsonify({
            'success': True,
            'count': len(alerts),
            'alerts': alerts
        })
        
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/news/sources', methods=['GET'])
def get_news_sources():
    """Get list of RSS sources"""
    sources = []
    for name, info in rss_collector.feeds.items():
        sources.append({
            'name': name,
            'url': info['url'],
            'reliability': info.get('reliability', 0.8)
        })
    
    return jsonify({
        'success': True,
        'sources': sources
    })

@app.route('/api/news/refresh', methods=['POST'])
def refresh_news():
    """Force refresh news collection"""
    try:
        # Clear seen articles cache
        rss_collector.clear_cache()
        
        # Collect fresh news
        articles = rss_collector.collect_all_feeds(hours_back=6, limit_per_feed=20)
        
        logger.info(f"Refresh completed: {len(articles)} articles collected")
        
        # Classify so relevance/disaster type get stored, then persist in the background
        for article in articles:
            try:
                ml_article = {
                    'title': article['title'],
                    'summary': article['summary'],
                    'content': article.get('content', '')
                }
                article['ml_analysis'] = ml_classifier.classify_article(ml_article)
            except Exception as e:
                logger.error(f"ML error during refresh classification: {e}")
                article['ml_analysis'] = {}
        
        store_articles_async(articles)
        
        return jsonify({
            'success': True,
            'message': f'Refreshed {len(articles)} articles',
            'count': len(articles)
        })
        
    except Exception as e:
        logger.error(f"Error refreshing news: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# DEBUG ENDPOINTS
# ============================================================

@app.route('/api/debug/alerts', methods=['GET'])
def debug_alerts():
    """Debug endpoint to see why alerts aren't showing"""
    try:
        hours = request.args.get('hours', 48, type=int)
        
        logger.info(f"=== DEBUG: Checking alerts for last {hours} hours ===")
        
        articles = rss_collector.collect_all_feeds(hours_back=hours, limit_per_feed=15)
        
        debug_info = {
            'total_articles': len(articles),
            'alerts_found': [],
            'classification_results': [],
            'urgency_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        }
        
        for i, article in enumerate(articles[:15]):
            try:
                ml_article = {
                    'title': article['title'],
                    'summary': article['summary'],
                    'content': article.get('content', '')
                }
                ml_result = ml_classifier.classify_article(ml_article)
                
                urgency = ml_result.get('urgency', 'low')
                severity = ml_result.get('severity_score', 0)
                disaster_type = ml_result.get('disaster_type', 'unknown')
                needs_attention = ml_result.get('needs_attention', False)
                
                debug_info['urgency_counts'][urgency] = debug_info['urgency_counts'].get(urgency, 0) + 1
                
                result_entry = {
                    'index': i + 1,
                    'title': article['title'][:100],
                    'source': article.get('source', 'unknown'),
                    'urgency': urgency,
                    'severity': severity,
                    'disaster_type': disaster_type,
                    'needs_attention': needs_attention,
                    'affected_areas': ml_result.get('affected_areas', []),
                    'key_numbers': ml_result.get('key_numbers', {}),
                    'is_alert': urgency in ['high', 'critical']
                }
                
                debug_info['classification_results'].append(result_entry)
                
                if urgency in ['high', 'critical']:
                    debug_info['alerts_found'].append({
                        'title': article['title'][:100],
                        'urgency': urgency,
                        'severity': severity
                    })
                    logger.info(f"  🔔 ALERT in debug: {urgency} - {article['title'][:80]}")
                else:
                    logger.debug(f"  No alert: {urgency} - {article['title'][:60]}")
                    
            except Exception as e:
                debug_info['classification_results'].append({
                    'index': i + 1,
                    'title': article['title'][:100],
                    'error': str(e)
                })
                logger.error(f"Error classifying article {i}: {e}")
        
        logger.info(f"=== DEBUG SUMMARY ===")
        logger.info(f"Total: {debug_info['total_articles']}")
        logger.info(f"Urgency counts: {debug_info['urgency_counts']}")
        logger.info(f"Alerts found: {len(debug_info['alerts_found'])}")
        
        return jsonify({
            'success': True,
            'debug': debug_info
        })
        
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debug/test_alert', methods=['POST'])
def test_alert():
    """Test endpoint to manually trigger an alert with sample text"""
    try:
        test_text = request.json.get('text', '')
        
        if not test_text:
            # Use sample disaster text
            test_text = "Emergency: Building collapse in Lagos with 15 people trapped. Rescue operations ongoing."
        
        article = {
            'title': test_text[:100],
            'summary': test_text,
            'content': test_text,
            'source': 'test',
            'published': datetime.now().isoformat()
        }
        
        result = ml_classifier.classify_article(article)
        
        return jsonify({
            'success': True,
            'text': test_text,
            'classification': result,
            'is_alert': result.get('urgency') in ['high', 'critical']
        })
        
    except Exception as e:
        logger.error(f"Test alert error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# SIMPLE TEST ENDPOINT
# ============================================================

@app.route('/api/test', methods=['GET'])
def test():
    """Simple test endpoint"""
    return jsonify({
        'success': True,
        'message': 'Flask API is running',
        'ml_loaded': ml_classifier.sentiment_pipeline is not None,
        'rss_feeds': len(rss_collector.feeds)
    })

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🌊 Disaster Management ML API")
    print("=" * 60)
    print(f"Server running on: http://localhost:{port}")
    print(f"Health check: http://localhost:{port}/api/health")
    print(f"Test endpoint: http://localhost:{port}/api/test")
    print(f"News endpoint: http://localhost:{port}/api/news/disaster")
    print(f"Alerts endpoint: http://localhost:{port}/api/news/alerts")
    print(f"Debug alerts: http://localhost:{port}/api/debug/alerts")
    print("=" * 60)
    
    # Run the app
    app.run(host='0.0.0.0', port=port, debug=True)
