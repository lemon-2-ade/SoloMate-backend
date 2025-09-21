from typing import Dict, List, Any, Optional, Tuple
import googlemaps
import requests
from datetime import datetime
import json

from app.core.config import settings

class GoogleMapsService:
    """Google Maps and Places API integration for SoloMate"""
    
    def __init__(self):
        if settings.GOOGLE_MAPS_API_KEY:
            self.gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
        else:
            self.gmaps = None
    
    def geocode_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Convert address to latitude/longitude coordinates"""
        if not self.gmaps:
            return None
        
        try:
            geocode_result = self.gmaps.geocode(address)
            if geocode_result:
                location = geocode_result[0]['geometry']['location']
                return {
                    "latitude": location['lat'],
                    "longitude": location['lng'],
                    "formatted_address": geocode_result[0]['formatted_address'],
                    "place_id": geocode_result[0].get('place_id')
                }
        except Exception as e:
            print(f"Geocoding error: {e}")
        
        return None
    
    def reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Convert coordinates to address"""
        if not self.gmaps:
            return None
        
        try:
            reverse_geocode_result = self.gmaps.reverse_geocode((latitude, longitude))
            if reverse_geocode_result:
                return {
                    "formatted_address": reverse_geocode_result[0]['formatted_address'],
                    "address_components": reverse_geocode_result[0]['address_components'],
                    "place_id": reverse_geocode_result[0].get('place_id')
                }
        except Exception as e:
            print(f"Reverse geocoding error: {e}")
        
        return None
    
    def find_nearby_places(
        self, 
        latitude: float, 
        longitude: float, 
        place_type: str = "tourist_attraction",
        radius: int = 5000,
        keyword: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find nearby places of interest"""
        if not self.gmaps:
            return []
        
        try:
            places_result = self.gmaps.places_nearby(
                location=(latitude, longitude),
                radius=radius,
                type=place_type,
                keyword=keyword
            )
            
            places = []
            for place in places_result.get('results', []):
                place_info = {
                    "name": place.get('name'),
                    "place_id": place.get('place_id'),
                    "types": place.get('types', []),
                    "rating": place.get('rating'),
                    "user_ratings_total": place.get('user_ratings_total'),
                    "vicinity": place.get('vicinity'),
                    "location": {
                        "latitude": place['geometry']['location']['lat'],
                        "longitude": place['geometry']['location']['lng']
                    },
                    "photos": []
                }
                
                # Get photo references
                if place.get('photos'):
                    for photo in place['photos'][:3]:  # Limit to 3 photos
                        place_info["photos"].append({
                            "photo_reference": photo.get('photo_reference'),
                            "width": photo.get('width'),
                            "height": photo.get('height')
                        })
                
                places.append(place_info)
            
            return places
        
        except Exception as e:
            print(f"Places search error: {e}")
            return []
    
    def get_place_details(self, place_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific place"""
        if not self.gmaps:
            return None
        
        try:
            place_details = self.gmaps.place(
                place_id=place_id,
                fields=[
                    'name', 'formatted_address', 'international_phone_number',
                    'website', 'rating', 'user_ratings_total', 'reviews',
                    'opening_hours', 'photos', 'geometry', 'types',
                    'price_level', 'permanently_closed'
                ]
            )
            
            result = place_details.get('result', {})
            
            place_info = {
                "name": result.get('name'),
                "address": result.get('formatted_address'),
                "phone": result.get('international_phone_number'),
                "website": result.get('website'),
                "rating": result.get('rating'),
                "user_ratings_total": result.get('user_ratings_total'),
                "price_level": result.get('price_level'),
                "types": result.get('types', []),
                "location": {
                    "latitude": result['geometry']['location']['lat'],
                    "longitude": result['geometry']['location']['lng']
                } if result.get('geometry') else None,
                "opening_hours": {},
                "reviews": [],
                "photos": []
            }
            
            # Parse opening hours
            if result.get('opening_hours'):
                place_info["opening_hours"] = {
                    "open_now": result['opening_hours'].get('open_now'),
                    "weekday_text": result['opening_hours'].get('weekday_text', [])
                }
            
            # Parse reviews
            if result.get('reviews'):
                for review in result['reviews'][:5]:  # Limit to 5 reviews
                    place_info["reviews"].append({
                        "author_name": review.get('author_name'),
                        "rating": review.get('rating'),
                        "text": review.get('text'),
                        "time": review.get('time')
                    })
            
            # Parse photos
            if result.get('photos'):
                for photo in result['photos'][:5]:  # Limit to 5 photos
                    place_info["photos"].append({
                        "photo_reference": photo.get('photo_reference'),
                        "width": photo.get('width'),
                        "height": photo.get('height')
                    })
            
            return place_info
        
        except Exception as e:
            print(f"Place details error: {e}")
            return None
    
    def get_photo_url(self, photo_reference: str, max_width: int = 400) -> str:
        """Generate Google Places photo URL"""
        if not settings.GOOGLE_MAPS_API_KEY:
            return ""
        
        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={max_width}&photo_reference={photo_reference}&key={settings.GOOGLE_MAPS_API_KEY}"
    
    def calculate_route(
        self, 
        origin: Tuple[float, float], 
        destination: Tuple[float, float],
        waypoints: Optional[List[Tuple[float, float]]] = None,
        mode: str = "walking"
    ) -> Optional[Dict[str, Any]]:
        """Calculate route between points"""
        if not self.gmaps:
            return None
        
        try:
            directions_result = self.gmaps.directions(
                origin=origin,
                destination=destination,
                waypoints=waypoints,
                mode=mode,
                optimize_waypoints=True
            )
            
            if directions_result:
                route = directions_result[0]
                
                # Extract route information
                route_info = {
                    "distance": route['legs'][0]['distance']['text'],
                    "duration": route['legs'][0]['duration']['text'],
                    "start_address": route['legs'][0]['start_address'],
                    "end_address": route['legs'][0]['end_address'],
                    "steps": [],
                    "overview_polyline": route['overview_polyline']['points']
                }
                
                # Extract steps
                for step in route['legs'][0]['steps']:
                    route_info["steps"].append({
                        "instruction": step['html_instructions'],
                        "distance": step['distance']['text'],
                        "duration": step['duration']['text'],
                        "start_location": step['start_location'],
                        "end_location": step['end_location']
                    })
                
                return route_info
        
        except Exception as e:
            print(f"Directions error: {e}")
        
        return None
    
    def find_quest_locations(
        self, 
        center_lat: float, 
        center_lon: float, 
        quest_type: str,
        radius: int = 10000
    ) -> List[Dict[str, Any]]:
        """Find potential quest locations based on quest type"""
        
        # Map quest types to Google Places types
        type_mapping = {
            "HERITAGE": ["museum", "historical", "monument"],
            "CULTURE": ["museum", "art_gallery", "theater", "cultural_center"],
            "LANDMARK": ["tourist_attraction", "point_of_interest"],
            "HIDDEN_GEMS": ["local_government_office", "park", "natural_feature"],
            "SAFETY_CHALLENGE": ["police", "hospital", "fire_station"],
            "COMMUNITY_PICKS": ["restaurant", "cafe", "shopping_mall"]
        }
        
        search_types = type_mapping.get(quest_type, ["tourist_attraction"])
        all_places = []
        
        for place_type in search_types:
            places = self.find_nearby_places(
                center_lat, center_lon, place_type, radius
            )
            all_places.extend(places)
        
        # Remove duplicates based on place_id
        unique_places = {}
        for place in all_places:
            if place['place_id'] not in unique_places:
                unique_places[place['place_id']] = place
        
        return list(unique_places.values())
    
    def get_travel_time_matrix(
        self,
        origins: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
        mode: str = "walking"
    ) -> Optional[Dict[str, Any]]:
        """Get travel time matrix between multiple points"""
        if not self.gmaps:
            return None
        
        try:
            matrix = self.gmaps.distance_matrix(
                origins=origins,
                destinations=destinations,
                mode=mode,
                units="metric"
            )
            
            return {
                "origin_addresses": matrix['origin_addresses'],
                "destination_addresses": matrix['destination_addresses'],
                "rows": matrix['rows']
            }
        
        except Exception as e:
            print(f"Distance matrix error: {e}")
            return None
    
    def search_places_text(
        self, 
        query: str, 
        location: Optional[Tuple[float, float]] = None,
        radius: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search for places using text query"""
        if not self.gmaps:
            return []
        
        try:
            places_result = self.gmaps.places(
                query=query,
                location=location,
                radius=radius
            )
            
            places = []
            for place in places_result.get('results', []):
                place_info = {
                    "name": place.get('name'),
                    "place_id": place.get('place_id'),
                    "formatted_address": place.get('formatted_address'),
                    "types": place.get('types', []),
                    "rating": place.get('rating'),
                    "location": {
                        "latitude": place['geometry']['location']['lat'],
                        "longitude": place['geometry']['location']['lng']
                    }
                }
                places.append(place_info)
            
            return places
        
        except Exception as e:
            print(f"Text search error: {e}")
            return []

# Singleton instance
google_maps_service = GoogleMapsService()

def create_static_map_url(
    center_lat: float,
    center_lon: float,
    zoom: int = 15,
    size: str = "400x400",
    markers: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Create Google Static Maps URL"""
    if not settings.GOOGLE_MAPS_API_KEY:
        return ""
    
    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    params = [
        f"center={center_lat},{center_lon}",
        f"zoom={zoom}",
        f"size={size}",
        f"key={settings.GOOGLE_MAPS_API_KEY}"
    ]
    
    if markers:
        for marker in markers:
            marker_str = f"markers=color:{marker.get('color', 'red')}|"
            marker_str += f"{marker['lat']},{marker['lng']}"
            if marker.get('label'):
                marker_str += f"|label:{marker['label']}"
            params.append(marker_str)
    
    return f"{base_url}?" + "&".join(params)

def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate latitude and longitude values"""
    return (-90 <= latitude <= 90) and (-180 <= longitude <= 180)