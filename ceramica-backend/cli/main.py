"""
Ceramica TUI — Client #1 (development client consuming the REST API).
Run: python cli/main.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

BASE_URL = "http://localhost:8000"
_state: dict = {"token": None, "store_id": None, "store_slug": None}


def _headers() -> dict:
    return {"Authorization": f"Bearer {_state['token']}"} if _state["token"] else {}


def _fmt_cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


async def login_flow(client: httpx.AsyncClient) -> bool:
    console.print(Panel("[bold cyan]Ceramica Store — Login[/]", expand=False))
    slug = questionary.text("Store slug:").ask()
    email = questionary.text("Email:").ask()
    password = questionary.password("Password:").ask()

    resp = await client.post("/auth/login", json={"store_slug": slug, "email": email, "password": password})
    if resp.status_code != 200:
        console.print(f"[red]Login failed: {resp.json().get('error', 'unknown error')}[/]")
        return False

    data = resp.json()["data"]
    _state["token"] = data["access_token"]
    _state["store_id"] = data["store_id"]
    _state["store_slug"] = slug
    console.print(f"[green]✓ Logged in as {email} [{data['role']}][/]")
    return True


async def show_dashboard(client: httpx.AsyncClient):
    resp = await client.get("/finance/dashboard", headers=_headers())
    if resp.status_code != 200:
        console.print("[red]Failed to load dashboard[/]")
        return
    d = resp.json()["data"]
    table = Table(title="📊 Dashboard (last 30 days)", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Revenue", _fmt_cents(d["revenue_cents"]))
    table.add_row("Expenses", _fmt_cents(d["expenses_cents"]))
    table.add_row("Profit", _fmt_cents(d["profit_cents"]))
    table.add_row("Sales count", str(d["sales_count"]))
    table.add_row("Pending debt", _fmt_cents(d["pending_debt_cents"]))
    table.add_row("Low-stock items", str(d["low_stock_count"]))
    console.print(table)


async def show_products(client: httpx.AsyncClient):
    resp = await client.get("/products?limit=50", headers=_headers())
    if resp.status_code != 200:
        console.print("[red]Failed to load products[/]")
        return
    items = resp.json()["data"]
    meta = resp.json()["meta"]
    table = Table(title=f"📦 Products ({meta['total']} total)", box=box.SIMPLE)
    table.add_column("SKU", style="yellow")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Price", justify="right")
    table.add_column("Stock", justify="right")
    for p in items:
        stock_style = "red" if p["stock_quantity"] <= p["low_stock_threshold"] else "green"
        table.add_row(
            p["sku"], p["name"], p.get("category") or "-",
            _fmt_cents(p["price_cents"]),
            f"[{stock_style}]{p['stock_quantity']}[/]",
        )
    console.print(table)


async def show_clients(client: httpx.AsyncClient):
    resp = await client.get("/clients?limit=50", headers=_headers())
    if resp.status_code != 200:
        console.print("[red]Failed to load clients[/]")
        return
    items = resp.json()["data"]
    meta = resp.json()["meta"]
    table = Table(title=f"👥 Clients ({meta['total']} total)", box=box.SIMPLE)
    table.add_column("Name")
    table.add_column("Phone")
    table.add_column("Debt", justify="right")
    for c in items:
        debt_style = "red" if c["debt_cents"] > 0 else "green"
        table.add_row(
            c["full_name"], c.get("phone") or "-",
            f"[{debt_style}]{_fmt_cents(c['debt_cents'])}[/]",
        )
    console.print(table)


async def show_sales(client: httpx.AsyncClient):
    resp = await client.get("/sales?limit=20", headers=_headers())
    if resp.status_code != 200:
        console.print("[red]Failed to load sales[/]")
        return
    items = resp.json()["data"]
    table = Table(title="🧾 Recent Sales", box=box.SIMPLE)
    table.add_column("ID", style="dim")
    table.add_column("Status")
    table.add_column("Total", justify="right")
    table.add_column("Paid", justify="right")
    table.add_column("Balance", justify="right")
    for s in items:
        status_color = {"completed": "green", "partial": "yellow", "pending": "red", "cancelled": "dim"}.get(s["status"], "white")
        table.add_row(
            s["id"][:8],
            f"[{status_color}]{s['status']}[/]",
            _fmt_cents(s["total_cents"]),
            _fmt_cents(s["paid_cents"]),
            _fmt_cents(s["balance_cents"]),
        )
    console.print(table)


async def quick_sale(client: httpx.AsyncClient):
    console.print(Panel("[bold]Quick Sale[/]", expand=False))
    resp = await client.get("/products?limit=100", headers=_headers())
    if resp.status_code != 200:
        console.print("[red]Cannot load products[/]")
        return
    products = {p["sku"]: p for p in resp.json()["data"]}

    items = []
    while True:
        sku = questionary.text("Product SKU (or blank to finish):").ask()
        if not sku:
            break
        if sku not in products:
            console.print(f"[red]SKU '{sku}' not found[/]")
            continue
        product = products[sku]
        qty = int(questionary.text(f"Quantity (stock: {product['stock_quantity']}):").ask() or "0")
        if qty <= 0:
            continue
        items.append({
            "product_id": product["id"],
            "quantity": qty,
            "unit_price_cents": product["price_cents"],
            "discount_cents": 0,
        })
        console.print(f"  [green]+ {qty}x {product['name']} = {_fmt_cents(qty * product['price_cents'])}[/]")

    if not items:
        return

    method_choice = questionary.select(
        "Payment method:", choices=["cash", "card", "transfer", "credit"]
    ).ask()

    total = sum(i["quantity"] * i["unit_price_cents"] - i["discount_cents"] for i in items)
    console.print(f"\nTotal: [bold green]{_fmt_cents(total)}[/]")
    confirm = questionary.confirm("Confirm sale?").ask()
    if not confirm:
        return

    payload = {
        "items": items,
        "discount_cents": 0,
        "payment_method": method_choice,
        "payment_amount_cents": total if method_choice != "credit" else None,
    }
    resp = await client.post("/sales", json=payload, headers=_headers())
    if resp.status_code == 201:
        sale = resp.json()["data"]
        console.print(f"[bold green]✓ Sale created: {sale['id'][:8]} — {sale['status']}[/]")
    else:
        console.print(f"[red]Sale failed: {resp.json().get('error')}[/]")


async def main_menu(client: httpx.AsyncClient):
    choices = [
        "📊  Dashboard",
        "📦  Products",
        "👥  Clients",
        "🧾  Sales",
        "💰  Quick Sale",
        "─────────────",
        "🚪  Logout",
    ]
    while True:
        choice = questionary.select(
            f"\n[{_state['store_slug']}] Main Menu", choices=choices
        ).ask()
        if choice is None or "Logout" in choice:
            break
        elif "Dashboard" in choice:
            await show_dashboard(client)
        elif "Products" in choice:
            await show_products(client)
        elif "Clients" in choice:
            await show_clients(client)
        elif "Sales" in choice:
            await show_sales(client)
        elif "Quick Sale" in choice:
            await quick_sale(client)


async def run():
    console.print(Panel(
        "[bold magenta]🏺 Ceramica Store Manager[/]\n"
        "[dim]TUI Client v1.0 — connects to REST API at localhost:8000[/]",
        expand=False
    ))
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Health check
        try:
            await client.get("/health")
        except httpx.ConnectError:
            console.print(f"[red]Cannot connect to API at {BASE_URL}. Is the server running?[/]")
            return

        logged_in = await login_flow(client)
        if logged_in:
            await main_menu(client)

    console.print("[dim]Goodbye![/]")


if __name__ == "__main__":
    asyncio.run(run())
