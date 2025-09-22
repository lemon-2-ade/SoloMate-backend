from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.schemas import (
    EmergencyContactCreate,
    EmergencyContactUpdate, 
    EmergencyContactResponse,
    SosAlertCreate,
    SosAlertResponse,
    MessageResponse
)
from prisma.models import User, EmergencyContact, SosAlert
import httpx
import os
from datetime import datetime

router = APIRouter(prefix="/emergency-contacts", tags=["Emergency Contacts"])

@router.post("/", response_model=EmergencyContactResponse, status_code=status.HTTP_201_CREATED)
async def create_emergency_contact(
    contact_data: EmergencyContactCreate,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new emergency contact for the current user."""
    try:
        # If this contact is marked as primary, unset all other primary contacts
        if contact_data.is_primary:
            await db.emergencycontact.update_many(
                where={"user_id": current_user.id, "is_primary": True},
                data={"is_primary": False}
            )
        
        # Create the new emergency contact
        contact = await db.emergencycontact.create(
            data={
                "user_id": current_user.id,
                "name": contact_data.name,
                "phone_number": contact_data.phone_number,
                "email": contact_data.email,
                "relationship": contact_data.relationship,
                "is_primary": contact_data.is_primary,
            }
        )
        
        return EmergencyContactResponse(**contact.dict())
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create emergency contact: {str(e)}"
        )

@router.get("/", response_model=List[EmergencyContactResponse])
async def get_emergency_contacts(
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get all emergency contacts for the current user."""
    try:
        contacts = await db.emergencycontact.find_many(
            where={"user_id": current_user.id, "is_active": True},
            order={"is_primary": "desc", "created_at": "desc"}
        )
        
        return [EmergencyContactResponse(**contact.dict()) for contact in contacts]
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve emergency contacts: {str(e)}"
        )

@router.get("/{contact_id}", response_model=EmergencyContactResponse)
async def get_emergency_contact(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get a specific emergency contact by ID."""
    try:
        contact = await db.emergencycontact.find_unique(
            where={"id": contact_id}
        )
        
        if not contact or contact.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found"
            )
        
        return EmergencyContactResponse(**contact.dict())
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve emergency contact: {str(e)}"
        )

@router.put("/{contact_id}", response_model=EmergencyContactResponse)
async def update_emergency_contact(
    contact_id: str,
    contact_data: EmergencyContactUpdate,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update an emergency contact."""
    try:
        # Check if contact exists and belongs to user
        contact = await db.emergencycontact.find_unique(
            where={"id": contact_id}
        )
        
        if not contact or contact.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found"
            )
        
        # If setting this contact as primary, unset all other primary contacts
        if contact_data.is_primary:
            await db.emergencycontact.update_many(
                where={"user_id": current_user.id, "is_primary": True, "id": {"not": contact_id}},
                data={"is_primary": False}
            )
        
        # Prepare update data
        update_data = {}
        if contact_data.name is not None:
            update_data["name"] = contact_data.name
        if contact_data.phone_number is not None:
            update_data["phone_number"] = contact_data.phone_number
        if contact_data.email is not None:
            update_data["email"] = contact_data.email
        if contact_data.relationship is not None:
            update_data["relationship"] = contact_data.relationship
        if contact_data.is_primary is not None:
            update_data["is_primary"] = contact_data.is_primary
        if contact_data.is_active is not None:
            update_data["is_active"] = contact_data.is_active
        
        # Update the contact
        updated_contact = await db.emergencycontact.update(
            where={"id": contact_id},
            data=update_data
        )
        
        return EmergencyContactResponse(**updated_contact.dict())
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update emergency contact: {str(e)}"
        )

@router.delete("/{contact_id}", response_model=MessageResponse)
async def delete_emergency_contact(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete an emergency contact."""
    try:
        # Check if contact exists and belongs to user
        contact = await db.emergencycontact.find_unique(
            where={"id": contact_id}
        )
        
        if not contact or contact.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found"
            )
        
        # Soft delete by setting is_active to False
        await db.emergencycontact.update(
            where={"id": contact_id},
            data={"is_active": False}
        )
        
        return MessageResponse(message="Emergency contact deleted successfully")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete emergency contact: {str(e)}"
        )

@router.post("/sos", response_model=SosAlertResponse, status_code=status.HTTP_201_CREATED)
async def send_sos_alert(
    sos_data: SosAlertCreate,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Send SOS alert to all emergency contacts with user's location."""
    try:
        # Get all active emergency contacts for the user
        contacts = await db.emergencycontact.find_many(
            where={"user_id": current_user.id, "is_active": True}
        )
        
        if not contacts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No emergency contacts found. Please add emergency contacts before using SOS."
            )
        
        # Reverse geocode to get address from coordinates
        address = await reverse_geocode(sos_data.latitude, sos_data.longitude)
        
        # Create SOS alert record
        sos_alert = await db.sosalert.create(
            data={
                "user_id": current_user.id,
                "latitude": sos_data.latitude,
                "longitude": sos_data.longitude,
                "address": address,
                "notes": sos_data.notes,
                "contacts_notified": 0
            }
        )
        
        # Send notifications to all emergency contacts
        contacts_notified = 0
        for contact in contacts:
            try:
                await send_emergency_notification(
                    contact=contact,
                    user=current_user,
                    latitude=sos_data.latitude,
                    longitude=sos_data.longitude,
                    address=address,
                    notes=sos_data.notes
                )
                contacts_notified += 1
            except Exception as e:
                print(f"Failed to notify contact {contact.name}: {str(e)}")
                # Continue with other contacts even if one fails
        
        # Update the SOS alert with the number of contacts notified
        updated_sos_alert = await db.sosalert.update(
            where={"id": sos_alert.id},
            data={"contacts_notified": contacts_notified}
        )
        
        return SosAlertResponse(**updated_sos_alert.dict())
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send SOS alert: {str(e)}"
        )

@router.get("/sos/history", response_model=List[SosAlertResponse])
async def get_sos_history(
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get SOS alert history for the current user."""
    try:
        sos_alerts = await db.sosalert.find_many(
            where={"user_id": current_user.id},
            order={"timestamp": "desc"}
        )
        
        return [SosAlertResponse(**alert.dict()) for alert in sos_alerts]
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve SOS history: {str(e)}"
        )

@router.put("/sos/{alert_id}/resolve", response_model=SosAlertResponse)
async def resolve_sos_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Mark an SOS alert as resolved."""
    try:
        # Check if alert exists and belongs to user
        alert = await db.sosalert.find_unique(
            where={"id": alert_id}
        )
        
        if not alert or alert.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SOS alert not found"
            )
        
        # Update alert as resolved
        updated_alert = await db.sosalert.update(
            where={"id": alert_id},
            data={
                "is_resolved": True,
                "resolved_at": datetime.utcnow()
            }
        )
        
        return SosAlertResponse(**updated_alert.dict())
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve SOS alert: {str(e)}"
        )

# Helper functions
async def reverse_geocode(latitude: float, longitude: float) -> str:
    """Convert coordinates to human-readable address using Google Maps API."""
    try:
        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            return f"Lat: {latitude}, Lng: {longitude}"
        
        url = f"https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{latitude},{longitude}",
            "key": google_maps_api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                return data["results"][0]["formatted_address"]
            else:
                return f"Lat: {latitude}, Lng: {longitude}"
    
    except Exception:
        return f"Lat: {latitude}, Lng: {longitude}"

async def send_emergency_notification(
    contact: EmergencyContact,
    user: User,
    latitude: float,
    longitude: float,
    address: str,
    notes: str = None
):
    """Send emergency notification to a contact via SMS and/or email."""
    
    # Construct the emergency message
    google_maps_link = f"https://maps.google.com/maps?q={latitude},{longitude}"
    
    message = f"""
🚨 EMERGENCY ALERT 🚨

{user.name or user.username} has triggered an SOS alert and needs immediate help!

📍 Location: {address}
🗺️ View on Map: {google_maps_link}
🕐 Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    if notes:
        message += f"\n📝 Notes: {notes}"
    
    message += f"""

Please check on {user.name or user.username} immediately or contact emergency services if needed.

This alert was sent automatically from the SoloMate safety system.
"""
    
    # Send SMS notification (implement with your preferred SMS service)
    await send_sms_notification(contact.phone_number, message)
    
    # Send email notification if email is provided
    if contact.email:
        await send_email_notification(
            contact.email,
            f"🚨 Emergency Alert from {user.name or user.username}",
            message
        )

async def send_sms_notification(phone_number: str, message: str):
    """Send SMS notification using Twilio or similar service."""
    # TODO: Implement SMS sending with Twilio
    # For now, just log the message
    print(f"SMS to {phone_number}: {message}")
    
    # Example Twilio implementation:
    # from twilio.rest import Client
    # client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    # message = client.messages.create(
    #     body=message,
    #     from_=os.getenv("TWILIO_PHONE_NUMBER"),
    #     to=phone_number
    # )

async def send_email_notification(email: str, subject: str, body: str):
    """Send email notification using SendGrid or similar service."""
    # TODO: Implement email sending with SendGrid
    # For now, just log the message
    print(f"Email to {email}: {subject}\n{body}")
    
    # Example SendGrid implementation:
    # import sendgrid
    # from sendgrid.helpers.mail import Mail
    # sg = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))
    # message = Mail(
    #     from_email=os.getenv('FROM_EMAIL'),
    #     to_emails=email,
    #     subject=subject,
    #     html_content=body.replace('\n', '<br>')
    # )
    # response = sg.send(message)