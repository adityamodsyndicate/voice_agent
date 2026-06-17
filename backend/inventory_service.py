import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from backend.models import LaptopItem, CustomerReservation

logger = logging.getLogger(__name__)

# Prepopulated catalog
INITIAL_INVENTORY = [
    LaptopItem(
        id="mac-air-m1",
        brand="Apple",
        model="MacBook Air M1",
        specs="8GB RAM, 256GB SSD, space gray",
        price=42000,
        condition="refurbished",
        warranty="1 Month testing warranty"
    ),
    LaptopItem(
        id="mac-pro-m2",
        brand="Apple",
        model="MacBook Pro M2",
        specs="16GB RAM, 512GB SSD, space gray",
        price=85000,
        condition="open-box",
        warranty="Remaining Apple brand warranty"
    ),
    LaptopItem(
        id="thinkpad-t480",
        brand="Lenovo",
        model="ThinkPad T480",
        specs="Intel Core i5 8th Gen, 8GB RAM, 256GB SSD, 14 inch screen",
        price=18500,
        condition="refurbished",
        warranty="1 Month testing warranty"
    ),
    LaptopItem(
        id="latitude-7490",
        brand="Dell",
        model="Latitude 7490",
        specs="Intel Core i5 8th Gen, 16GB RAM, 256GB SSD, 14 inch Full HD",
        price=21000,
        condition="refurbished",
        warranty="1 Month testing warranty"
    ),
    LaptopItem(
        id="elitebook-840",
        brand="HP",
        model="EliteBook 840 G5",
        specs="Intel Core i7 8th Gen, 16GB RAM, 512GB SSD, backlit keyboard",
        price=24500,
        condition="refurbished",
        warranty="1 Month testing warranty"
    ),
    LaptopItem(
        id="rog-strix",
        brand="Asus",
        model="ROG Strix Gaming",
        specs="Intel Core i7 10th Gen, 16GB RAM, 512GB SSD, GTX 1660Ti Graphics",
        price=45000,
        condition="used",
        warranty="1 Month testing warranty"
    ),
]


class InventoryService:
    """In-memory inventory database and reservation manager for Optimist Computers."""

    def __init__(self):
        self.inventory: Dict[str, LaptopItem] = {item.id: item for item in INITIAL_INVENTORY}
        self.reservations: Dict[str, CustomerReservation] = {}
        self._generate_mock_reservations()

    def _generate_mock_reservations(self):
        """Pre-populate a mock reservation for testing lookup."""
        mock_id = f"res-{uuid.uuid4().hex[:6]}"
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.reservations[mock_id] = CustomerReservation(
            id=mock_id,
            customer_name="Rohan Sharma",
            customer_phone="9876543210",
            laptop_model="MacBook Air M1",
            visit_date=tomorrow,
            visit_time="14:00"
        )
        logger.info(f"[INVENTORY_SERVICE] Initialized mock reservation: {mock_id}")

    async def get_available_laptops(
        self, brand: Optional[str] = None, max_price: Optional[int] = None, query: Optional[str] = None
    ) -> dict:
        """Search available laptops in stock, filtering by brand, price, or search query."""
        results = []
        for item in self.inventory.values():
            if not item.is_available:
                continue
            
            # Filter by Brand
            if brand and brand.lower() not in item.brand.lower():
                continue
            
            # Filter by Max Price
            if max_price is not None and item.price > max_price:
                continue

            # General query filter (specs or model keyword)
            if query:
                q = query.lower()
                matches_query = (
                    q in item.brand.lower() or 
                    q in item.model.lower() or 
                    q in item.specs.lower() or
                    q in item.condition.lower()
                )
                if not matches_query:
                    continue

            results.append(item)

        if not results:
            message = "I couldn't find any laptops matching that criteria in our current inventory. Our stock changes daily, so please feel free to call or WhatsApp us at +91 93555 01543 to verify."
            return {"laptops": [], "message": message}

        # Return up to 4 models (to avoid overwhelming the caller)
        results = results[:4]
        return {
            "laptops": [
                {
                    "laptop_id": item.id,
                    "brand": item.brand,
                    "model": item.model,
                    "specs": item.specs,
                    "price": item.price,
                    "condition": item.condition,
                    "description": item.display(),
                }
                for item in results
            ],
            "total_matches": len(results)
        }

    async def reserve_laptop(
        self, customer_name: str, customer_phone: str, laptop_model: str, visit_date: str, visit_time: str
    ) -> dict:
        """Reserve a laptop and schedule a showroom visit. Returns confirmation details."""
        # Clean phone input
        customer_phone = customer_phone.replace(" ", "").replace("-", "")

        # Check if the store is open on that date
        try:
            dt = datetime.strptime(visit_date, "%Y-%m-%d").date()
            if dt.weekday() == 6:  # Sunday
                return {
                    "success": False,
                    "error": "The shop is closed on Sundays. Please select a day from Monday to Saturday."
                }
        except ValueError:
            pass

        res_id = f"res-{uuid.uuid4().hex[:6]}"
        reservation = CustomerReservation(
            id=res_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            laptop_model=laptop_model,
            visit_date=visit_date,
            visit_time=visit_time
        )
        self.reservations[res_id] = reservation
        logger.info(f"[INVENTORY_SERVICE] Reserved laptop: {reservation.display()}")

        return {
            "success": True,
            "reservation_id": res_id,
            "confirmation": f"Reserved visit: {reservation.display()}",
            "customer_name": customer_name,
            "shop_address": "Shop G-5, Shakuntala Building, 59 Nehru Place, New Delhi",
            "shop_timings": "11 AM to 8 PM, Monday through Saturday"
        }

    async def check_reservation(
        self, customer_name: Optional[str] = None, customer_phone: Optional[str] = None
    ) -> dict:
        """Look up a customer's visit reservation by phone or name."""
        if not customer_name and not customer_phone:
            return {"found": False, "message": "Please provide your name or phone number so I can look up the reservation."}

        matches = []
        # Normalise phone
        phone_cleaned = customer_phone.replace(" ", "").replace("-", "") if customer_phone else None

        for res in self.reservations.values():
            if phone_cleaned and phone_cleaned in res.customer_phone.replace(" ", "").replace("-", ""):
                matches.append(res)
            elif customer_name and customer_name.lower() in res.customer_name.lower():
                matches.append(res)

        if not matches:
            return {
                "found": False,
                "message": "I couldn't find any showroom visit or laptop reservations under that name or phone number."
            }

        return {
            "found": True,
            "reservations": [
                {
                    "reservation_id": r.id,
                    "customer_name": r.customer_name,
                    "laptop_model": r.laptop_model,
                    "visit_date": r.visit_date,
                    "visit_time": r.visit_time,
                    "description": r.display(),
                }
                for r in matches
            ]
        }

    async def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a reservation."""
        if reservation_id in self.reservations:
            res = self.reservations.pop(reservation_id)
            logger.info(f"[INVENTORY_SERVICE] Cancelled reservation: {reservation_id}")
            return {
                "success": True,
                "message": f"Successfully cancelled reservation for {res.customer_name} to check out the {res.laptop_model}."
            }
        return {"success": False, "error": "Reservation not found."}


# Singleton instance shared across requests
inventory_service = InventoryService()
