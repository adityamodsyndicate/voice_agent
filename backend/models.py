from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class LaptopItem:
    """A laptop model in stock."""
    id: str
    brand: str
    model: str
    specs: str
    price: int  # in INR
    condition: str  # "refurbished", "open-box", "used"
    warranty: str
    is_available: bool = True

    def display(self) -> str:
        """Formatted laptop details for text-to-speech."""
        return f"{self.condition.title()} {self.brand} {self.model} with {self.specs} priced at {self.price} Rupees, including {self.warranty}."

@dataclass
class CustomerReservation:
    """A customer showroom visit reservation."""
    id: str
    customer_name: str
    customer_phone: str
    laptop_model: str
    visit_date: str  # YYYY-MM-DD
    visit_time: str  # HH:MM
    created_at: datetime = field(default_factory=datetime.now)

    def display(self) -> str:
        """Formatted reservation details for text-to-speech."""
        # Convert 24h time to 12h for natural speech
        hour, minute = map(int, self.visit_time.split(":"))
        period = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        time_str = f"{display_hour}:{minute:02d} {period}" if minute else f"{display_hour} {period}"
        return f"Reservation for {self.customer_name} to check a {self.laptop_model} on {self.visit_date} at {time_str}."
