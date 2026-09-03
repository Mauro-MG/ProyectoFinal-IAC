def format_currency(value):
    if value is None:
        return "$0.00"
    return f"${value:,.2f}"

def format_date(value):
    if not value:
        return ""
    return value.strftime("%d/%m/%Y %H:%M")
