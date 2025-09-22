"""
News Scraping Agent for Safety Index Enhancement

This module provides comprehensive news scraping capabilities to enhance
location safety assessment using real-time news data and sentiment analysis.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

import aiohttp
import feedparser
import nltk
from bs4 import BeautifulSoup
from textblob import TextBlob
from langchain.schema import Document
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from geopy.distance import geodesic

from app.core.config import settings


# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')


class NewsScrapingAgent:
    """Advanced news scraping agent for location-based safety intelligence"""
    
    def __init__(self):
        self.session = None
        self.llm = ChatOpenAI(
            temperature=0.1,
            model="gpt-3.5-turbo",
            api_key=settings.OPENAI_API_KEY
        )
        
        # Safety-related keywords for filtering news
        self.safety_keywords = {
            'crime': ['crime', 'theft', 'robbery', 'murder', 'assault', 'burglary', 'vandalism'],
            'violence': ['violence', 'attack', 'shooting', 'stabbing', 'riot', 'protest'],
            'terrorism': ['terrorism', 'terrorist', 'bomb', 'explosion', 'threat'],
            'traffic': ['accident', 'crash', 'traffic', 'collision', 'pedestrian'],
            'natural_disaster': ['earthquake', 'flood', 'storm', 'hurricane', 'wildfire'],
            'health': ['outbreak', 'disease', 'epidemic', 'contamination', 'poisoning'],
            'positive': ['safe', 'security', 'patrol', 'improvement', 'renovation', 'festival'],
            'infrastructure': ['construction', 'roadwork', 'closure', 'maintenance']
        }
        
        # Major news sources with RSS feeds
        self.news_sources = {
            'bbc': 'http://feeds.bbci.co.uk/news/world/rss.xml',
            'reuters': 'http://feeds.reuters.com/Reuters/worldNews',
            'cnn': 'http://rss.cnn.com/rss/edition.rss',
            'guardian': 'https://www.theguardian.com/world/rss',
            'ap_news': 'https://feeds.apnews.com/rss/apf-topnews.xml'
        }
        
        # Location-specific news APIs
        self.location_apis = {
            'newsapi': 'https://newsapi.org/v2/everything',
            'gdelt': 'https://api.gdeltproject.org/api/v2/geo/geo'
        }

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'SoloMate-NewsAgent/1.0 (Safety Research Bot)'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def scrape_location_news(
        self,
        latitude: float,
        longitude: float,
        city_name: str,
        country: str,
        radius_km: float = 50,
        days_back: int = 7
    ) -> List[Dict]:
        """
        Scrape news articles relevant to a specific location
        
        Args:
            latitude: Location latitude
            longitude: Location longitude
            city_name: Name of the city
            country: Country name
            radius_km: Search radius in kilometers
            days_back: How many days back to search
            
        Returns:
            List of processed news articles with safety scores
        """
        logging.info(f"Scraping news for {city_name}, {country} ({latitude}, {longitude})")
        
        all_articles = []
        
        # Scrape from RSS feeds
        rss_articles = await self._scrape_rss_feeds(city_name, country)
        all_articles.extend(rss_articles)
        
        # Scrape using NewsAPI if available
        if hasattr(settings, 'NEWSAPI_KEY') and settings.NEWSAPI_KEY:
            newsapi_articles = await self._scrape_newsapi(
                city_name, country, days_back
            )
            all_articles.extend(newsapi_articles)
        
        # Scrape local news websites
        local_articles = await self._scrape_local_news(
            city_name, country, latitude, longitude
        )
        all_articles.extend(local_articles)
        
        # Filter and analyze articles for safety relevance
        safety_articles = await self._analyze_safety_relevance(
            all_articles, city_name, latitude, longitude, radius_km
        )
        
        logging.info(f"Found {len(safety_articles)} safety-relevant articles")
        return safety_articles

    async def _scrape_rss_feeds(self, city_name: str, country: str) -> List[Dict]:
        """Scrape major news RSS feeds for location mentions"""
        articles = []
        search_terms = [city_name.lower(), country.lower()]
        
        for source_name, rss_url in self.news_sources.items():
            try:
                async with self.session.get(rss_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        feed = feedparser.parse(content)
                        
                        for entry in feed.entries[:20]:  # Limit to recent articles
                            # Check if article mentions our location
                            title_lower = entry.title.lower()
                            summary_lower = getattr(entry, 'summary', '').lower()
                            
                            location_mentioned = any(
                                term in title_lower or term in summary_lower
                                for term in search_terms
                            )
                            
                            if location_mentioned:
                                articles.append({
                                    'title': entry.title,
                                    'summary': getattr(entry, 'summary', ''),
                                    'url': entry.link,
                                    'published': getattr(entry, 'published', ''),
                                    'source': source_name,
                                    'type': 'rss'
                                })
                                
            except Exception as e:
                logging.warning(f"Failed to scrape {source_name}: {e}")
                continue
        
        return articles

    async def _scrape_newsapi(self, city_name: str, country: str, days_back: int) -> List[Dict]:
        """Scrape using NewsAPI for more targeted location news"""
        articles = []
        
        # Construct search query
        query = f'"{city_name}" AND ("{country}" OR "crime" OR "safety" OR "incident")'
        from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        params = {
            'q': query,
            'from': from_date,
            'sortBy': 'publishedAt',
            'language': 'en',
            'pageSize': 50,
            'apiKey': getattr(settings, 'NEWSAPI_KEY', '')
        }
        
        try:
            async with self.session.get(self.location_apis['newsapi'], params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for article in data.get('articles', []):
                        articles.append({
                            'title': article.get('title', ''),
                            'summary': article.get('description', ''),
                            'content': article.get('content', ''),
                            'url': article.get('url', ''),
                            'published': article.get('publishedAt', ''),
                            'source': article.get('source', {}).get('name', 'newsapi'),
                            'type': 'newsapi'
                        })
                        
        except Exception as e:
            logging.warning(f"NewsAPI scraping failed: {e}")
        
        return articles

    async def _scrape_local_news(
        self, 
        city_name: str, 
        country: str, 
        latitude: float, 
        longitude: float
    ) -> List[Dict]:
        """Scrape local news websites and regional sources"""
        articles = []
        
        # Common local news URL patterns
        search_queries = [
            f"{city_name} news crime",
            f"{city_name} safety incidents",
            f"{city_name} police reports",
            f"{country} {city_name} security"
        ]
        
        # Use web search to find local news
        for query in search_queries:
            try:
                # This would typically use a search API like Google Custom Search
                # For now, we'll use a simple approach
                encoded_query = quote_plus(f"site:news OR {query}")
                
                # Note: In production, you'd want to use proper search APIs
                # This is a simplified implementation
                
            except Exception as e:
                logging.warning(f"Local news scraping failed for {query}: {e}")
                continue
        
        return articles

    async def _analyze_safety_relevance(
        self,
        articles: List[Dict],
        city_name: str,
        latitude: float,
        longitude: float,
        radius_km: float
    ) -> List[Dict]:
        """Analyze articles for safety relevance and sentiment"""
        
        safety_articles = []
        
        for article in articles:
            try:
                # Extract text for analysis
                text_content = f"{article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}"
                
                # Check for safety keywords
                safety_score = self._calculate_safety_keyword_score(text_content)
                
                if safety_score > 0.3:  # Threshold for safety relevance
                    # Perform sentiment analysis
                    sentiment = self._analyze_sentiment(text_content)
                    
                    # Use AI to extract location and safety details
                    ai_analysis = await self._ai_analyze_article(article, city_name)
                    
                    enhanced_article = {
                        **article,
                        'safety_score': safety_score,
                        'sentiment': sentiment,
                        'ai_analysis': ai_analysis,
                        'processed_at': datetime.now().isoformat(),
                        'location': {
                            'city': city_name,
                            'latitude': latitude,
                            'longitude': longitude
                        }
                    }
                    
                    safety_articles.append(enhanced_article)
                    
            except Exception as e:
                logging.warning(f"Failed to analyze article: {e}")
                continue
        
        return safety_articles

    def _calculate_safety_keyword_score(self, text: str) -> float:
        """Calculate safety relevance score based on keywords"""
        text_lower = text.lower()
        total_score = 0
        total_words = len(text.split())
        
        if total_words == 0:
            return 0
        
        for category, keywords in self.safety_keywords.items():
            category_score = 0
            
            for keyword in keywords:
                count = text_lower.count(keyword)
                if category == 'positive':
                    # Positive safety keywords increase safety
                    category_score += count * 0.1
                else:
                    # Negative safety keywords decrease safety
                    category_score += count * 0.2
            
            total_score += category_score
        
        # Normalize by text length
        return min(1.0, total_score / total_words * 100)

    def _analyze_sentiment(self, text: str) -> Dict:
        """Analyze sentiment of news article"""
        try:
            blob = TextBlob(text)
            sentiment = blob.sentiment
            
            return {
                'polarity': sentiment.polarity,  # -1 (negative) to 1 (positive)
                'subjectivity': sentiment.subjectivity,  # 0 (objective) to 1 (subjective)
                'classification': self._classify_sentiment(sentiment.polarity)
            }
        except Exception as e:
            logging.warning(f"Sentiment analysis failed: {e}")
            return {'polarity': 0, 'subjectivity': 0, 'classification': 'neutral'}

    def _classify_sentiment(self, polarity: float) -> str:
        """Classify sentiment polarity into categories"""
        if polarity > 0.3:
            return 'positive'
        elif polarity < -0.3:
            return 'negative'
        else:
            return 'neutral'

    async def _ai_analyze_article(self, article: Dict, city_name: str) -> Dict:
        """Use AI to analyze article for safety insights"""
        
        prompt_template = ChatPromptTemplate.from_template("""
        Analyze the following news article for safety and security information related to {city_name}.

        Article Title: {title}
        Article Summary: {summary}

        Please provide:
        1. Safety threat level (1-10, where 10 is most dangerous)
        2. Type of safety concern (crime, natural disaster, infrastructure, etc.)
        3. Specific location mentioned (if any)
        4. Timeframe of the incident
        5. Recommendation for travelers

        Respond in JSON format:
        {{
            "threat_level": <number>,
            "concern_type": "<string>",
            "specific_location": "<string or null>",
            "timeframe": "<string>",
            "traveler_recommendation": "<string>",
            "confidence": <float 0-1>
        }}
        """)

        try:
            response = await self.llm.ainvoke(
                prompt_template.format_messages(
                    city_name=city_name,
                    title=article.get('title', ''),
                    summary=article.get('summary', '')
                )
            )
            
            # Parse JSON response
            import json
            analysis = json.loads(response.content)
            return analysis
            
        except Exception as e:
            logging.warning(f"AI analysis failed: {e}")
            return {
                "threat_level": 5,
                "concern_type": "unknown",
                "specific_location": None,
                "timeframe": "unknown",
                "traveler_recommendation": "Exercise normal caution",
                "confidence": 0.0
            }

    async def calculate_news_safety_factor(
        self,
        articles: List[Dict],
        days_weight: int = 7
    ) -> Dict:
        """
        Calculate overall safety factor from news articles
        
        Returns:
            Dict with safety metrics derived from news analysis
        """
        if not articles:
            return {
                'news_safety_factor': 1.0,  # Neutral if no news
                'confidence': 0.0,
                'article_count': 0,
                'avg_threat_level': 5.0,
                'sentiment_score': 0.0
            }
        
        # Calculate weighted scores
        total_threat = 0
        total_sentiment = 0
        total_confidence = 0
        recent_articles = 0
        
        cutoff_date = datetime.now() - timedelta(days=days_weight)
        
        for article in articles:
            try:
                # Weight recent articles more heavily
                published_date = datetime.fromisoformat(
                    article.get('processed_at', datetime.now().isoformat())
                )
                
                if published_date > cutoff_date:
                    weight = 1.0
                    recent_articles += 1
                else:
                    # Decay weight for older articles
                    days_old = (datetime.now() - published_date).days
                    weight = max(0.1, 1.0 - (days_old / 30))  # 30-day decay
                
                # Accumulate weighted scores
                ai_analysis = article.get('ai_analysis', {})
                threat_level = ai_analysis.get('threat_level', 5)
                confidence = ai_analysis.get('confidence', 0.5)
                sentiment = article.get('sentiment', {}).get('polarity', 0)
                
                total_threat += threat_level * weight * confidence
                total_sentiment += sentiment * weight
                total_confidence += confidence * weight
                
            except Exception as e:
                logging.warning(f"Error processing article for safety factor: {e}")
                continue
        
        # Calculate averages
        article_count = len(articles)
        avg_threat = total_threat / max(1, total_confidence)
        avg_sentiment = total_sentiment / max(1, article_count)
        avg_confidence = total_confidence / max(1, article_count)
        
        # Convert threat level to safety factor (inverse relationship)
        # Threat level 1-3: Very safe (factor 1.0-0.9)
        # Threat level 4-6: Moderate (factor 0.9-0.7)
        # Threat level 7-10: Dangerous (factor 0.7-0.3)
        
        if avg_threat <= 3:
            news_safety_factor = 1.0 - (avg_threat - 1) * 0.05  # 1.0 to 0.9
        elif avg_threat <= 6:
            news_safety_factor = 0.9 - (avg_threat - 3) * 0.067  # 0.9 to 0.7
        else:
            news_safety_factor = 0.7 - (avg_threat - 7) * 0.1  # 0.7 to 0.3
        
        # Adjust for sentiment (positive news can offset negative threat)
        sentiment_adjustment = avg_sentiment * 0.1  # Max ±0.1 adjustment
        news_safety_factor = max(0.1, min(1.0, news_safety_factor + sentiment_adjustment))
        
        return {
            'news_safety_factor': round(news_safety_factor, 3),
            'confidence': round(avg_confidence, 3),
            'article_count': article_count,
            'recent_article_count': recent_articles,
            'avg_threat_level': round(avg_threat, 2),
            'sentiment_score': round(avg_sentiment, 3),
            'analysis_date': datetime.now().isoformat()
        }


# Singleton instance for use across the application
news_agent = NewsScrapingAgent()