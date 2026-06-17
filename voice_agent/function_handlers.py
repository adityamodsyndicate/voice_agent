import logging

logger = logging.getLogger(__name__)


async def dispatch_function(name: str, args: dict) -> dict:
    """Dispatches a voice agent function call to the inventory service.

    Args:
        name: Function name (e.g. 'search_laptop_inventory')
        args: Dictionary of arguments passed by the agent

    Returns:
        A dictionary of results sent back to the agent as context
    """
    from backend.inventory_service import inventory_service

    if name == "search_laptop_inventory":
        return await inventory_service.get_available_laptops(
            brand=args.get("brand"),
            max_price=args.get("max_price"),
            query=args.get("query"),
        )

    elif name == "reserve_laptop_or_visit":
        return await inventory_service.reserve_laptop(
            customer_name=args["customer_name"],
            customer_phone=args["customer_phone"],
            laptop_model=args["laptop_model"],
            visit_date=args["visit_date"],
            visit_time=args["visit_time"],
        )

    elif name == "check_reservation":
        return await inventory_service.check_reservation(
            customer_name=args.get("customer_name"),
            customer_phone=args.get("customer_phone"),
        )

    elif name == "cancel_reservation":
        return await inventory_service.cancel_reservation(
            reservation_id=args["reservation_id"],
        )

    elif name == "end_call":
        reason = args.get("reason", "customer_goodbye")
        logger.info(f"Call ending via tool call: {reason}")
        return {"status": "call_ended", "reason": reason}

    else:
        logger.warning(f"Unknown function requested: {name}")
        return {"error": f"Unknown function: {name}"}
