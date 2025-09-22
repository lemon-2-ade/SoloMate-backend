"""
Advanced News Analysis AI Agent with MCP Integration

This module provides sophisticated AI-powered analysis of news articles
for safety assessment, with support for Model Context Protocol (MCP)
for enhanced structured data retrieval.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import re

from langchain.schema import Document, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain.callbacks import get_openai_callback
from pydantic import BaseModel, Field
from textblob import TextBlob

from app.core.config import settings
from app.services.news_scraping_agent import NewsScrapingAgent


class SafetyAnalysisResult(BaseModel):
    """Structured output for safety analysis"""
    threat_level: int = Field(description="Threat level 1-10", ge=1, le=10)
    concern_type: str = Field(description="Type of safety concern")
    specific_location: Optional[str] = Field(description="Specific location mentioned")
    timeframe: str = Field(description="When the incident occurred")
    affected_radius_km: float = Field(description="Estimated affected area in km", ge=0.1, le=100.0)
    traveler_recommendation: str = Field(description="Recommendation for travelers")
    confidence: float = Field(description="Analysis confidence", ge=0.0, le=1.0)
    urgency: str = Field(description="Urgency level: low, medium, high, critical")
    key_facts: List[str] = Field(description="Key facts extracted from the article")


class SentimentAnalysisResult(BaseModel):
    """Structured output for sentiment analysis"""
    polarity: float = Field(description="Sentiment polarity -1 to 1", ge=-1.0, le=1.0)
    subjectivity: float = Field(description="Subjectivity 0 to 1", ge=0.0, le=1.0)
    emotional_tone: str = Field(description="Overall emotional tone")
    safety_impact: str = Field(description="Impact on perceived safety")
    confidence: float = Field(description="Analysis confidence", ge=0.0, le=1.0)


class LocationExtractionResult(BaseModel):
    """Structured output for location extraction"""
    primary_location: Optional[str] = Field(description="Main location mentioned")
    secondary_locations: List[str] = Field(description="Additional locations")
    coordinates: Optional[Dict[str, float]] = Field(description="Lat/lng if extractable")
    location_type: str = Field(description="Type of location: city, district, landmark, etc.")
    confidence: float = Field(description="Extraction confidence", ge=0.0, le=1.0)


class NewsAnalysisAI:
    """Advanced AI agent for comprehensive news analysis"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            temperature=0.1,
            model="gpt-3.5-turbo-16k",  # Use 16k context for longer articles
            api_key=settings.OPENAI_API_KEY
        )
        
        self.safety_parser = PydanticOutputParser(pydantic_object=SafetyAnalysisResult)
        self.sentiment_parser = PydanticOutputParser(pydantic_object=SentimentAnalysisResult)
        self.location_parser = PydanticOutputParser(pydantic_object=LocationExtractionResult)
        
        # MCP client setup (if available)
        self.mcp_client = self._setup_mcp_client()
        
        # Safety-related patterns for enhanced detection
        self.safety_patterns = {
            'crime_indicators': [
                r'\b(?:murder|homicide|killing)\b',
                r'\b(?:robbery|mugging|theft|burglary)\b',
                r'\b(?:assault|attack|violence)\b',
                r'\b(?:rape|sexual assault)\b',
                r'\b(?:fraud|scam|con)\b',
                r'\b(?:drug dealing|trafficking)\b'
            ],
            'safety_indicators': [
                r'\b(?:police patrol|security increase)\b',
                r'\b(?:safety measure|security camera)\b',
                r'\b(?:well lit|good lighting)\b',
                r'\b(?:emergency services|first aid)\b'
            ],
            'location_indicators': [
                r'\b(?:downtown|city center|tourist area)\b',
                r'\b(?:metro|subway|train station)\b',
                r'\b(?:airport|bus terminal)\b',
                r'\b(?:hotel|accommodation)\b',
                r'\b(?:restaurant|shopping)\b'
            ]
        }

    def _setup_mcp_client(self):
        """Setup MCP client for structured data retrieval"""
        try:
            # Import MCP client if available
            # from mcp import Client
            # return Client(server_url=settings.MCP_SERVER_URL)
            return None  # Placeholder for now
        except ImportError:
            logging.info("MCP not available, using direct scraping only")
            return None

    async def analyze_article_comprehensive(
        self,
        article: Dict,
        target_city: str,
        target_country: str,
        target_coordinates: Tuple[float, float]
    ) -> Dict:
        """
        Perform comprehensive analysis of a news article
        
        Args:
            article: Article data from scraping
            target_city: Target city name
            target_country: Target country
            target_coordinates: (latitude, longitude) tuple
            
        Returns:
            Comprehensive analysis results
        """
        
        # Extract article text
        text_content = self._extract_article_text(article)
        
        if not text_content or len(text_content.strip()) < 50:
            return self._create_minimal_analysis("Insufficient content")
        
        # Parallel analysis tasks
        tasks = [
            self._analyze_safety_threats(text_content, target_city, target_country),
            self._analyze_sentiment_detailed(text_content),
            self._extract_locations(text_content, target_coordinates),
            self._calculate_relevance_score(text_content, target_city, target_country),
            self._extract_temporal_info(text_content),
        ]
        
        # Execute analysis tasks
        try:
            with get_openai_callback() as cb:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                safety_analysis = results[0] if not isinstance(results[0], Exception) else None
                sentiment_analysis = results[1] if not isinstance(results[1], Exception) else None
                location_analysis = results[2] if not isinstance(results[2], Exception) else None
                relevance_score = results[3] if not isinstance(results[3], Exception) else 0.0
                temporal_info = results[4] if not isinstance(results[4], Exception) else {}
                
                # Log token usage
                logging.info(f"OpenAI tokens used: {cb.total_tokens}")
                
        except Exception as e:
            logging.error(f"Analysis failed: {e}")
            return self._create_minimal_analysis(f"Analysis error: {e}")
        
        # Combine results
        combined_analysis = self._combine_analysis_results(
            article,
            safety_analysis,
            sentiment_analysis,
            location_analysis,
            relevance_score,
            temporal_info
        )
        
        return combined_analysis

    def _extract_article_text(self, article: Dict) -> str:
        """Extract and clean text content from article"""
        text_parts = []
        
        if article.get('title'):
            text_parts.append(article['title'])
        
        if article.get('summary'):
            text_parts.append(article['summary'])
        
        if article.get('content'):
            # Clean HTML/markup if present
            content = re.sub(r'<[^>]+>', '', article['content'])
            text_parts.append(content)
        
        return ' '.join(text_parts).strip()

    async def _analyze_safety_threats(
        self,
        text: str,
        target_city: str,
        target_country: str
    ) -> Optional[SafetyAnalysisResult]:
        """Analyze text for safety threats using AI"""
        
        prompt = ChatPromptTemplate.from_template("""
        You are an expert safety analyst. Analyze the following news article for safety and security threats.

        Target Location: {target_city}, {target_country}
        Article Text: {text}

        Focus on:
        1. Any criminal activity, violence, or security incidents
        2. Natural disasters or health emergencies
        3. Infrastructure problems affecting safety
        4. Positive safety developments (police presence, security measures)
        5. Tourist-specific risks or recommendations

        Assess the threat level on a scale of 1-10:
        - 1-2: Very safe, positive safety news
        - 3-4: Minor concerns, normal precautions
        - 5-6: Moderate risk, increased awareness needed
        - 7-8: High risk, significant safety concerns
        - 9-10: Extreme danger, avoid area

        {format_instructions}
        """)

        try:
            formatted_prompt = prompt.format(
                target_city=target_city,
                target_country=target_country,
                text=text[:8000],  # Limit text length
                format_instructions=self.safety_parser.get_format_instructions()
            )
            
            response = await self.llm.ainvoke([HumanMessage(content=formatted_prompt)])
            result = self.safety_parser.parse(response.content)
            return result
            
        except Exception as e:
            logging.warning(f"Safety analysis failed: {e}")
            return None

    async def _analyze_sentiment_detailed(self, text: str) -> Optional[SentimentAnalysisResult]:
        """Perform detailed sentiment analysis"""
        
        # Quick TextBlob analysis
        blob = TextBlob(text)
        basic_sentiment = blob.sentiment
        
        prompt = ChatPromptTemplate.from_template("""
        Analyze the emotional tone and sentiment of this news article, particularly as it relates to safety perception.

        Article Text: {text}

        Consider:
        1. Overall emotional tone (fearful, reassuring, neutral, alarming)
        2. How this news might affect a traveler's sense of safety
        3. Whether the tone is objective reporting or sensationalized
        4. Impact on tourism and visitor confidence

        Basic sentiment scores:
        - Polarity: {polarity} (TextBlob analysis)
        - Subjectivity: {subjectivity} (TextBlob analysis)

        {format_instructions}
        """)

        try:
            formatted_prompt = prompt.format(
                text=text[:6000],
                polarity=basic_sentiment.polarity,
                subjectivity=basic_sentiment.subjectivity,
                format_instructions=self.sentiment_parser.get_format_instructions()
            )
            
            response = await self.llm.ainvoke([HumanMessage(content=formatted_prompt)])
            result = self.sentiment_parser.parse(response.content)
            return result
            
        except Exception as e:
            logging.warning(f"Sentiment analysis failed: {e}")
            return None

    async def _extract_locations(
        self,
        text: str,
        target_coordinates: Tuple[float, float]
    ) -> Optional[LocationExtractionResult]:
        """Extract and geocode locations mentioned in the article"""
        
        prompt = ChatPromptTemplate.from_template("""
        Extract all locations mentioned in this news article. Focus on specific places, neighborhoods, landmarks, or areas.

        Article Text: {text}

        Target coordinates for reference: {target_lat}, {target_lng}

        Extract:
        1. The primary location where the event occurred
        2. Any secondary locations mentioned
        3. Types of locations (residential area, tourist district, downtown, etc.)
        4. Try to estimate coordinates if you recognize specific landmarks

        {format_instructions}
        """)

        try:
            formatted_prompt = prompt.format(
                text=text[:6000],
                target_lat=target_coordinates[0],
                target_lng=target_coordinates[1],
                format_instructions=self.location_parser.get_format_instructions()
            )
            
            response = await self.llm.ainvoke([HumanMessage(content=formatted_prompt)])
            result = self.location_parser.parse(response.content)
            return result
            
        except Exception as e:
            logging.warning(f"Location extraction failed: {e}")
            return None

    async def _calculate_relevance_score(
        self,
        text: str,
        target_city: str,
        target_country: str
    ) -> float:
        """Calculate how relevant this article is to the target location"""
        
        text_lower = text.lower()
        city_lower = target_city.lower()
        country_lower = target_country.lower()
        
        relevance_score = 0.0
        
        # Direct mentions
        if city_lower in text_lower:
            relevance_score += 0.5
        if country_lower in text_lower:
            relevance_score += 0.3
        
        # Pattern-based relevance
        for pattern_type, patterns in self.safety_patterns.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
                if pattern_type == 'safety_indicators':
                    relevance_score += matches * 0.1
                elif pattern_type == 'crime_indicators':
                    relevance_score += matches * 0.15
                elif pattern_type == 'location_indicators':
                    relevance_score += matches * 0.05
        
        return min(1.0, relevance_score)

    async def _extract_temporal_info(self, text: str) -> Dict:
        """Extract temporal information from the article"""
        
        # Common time patterns
        time_patterns = [
            r'\b(?:today|yesterday|this morning|tonight|this evening)\b',
            r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
            r'\b\d{1,2}:\d{2}\s*(?:am|pm)\b',
            r'\b\d{1,2}/\d{1,2}/\d{4}\b'
        ]
        
        temporal_mentions = []
        for pattern in time_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            temporal_mentions.extend(matches)
        
        return {
            'temporal_mentions': temporal_mentions,
            'has_recent_time_reference': any(
                word in text.lower() 
                for word in ['today', 'yesterday', 'this morning', 'tonight', 'breaking']
            ),
            'urgency_indicators': re.findall(
                r'\b(?:breaking|urgent|alert|emergency|immediate)\b',
                text,
                re.IGNORECASE
            )
        }

    def _combine_analysis_results(
        self,
        original_article: Dict,
        safety_analysis: Optional[SafetyAnalysisResult],
        sentiment_analysis: Optional[SentimentAnalysisResult],
        location_analysis: Optional[LocationExtractionResult],
        relevance_score: float,
        temporal_info: Dict
    ) -> Dict:
        """Combine all analysis results into a comprehensive output"""
        
        # Default values
        threat_level = 5
        confidence = 0.0
        concern_type = "UNKNOWN"
        
        if safety_analysis:
            threat_level = safety_analysis.threat_level
            confidence = safety_analysis.confidence
            concern_type = safety_analysis.concern_type.upper()
        
        sentiment_scores = {
            'polarity': 0.0,
            'subjectivity': 0.0,
            'emotional_tone': 'neutral'
        }
        
        if sentiment_analysis:
            sentiment_scores = {
                'polarity': sentiment_analysis.polarity,
                'subjectivity': sentiment_analysis.subjectivity,
                'emotional_tone': sentiment_analysis.emotional_tone
            }
        
        return {
            'article_id': original_article.get('id'),
            'analysis_timestamp': datetime.now().isoformat(),
            
            # Safety metrics
            'threat_level': threat_level,
            'concern_type': concern_type,
            'confidence': confidence,
            'relevance_score': relevance_score,
            
            # Sentiment metrics
            'sentiment': sentiment_scores,
            
            # Location data
            'location_analysis': location_analysis.dict() if location_analysis else None,
            
            # Temporal data
            'temporal_info': temporal_info,
            
            # Safety impact calculation
            'safety_impact_factor': self._calculate_safety_impact_factor(
                threat_level, relevance_score, confidence, sentiment_scores['polarity']
            ),
            
            # Metadata
            'processing_successful': True,
            'ai_model_used': 'gpt-3.5-turbo-16k'
        }

    def _calculate_safety_impact_factor(
        self,
        threat_level: int,
        relevance_score: float,
        confidence: float,
        sentiment_polarity: float
    ) -> float:
        """
        Calculate overall safety impact factor for use in safety index
        
        Returns value between -1.0 (very negative impact) and 1.0 (very positive impact)
        """
        
        # Convert threat level to impact (inverse relationship)
        # Threat 1-3 = positive impact, 4-6 = neutral, 7-10 = negative impact
        if threat_level <= 3:
            base_impact = (4 - threat_level) / 3 * 0.5  # 0.17 to 0.5
        elif threat_level <= 6:
            base_impact = 0.0  # Neutral
        else:
            base_impact = -(threat_level - 6) / 4 * 1.0  # -0.25 to -1.0
        
        # Weight by relevance and confidence
        weighted_impact = base_impact * relevance_score * confidence
        
        # Adjust for sentiment
        sentiment_adjustment = sentiment_polarity * 0.2  # Max ±0.2 adjustment
        
        final_impact = weighted_impact + sentiment_adjustment
        
        # Clamp to [-1.0, 1.0]
        return max(-1.0, min(1.0, final_impact))

    def _create_minimal_analysis(self, reason: str) -> Dict:
        """Create minimal analysis result for failed cases"""
        return {
            'analysis_timestamp': datetime.now().isoformat(),
            'threat_level': 5,  # Neutral
            'concern_type': 'UNKNOWN',
            'confidence': 0.0,
            'relevance_score': 0.0,
            'sentiment': {'polarity': 0.0, 'subjectivity': 0.0, 'emotional_tone': 'neutral'},
            'location_analysis': None,
            'temporal_info': {},
            'safety_impact_factor': 0.0,
            'processing_successful': False,
            'failure_reason': reason
        }


# Singleton instance
news_analysis_ai = NewsAnalysisAI()