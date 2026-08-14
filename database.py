# flask-api/database.py

import os
import json
import logging
from datetime import datetime

import mysql.connector
from mysql.connector import Error

logger = logging.getLogger(__name__)

# The specific categories MLDisasterClassifier/RSSNewsCollector assign -
# kept in sync with ml_disaster_classifier.py's keyword_weights and
# rss_news_collector.py's disaster_keywords categories.
SPECIFIC_DISASTER_TYPES = {
    'flood', 'fire', 'building_collapse', 'epidemic',
    'storm', 'landslide', 'drought', 'accident'
}

# 'general_disaster' is the classifier's fallback when no specific category
# keyword matched strongly - it's only trusted enough to store if the
# confidence behind it clears this bar. Below it, it's too ambiguous to be
# worth persisting as a "disaster".
MIN_CONFIDENCE_FOR_GENERAL = 40


class Database:
    """MySQL connection wrapper for the disaster news pipeline"""

    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.user = os.getenv('DB_USER', 'root')
        self.password = os.getenv('DB_PASSWORD', '')
        self.database = os.getenv('DB_NAME', 'disaster_management')
        self.port = int(os.getenv('DB_PORT', 3306))
        self.connection = None
        self.connect()

    def connect(self):
        """Open (or reopen) the MySQL connection"""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                autocommit=False
            )
            logger.info(f"Connected to MySQL database '{self.database}' at {self.host}:{self.port}")
        except Error as e:
            logger.error(f"Error connecting to MySQL: {e}")
            self.connection = None

    def is_connected(self):
        """Check connection is alive, reconnecting once if it dropped"""
        try:
            if self.connection is not None and self.connection.is_connected():
                return True
        except Error:
            pass

        # Try a single reconnect - long-lived Flask processes can lose
        # idle MySQL connections (wait_timeout) between requests.
        logger.warning("MySQL connection not active, attempting to reconnect...")
        self.connect()
        try:
            return self.connection is not None and self.connection.is_connected()
        except Error:
            return False

    def _is_disaster_related(self, ml):
        """
        Storage-layer gate: only persist articles the ML step actually
        confirmed as disaster-related. RSSNewsCollector already filters on
        disaster keywords at collection time and MLDisasterClassifier
        classifies each article, but neither of those guarantees survives
        a failed classification call (app.py falls back to an empty/low
        dict on error) or a genuinely ambiguous article. This is the last
        checkpoint before anything reaches the database, so nothing gets
        stored on trust alone.

        Returns (is_disaster: bool, reason: str | None) - reason is only
        set when rejecting, for logging.
        """
        if not ml:
            return False, 'no ML analysis (classification unavailable/failed)'

        disaster_type = (ml.get('disaster_type') or '').strip()
        if not disaster_type:
            return False, 'no disaster_type on the ML result'

        if disaster_type in SPECIFIC_DISASTER_TYPES:
            return True, None

        confidence = ml.get('confidence') or 0
        if disaster_type == 'general_disaster' and confidence >= MIN_CONFIDENCE_FOR_GENERAL:
            return True, None

        return False, f"weak/unrecognized classification (type={disaster_type or 'none'}, confidence={confidence})"

    def insert_news_article(self, article):
        """
        Insert news article into database.

        Only stores articles the ML step actually confirmed as
        disaster-related (see _is_disaster_related) - everything else is
        skipped before touching the database, same as a duplicate would be.

        NOTE on schema: news_articles has two generations of ML-result
        columns. The legacy ones (tags, disaster_types, locations_mentioned,
        relevance_score) are NOT read anywhere in index.php - confirmed by
        grepping the PHP dashboard, which reads disaster_type, disaster_score,
        urgency, severity_score, sentiment, sentiment_confidence,
        affected_areas, and key_numbers as top-level columns instead. This
        writes to the live columns the dashboard actually displays; the
        legacy columns are left at their schema defaults (NULL/0) since
        nothing reads them.
        """
        ml = article.get('ml_analysis') or {}
        sentiment_info = ml.get('sentiment') or {}

        is_disaster, reason = self._is_disaster_related(ml)
        if not is_disaster:
            logger.debug(f"Not storing '{article.get('title', '')[:60]}': {reason}")
            return False

        if not self.is_connected():
            return False

        try:
            cursor = self.connection.cursor()

            # Convert published_parsed to datetime if exists
            published_at = None
            if article.get('published_parsed'):
                published_at = datetime.fromtimestamp(article['published_parsed'])

            has_ml = bool(ml)

            cursor.execute("""
                INSERT IGNORE INTO news_articles 
                (article_id, source, source_url, reliability, title, summary, 
                 content, link, published_at, author,
                 disaster_type, disaster_score, urgency, severity_score,
                 sentiment, sentiment_confidence, affected_areas, key_numbers,
                 ml_processed, ml_processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                article.get('id'),
                article.get('source'),
                article.get('source_url'),
                article.get('reliability', 0.8),
                article.get('title', '')[:500],
                article.get('summary', '')[:1000],
                article.get('content', '')[:5000],
                article.get('link'),
                published_at,
                article.get('author', ''),
                ml.get('disaster_type'),
                ml.get('confidence'),
                ml.get('urgency', 'low'),
                ml.get('severity_score', 0),
                sentiment_info.get('sentiment'),
                sentiment_info.get('confidence'),
                json.dumps(ml.get('affected_areas', [])),
                json.dumps(ml.get('key_numbers', {})),
                1 if has_ml else 0,
                datetime.now() if has_ml else None
            ))

            self.connection.commit()
            inserted = cursor.rowcount > 0  # 0 rows affected = duplicate, ignored by INSERT IGNORE
            cursor.close()
            return inserted

        except Error as e:
            logger.error(f"Error inserting news article: {e}")
            try:
                self.connection.rollback()
            except Error:
                pass
            return False

    def insert_news_articles_bulk(self, articles):
        """
        Insert a list of articles, returns (inserted_count, skipped_count).

        skipped_count covers both DB-level skips (duplicates, connection/
        insert errors) and articles rejected by the disaster-relatedness
        storage gate in insert_news_article - i.e. this now also counts
        articles that were deliberately never written because the ML step
        didn't confirm them as disaster-related.
        """
        inserted = 0
        skipped = 0
        filtered_not_disaster = 0
        for article in articles:
            ml = article.get('ml_analysis') or {}
            is_disaster, _reason = self._is_disaster_related(ml)
            if not is_disaster:
                filtered_not_disaster += 1

            if self.insert_news_article(article):
                inserted += 1
            else:
                skipped += 1

        if filtered_not_disaster:
            logger.info(
                f"Storage gate filtered {filtered_not_disaster}/{len(articles)} "
                f"article(s) as not disaster-related - not written to DB"
            )

        return inserted, skipped

    def get_news_articles(self, limit=100, min_severity=0, days_back=7):
        """
        Get news articles from database, ranked by severity (the live,
        indexed column - relevance_score is a legacy field the dashboard
        never populates or reads, so filtering on it always returned
        everything or nothing depending on the threshold).
        """
        if not self.is_connected():
            return []

        try:
            cursor = self.connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT * FROM news_articles 
                WHERE severity_score >= %s 
                AND (published_at >= DATE_SUB(NOW(), INTERVAL %s DAY) OR published_at IS NULL)
                ORDER BY severity_score DESC, published_at DESC
                LIMIT %s
            """, (min_severity, days_back, limit))

            articles = cursor.fetchall()
            cursor.close()

            # Parse JSON fields
            for article in articles:
                if article.get('affected_areas'):
                    article['affected_areas'] = json.loads(article['affected_areas'])
                if article.get('key_numbers'):
                    article['key_numbers'] = json.loads(article['key_numbers'])

            return articles

        except Error as e:
            logger.error(f"Error getting news articles: {e}")
            return []

    def close(self):
        """Close the connection cleanly"""
        try:
            if self.connection is not None and self.connection.is_connected():
                self.connection.close()
                logger.info("MySQL connection closed")
        except Error as e:
            logger.error(f"Error closing MySQL connection: {e}")