import os
import json
import httpx
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("harvest-api")

# Get environment variables for Harvest API
HARVEST_ACCOUNT_ID = os.environ.get("HARVEST_ACCOUNT_ID")
HARVEST_API_KEY = os.environ.get("HARVEST_API_KEY")

if not HARVEST_ACCOUNT_ID or not HARVEST_API_KEY:
    raise ValueError(
        "Missing Harvest API credentials. Set HARVEST_ACCOUNT_ID and HARVEST_API_KEY environment variables."
    )

# Read-only mode: when enabled, write operations return an error message
# instead of modifying Harvest data.
HARVEST_READ_ONLY = os.environ.get("HARVEST_READ_ONLY", "").lower() in ("true", "1", "yes")

READ_ONLY_MESSAGE = json.dumps(
    {
        "error": "read_only_mode",
        "message": (
            "This Harvest MCP server is running in read-only mode. "
            "To enable write operations, remove the HARVEST_READ_ONLY environment variable "
            "or set it to 'false' in your MCP server configuration."
        ),
    },
    indent=2,
)


# Helper function to make Harvest API requests
async def harvest_request(path, params=None, method="GET"):
    headers = {
        "Harvest-Account-Id": HARVEST_ACCOUNT_ID,
        "Authorization": f"Bearer {HARVEST_API_KEY}",
        "User-Agent": "Harvest MCP Server",
        "Content-Type": "application/json",
    }

    url = f"https://api.harvestapp.com/v2/{path}"

    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, headers=headers, params=params)
        else:
            response = await client.request(method, url, headers=headers, json=params)

        if response.status_code not in (200, 201):
            raise Exception(
                f"Harvest API Error: {response.status_code} {response.text}"
            )

        return response.json()


@mcp.tool()
async def list_users(is_active: bool = None, page: int = None, per_page: int = None):
    """List all users in your Harvest account.

    Args:
        is_active: Pass true to only return active users and false to return inactive users
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = {}
    if is_active is not None:
        params["is_active"] = "true" if is_active else "false"
    else:
        params["is_active"] = "true"
    if page is not None:
        params["page"] = str(page)
    if per_page is not None:
        params["per_page"] = str(per_page)
    else:
        params["per_page"] = 200

    response = await harvest_request("users", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_user_details(user_id: int):
    """Retrieve details for a specific user.

    Args:
        user_id: The ID of the user to retrieve
    """
    response = await harvest_request(f"users/{user_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_time_entries(
    user_id: int = None,
    project_id: int = None,
    from_date: str = None,
    to_date: str = None,
    is_running: bool = None,
    is_billable: bool = None,
):
    """List time entries with optional filtering.

    Args:
        user_id: Filter by user ID
        project_id: Only return time entries belonging to the project with the given ID
        from_date: Only return time entries with a spent_date on or after the given date (YYYY-MM-DD)
        to_date: Only return time entries with a spent_date on or before the given date (YYYY-MM-DD)
        is_running: Pass true to only return running time entries and false to return non-running time entries
        is_billable: Pass true to only return billable time entries and false to return non-billable time entries
    """
    params = {}
    if user_id is not None:
        params["user_id"] = str(user_id)
    if project_id is not None:
        params["project_id"] = str(project_id)
    if from_date is not None:
        params["from"] = from_date
    if to_date is not None:
        params["to"] = to_date
    if is_running is not None:
        params["is_running"] = "true" if is_running else "false"
    if is_billable is not None:
        params["is_billable"] = "true" if is_billable else "false"

    response = await harvest_request("time_entries", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def create_time_entry(
    project_id: int,
    task_id: int,
    spent_date: str,
    hours: float,
    notes: str | int | None = None,
):
    """Create a new time entry.

    Args:
        project_id: The ID of the project to associate with the time entry
        task_id: The ID of the task to associate with the time entry
        spent_date: The date when the time was spent (YYYY-MM-DD)
        hours: The number of hours spent
        notes: Optional notes about the time entry
    """
    if HARVEST_READ_ONLY:
        return READ_ONLY_MESSAGE

    params = {
        "project_id": project_id,
        "task_id": task_id,
        "spent_date": spent_date,
        "hours": hours,
    }

    if notes is not None:
        params["notes"] = str(notes)

    response = await harvest_request("time_entries", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def stop_timer(time_entry_id: int):
    """Stop a running timer.

    Args:
        time_entry_id: The ID of the running time entry to stop
    """
    if HARVEST_READ_ONLY:
        return READ_ONLY_MESSAGE

    response = await harvest_request(
        f"time_entries/{time_entry_id}/stop", method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def start_timer(
    project_id: int,
    task_id: int,
    notes: str | int | None = None,
):
    """Start a new timer.

    Args:
        project_id: The ID of the project to associate with the time entry
        task_id: The ID of the task to associate with the time entry
        notes: Optional notes about the time entry
    """
    if HARVEST_READ_ONLY:
        return READ_ONLY_MESSAGE

    params = {
        "project_id": project_id,
        "task_id": task_id,
        "spent_date": datetime.now().strftime("%Y-%m-%d"),
    }

    if notes is not None:
        params["notes"] = str(notes)

    response = await harvest_request("time_entries", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_projects(client_id: int = None, is_active: bool = None):
    """List projects with optional filtering.

    Args:
        client_id: Filter by client ID
        is_active: Pass true to only return active projects and false to return inactive projects
    """
    params = {}
    if client_id is not None:
        params["client_id"] = str(client_id)
    if is_active is not None:
        params["is_active"] = "true" if is_active else "false"

    response = await harvest_request("projects", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_project_details(project_id: int):
    """Get detailed information about a specific project.

    Args:
        project_id: The ID of the project to retrieve
    """
    response = await harvest_request(f"projects/{project_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_clients(is_active: bool = None):
    """List clients with optional filtering.

    Args:
        is_active: Pass true to only return active clients and false to return inactive clients
    """
    params = {}
    if is_active is not None:
        params["is_active"] = "true" if is_active else "false"

    response = await harvest_request("clients", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_client_details(client_id: int):
    """Get detailed information about a specific client.

    Args:
        client_id: The ID of the client to retrieve
    """
    response = await harvest_request(f"clients/{client_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_tasks(is_active: bool = None):
    """List all tasks with optional filtering.

    Args:
        is_active: Pass true to only return active tasks and false to return inactive tasks
    """
    params = {}
    if is_active is not None:
        params["is_active"] = "true" if is_active else "false"

    response = await harvest_request("tasks", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_unsubmitted_timesheets(
    user_id: int = None,
    from_date: str = None,
    to_date: str = None,
    page: int = None,
    per_page: int = None,
):
    """Get unsubmitted timesheets (time entries that haven't been submitted for approval).

    This function queries for time entries that are not yet closed/submitted, which typically
    means they are still editable and haven't been submitted for approval or invoicing.

    Args:
        user_id: Filter by specific user ID (optional)
        from_date: Only return time entries with a spent_date on or after the given date (YYYY-MM-DD)
        to_date: Only return time entries with a spent_date on or before the given date (YYYY-MM-DD)
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = {}
    if user_id is not None:
        params["user_id"] = str(user_id)
    if from_date is not None:
        params["from"] = from_date
    if to_date is not None:
        params["to"] = to_date
    if page is not None:
        params["page"] = str(page)
    if per_page is not None:
        params["per_page"] = str(per_page)
    else:
        params["per_page"] = "200"

    # Get all time entries first
    response = await harvest_request("time_entries", params)

    # Filter for unsubmitted entries (those that are not closed)
    unsubmitted_entries = []
    if "time_entries" in response:
        for entry in response["time_entries"]:
            # Time entries that are not closed are considered unsubmitted
            if not entry.get("is_closed", False):
                unsubmitted_entries.append(entry)

    # Create a response structure similar to the original API response
    filtered_response = {
        "time_entries": unsubmitted_entries,
        "per_page": response.get("per_page", len(unsubmitted_entries)),
        "total_pages": 1,  # Simplified since we're filtering client-side
        "total_entries": len(unsubmitted_entries),
        "next_page": None,
        "previous_page": None,
        "page": response.get("page", 1),
        "links": response.get("links", {}),
    }

    return json.dumps(filtered_response, indent=2)


@mcp.tool()
async def create_invoice_from_time_and_expenses(
    client_id: int,
    project_ids: list[int],
    time_summary_type: str = None,
    time_from: str = None,
    time_to: str = None,
    expense_summary_type: str = None,
    expense_from: str = None,
    expense_to: str = None,
    expense_attach_receipt: bool = None,
    issue_date: str = None,
    due_date: str = None,
    payment_term: str = None,
    subject: str = None,
    notes: str = None,
    number: str = None,
    purchase_order: str = None,
    currency: str = None,
    tax: float = None,
    tax2: float = None,
    discount: float = None,
):
    """Create an invoice based on tracked time and expenses for a client.

    Args:
        client_id: The ID of the client this invoice will be sent to
        project_ids: The IDs of the projects to include time/expenses from
        time_summary_type: How to summarize time entries per line item: project, task, people, or detailed. Omit to exclude time.
        time_from: Start date for included time entries (YYYY-MM-DD)
        time_to: End date for included time entries (YYYY-MM-DD)
        expense_summary_type: How to summarize expenses per line item: project, category, people, or detailed. Omit to exclude expenses.
        expense_from: Start date for included expenses (YYYY-MM-DD)
        expense_to: End date for included expenses (YYYY-MM-DD)
        expense_attach_receipt: If true, attach a PDF expense report with receipts to the invoice
        issue_date: Date the invoice was issued (YYYY-MM-DD). Defaults to today.
        due_date: Date the invoice is due (YYYY-MM-DD)
        payment_term: Timeframe client is expected to pay: upon receipt, net 15, net 30, net 45, net 60, or custom
        subject: The invoice subject
        notes: Additional notes to include on the invoice
        number: Invoice number. Auto-generated if not provided.
        purchase_order: The purchase order number associated with this invoice
        currency: ISO 4217 currency code. Defaults to the client's currency.
        tax: Percentage for first additional tax on the invoice
        tax2: Percentage for second additional tax on the invoice
        discount: Percentage discount on the invoice
    """
    line_items_import = {"project_ids": project_ids}

    if time_summary_type is not None:
        time_import = {"summary_type": time_summary_type}
        if time_from is not None:
            time_import["from"] = time_from
        if time_to is not None:
            time_import["to"] = time_to
        line_items_import["time"] = time_import

    if expense_summary_type is not None:
        expense_import = {"summary_type": expense_summary_type}
        if expense_from is not None:
            expense_import["from"] = expense_from
        if expense_to is not None:
            expense_import["to"] = expense_to
        if expense_attach_receipt is not None:
            expense_import["attach_receipt"] = expense_attach_receipt
        line_items_import["expenses"] = expense_import

    params = {
        "client_id": client_id,
        "line_items_import": line_items_import,
    }

    if issue_date is not None:
        params["issue_date"] = issue_date
    if due_date is not None:
        params["due_date"] = due_date
    if payment_term is not None:
        params["payment_term"] = payment_term
    if subject is not None:
        params["subject"] = subject
    if notes is not None:
        params["notes"] = notes
    if number is not None:
        params["number"] = number
    if purchase_order is not None:
        params["purchase_order"] = purchase_order
    if currency is not None:
        params["currency"] = currency
    if tax is not None:
        params["tax"] = tax
    if tax2 is not None:
        params["tax2"] = tax2
    if discount is not None:
        params["discount"] = discount

    response = await harvest_request("invoices", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_invoices(
    client_id: int = None,
    project_id: int = None,
    state: str = None,
    from_date: str = None,
    to_date: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all invoices, with optional filtering.

    Args:
        client_id: Filter by client ID
        project_id: Filter by project ID
        state: Filter by invoice state: draft, open, paid, or closed
        from_date: Only return invoices with an issue_date on or after this date (YYYY-MM-DD)
        to_date: Only return invoices with an issue_date on or before this date (YYYY-MM-DD)
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = {}
    if client_id is not None:
        params["client_id"] = str(client_id)
    if project_id is not None:
        params["project_id"] = str(project_id)
    if state is not None:
        params["state"] = state
    if from_date is not None:
        params["from"] = from_date
    if to_date is not None:
        params["to"] = to_date
    if page is not None:
        params["page"] = str(page)
    if per_page is not None:
        params["per_page"] = str(per_page)

    response = await harvest_request("invoices", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_invoice_details(invoice_id: int):
    """Retrieve details for a specific invoice.

    Args:
        invoice_id: The ID of the invoice to retrieve
    """
    response = await harvest_request(f"invoices/{invoice_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_invoice_payments(invoice_id: int):
    """List all payments for a specific invoice.

    Args:
        invoice_id: The ID of the invoice to retrieve payments for
    """
    response = await harvest_request(f"invoices/{invoice_id}/payments")
    return json.dumps(response, indent=2)


@mcp.tool()
async def create_invoice_payment(
    invoice_id: int,
    amount: float,
    paid_at: str = None,
    paid_date: str = None,
    notes: str = None,
):
    """Record a payment against an invoice.

    Args:
        invoice_id: The ID of the invoice to record a payment for
        amount: The amount of the payment
        paid_at: Datetime the payment was made (ISO 8601). Defaults to now.
        paid_date: Date the payment was made (YYYY-MM-DD). Defaults to today.
        notes: Optional notes about the payment
    """
    params = {"amount": amount}
    if paid_at is not None:
        params["paid_at"] = paid_at
    if paid_date is not None:
        params["paid_date"] = paid_date
    if notes is not None:
        params["notes"] = notes

    response = await harvest_request(f"invoices/{invoice_id}/payments", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_uninvoiced_report(
    from_date: str,
    to_date: str,
    page: int = None,
    per_page: int = None,
):
    """Get a report of billable time and expenses that have not yet been invoiced.

    Args:
        from_date: Start date for the report (YYYY-MM-DD, required)
        to_date: End date for the report (YYYY-MM-DD, required)
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = {"from": from_date, "to": to_date}
    if page is not None:
        params["page"] = str(page)
    if per_page is not None:
        params["per_page"] = str(per_page)

    response = await harvest_request("reports/uninvoiced", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def update_time_entry(
    time_entry_id: int,
    project_id: int = None,
    task_id: int = None,
    spent_date: str = None,
    hours: float = None,
    notes: str = None,
):
    """Update an existing time entry.

    Args:
        time_entry_id: The ID of the time entry to update
        project_id: The ID of the project to associate with the time entry
        task_id: The ID of the task to associate with the time entry
        spent_date: The date when the time was spent (YYYY-MM-DD)
        hours: The number of hours spent
        notes: Notes about the time entry
    """
    params = {}
    if project_id is not None:
        params["project_id"] = project_id
    if task_id is not None:
        params["task_id"] = task_id
    if spent_date is not None:
        params["spent_date"] = spent_date
    if hours is not None:
        params["hours"] = hours
    if notes is not None:
        params["notes"] = str(notes)

    response = await harvest_request(f"time_entries/{time_entry_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
async def delete_time_entry(time_entry_id: int):
    """Delete a time entry.

    Args:
        time_entry_id: The ID of the time entry to delete
    """
    async with httpx.AsyncClient() as client:
        headers = {
            "Harvest-Account-Id": HARVEST_ACCOUNT_ID,
            "Authorization": f"Bearer {HARVEST_API_KEY}",
            "User-Agent": "Harvest MCP Server",
        }
        response = await client.delete(
            f"https://api.harvestapp.com/v2/time_entries/{time_entry_id}",
            headers=headers,
        )
        if response.status_code != 204:
            raise Exception(f"Harvest API Error: {response.status_code} {response.text}")

    return json.dumps({"deleted": True, "time_entry_id": time_entry_id}, indent=2)


@mcp.tool()
async def list_project_user_assignments(project_id: int, page: int = None, per_page: int = None):
    """List all user assignments for a specific project.

    Args:
        project_id: The ID of the project
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = {}
    if page is not None:
        params["page"] = str(page)
    if per_page is not None:
        params["per_page"] = str(per_page)

    response = await harvest_request(f"projects/{project_id}/user_assignments", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_project_task_assignments(project_id: int, page: int = None, per_page: int = None):
    """List all task assignments for a specific project.

    Args:
        project_id: The ID of the project
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = {}
    if page is not None:
        params["page"] = str(page)
    if per_page is not None:
        params["per_page"] = str(per_page)

    response = await harvest_request(f"projects/{project_id}/task_assignments", params)
    return json.dumps(response, indent=2)


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
