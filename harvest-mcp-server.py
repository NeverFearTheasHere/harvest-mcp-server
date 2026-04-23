import os
import json
import functools
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
        elif method == "DELETE":
            response = await client.delete(url, headers=headers, params=params)
        else:
            response = await client.request(method, url, headers=headers, json=params)

        if response.status_code not in (200, 201, 204):
            raise Exception(
                f"Harvest API Error: {response.status_code} {response.text}"
            )

        if response.status_code == 204 or not response.content:
            return {"ok": True}

        return response.json()


def build_body(**kwargs):
    """Drop None values — use for POST/PATCH JSON bodies."""
    return {k: v for k, v in kwargs.items() if v is not None}


def build_query(**kwargs):
    """Drop None values and stringify bools/ints — use for GET query params."""
    params = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, bool):
            params[k] = "true" if v else "false"
        elif isinstance(v, int):
            params[k] = str(v)
        else:
            params[k] = v
    return params


def requires_write(func):
    """Short-circuit write tools when HARVEST_READ_ONLY is set."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if HARVEST_READ_ONLY:
            return READ_ONLY_MESSAGE
        return await func(*args, **kwargs)
    return wrapper


@mcp.tool()
async def list_users(is_active: bool = None, page: int = None, per_page: int = None):
    """List all users in your Harvest account.

    Args:
        is_active: Pass true to only return active users and false to return inactive users
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = build_query(
        is_active=is_active if is_active is not None else True,
        page=page,
        per_page=per_page if per_page is not None else 200,
    )
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
    params = build_query(
        user_id=user_id,
        project_id=project_id,
        is_running=is_running,
        is_billable=is_billable,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("time_entries", params)
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
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
    params = build_body(
        project_id=project_id,
        task_id=task_id,
        spent_date=spent_date,
        hours=hours,
        notes=str(notes) if notes is not None else None,
    )
    response = await harvest_request("time_entries", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def stop_timer(time_entry_id: int):
    """Stop a running timer.

    Args:
        time_entry_id: The ID of the running time entry to stop
    """
    response = await harvest_request(
        f"time_entries/{time_entry_id}/stop", method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
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
    params = build_body(
        project_id=project_id,
        task_id=task_id,
        spent_date=datetime.now().strftime("%Y-%m-%d"),
        notes=str(notes) if notes is not None else None,
    )
    response = await harvest_request("time_entries", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_projects(client_id: int = None, is_active: bool = None):
    """List projects with optional filtering.

    Args:
        client_id: Filter by client ID
        is_active: Pass true to only return active projects and false to return inactive projects
    """
    params = build_query(client_id=client_id, is_active=is_active)
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
@requires_write
async def create_project(
    client_id: int,
    name: str,
    is_billable: bool,
    bill_by: str,
    budget_by: str,
    code: str = None,
    is_active: bool = None,
    is_fixed_fee: bool = None,
    hourly_rate: float = None,
    budget: float = None,
    budget_is_monthly: bool = None,
    notify_when_over_budget: bool = None,
    over_budget_notification_percentage: float = None,
    show_budget_to_all: bool = None,
    cost_budget: float = None,
    cost_budget_include_expenses: bool = None,
    fee: float = None,
    notes: str = None,
    starts_on: str = None,
    ends_on: str = None,
):
    """Create a new project.

    Args:
        client_id: The ID of the client to associate with the project
        name: The name of the project
        is_billable: Whether the project is billable or not
        bill_by: The method by which the project is invoiced - "Project", "Tasks", "People", or "none"
        budget_by: The method by which the project is budgeted - "project", "project_cost", "task", "task_fees", "person", or "none"
        code: The project code
        is_active: Whether the project is active or archived
        is_fixed_fee: Whether the project is a fixed-fee project or not
        hourly_rate: Rate for projects billed by Project Hourly Rate
        budget: The budget in hours for the project when budget_by is "project" or "none"
        budget_is_monthly: Option to have the budget reset every month
        notify_when_over_budget: Whether project managers should be notified when the project goes over budget
        over_budget_notification_percentage: Percentage value used to trigger over budget email alerts (0.0 to 100.0)
        show_budget_to_all: Option to show project budget to all employees (defaults to project managers and up)
        cost_budget: The monetary budget for the project when budget_by is "project_cost"
        cost_budget_include_expenses: Option for budget of "project_cost" to include tracked expenses
        fee: The amount you plan to invoice for the project (only used by fixed-fee projects)
        notes: Project notes
        starts_on: Date the project was started (YYYY-MM-DD)
        ends_on: Date the project will end (YYYY-MM-DD)
    """
    params = build_body(
        client_id=client_id,
        name=name,
        is_billable=is_billable,
        bill_by=bill_by,
        budget_by=budget_by,
        code=code,
        is_active=is_active,
        is_fixed_fee=is_fixed_fee,
        hourly_rate=hourly_rate,
        budget=budget,
        budget_is_monthly=budget_is_monthly,
        notify_when_over_budget=notify_when_over_budget,
        over_budget_notification_percentage=over_budget_notification_percentage,
        show_budget_to_all=show_budget_to_all,
        cost_budget=cost_budget,
        cost_budget_include_expenses=cost_budget_include_expenses,
        fee=fee,
        notes=notes,
        starts_on=starts_on,
        ends_on=ends_on,
    )
    response = await harvest_request("projects", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_clients(is_active: bool = None):
    """List clients with optional filtering.

    Args:
        is_active: Pass true to only return active clients and false to return inactive clients
    """
    params = build_query(is_active=is_active)
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
@requires_write
async def create_client(
    name: str,
    is_active: bool = None,
    address: str = None,
    currency: str = None,
):
    """Create a new client.

    Args:
        name: The name of the client
        is_active: Whether the client is active or archived
        address: The physical address of the client
        currency: The currency code the client is billed in (ISO 4217, e.g. "USD", "EUR")
    """
    params = build_body(
        name=name,
        is_active=is_active,
        address=address,
        currency=currency,
    )
    response = await harvest_request("clients", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_tasks(is_active: bool = None):
    """List all tasks with optional filtering.

    Args:
        is_active: Pass true to only return active tasks and false to return inactive tasks
    """
    params = build_query(is_active=is_active)
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
    params = build_query(
        user_id=user_id,
        page=page,
        per_page=per_page if per_page is not None else 200,
        **{"from": from_date, "to": to_date},
    )
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
@requires_write
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
        line_items_import["time"] = build_body(
            summary_type=time_summary_type,
            **{"from": time_from, "to": time_to},
        )
    if expense_summary_type is not None:
        line_items_import["expenses"] = build_body(
            summary_type=expense_summary_type,
            attach_receipt=expense_attach_receipt,
            **{"from": expense_from, "to": expense_to},
        )

    params = build_body(
        client_id=client_id,
        line_items_import=line_items_import,
        issue_date=issue_date,
        due_date=due_date,
        payment_term=payment_term,
        subject=subject,
        notes=notes,
        number=number,
        purchase_order=purchase_order,
        currency=currency,
        tax=tax,
        tax2=tax2,
        discount=discount,
    )
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
    params = build_query(
        client_id=client_id,
        project_id=project_id,
        state=state,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
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
@requires_write
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
    params = build_body(
        amount=amount,
        paid_at=paid_at,
        paid_date=paid_date,
        notes=notes,
    )
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
    params = build_query(
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("reports/uninvoiced", params)
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
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
    params = build_body(
        project_id=project_id,
        task_id=task_id,
        spent_date=spent_date,
        hours=hours,
        notes=str(notes) if notes is not None else None,
    )
    response = await harvest_request(f"time_entries/{time_entry_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_time_entry(time_entry_id: int):
    """Delete a time entry.

    Args:
        time_entry_id: The ID of the time entry to delete
    """
    await harvest_request(f"time_entries/{time_entry_id}", method="DELETE")
    return json.dumps({"deleted": True, "time_entry_id": time_entry_id}, indent=2)


@mcp.tool()
async def list_project_user_assignments(project_id: int, page: int = None, per_page: int = None):
    """List all user assignments for a specific project.

    Args:
        project_id: The ID of the project
        page: The page number for pagination
        per_page: The number of records to return per page (1-2000)
    """
    params = build_query(page=page, per_page=per_page)
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
    params = build_query(page=page, per_page=per_page)
    response = await harvest_request(f"projects/{project_id}/task_assignments", params)
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_project(
    project_id: int,
    client_id: int = None,
    name: str = None,
    is_billable: bool = None,
    bill_by: str = None,
    budget_by: str = None,
    code: str = None,
    is_active: bool = None,
    is_fixed_fee: bool = None,
    hourly_rate: float = None,
    budget: float = None,
    budget_is_monthly: bool = None,
    notify_when_over_budget: bool = None,
    over_budget_notification_percentage: float = None,
    show_budget_to_all: bool = None,
    cost_budget: float = None,
    cost_budget_include_expenses: bool = None,
    fee: float = None,
    notes: str = None,
    starts_on: str = None,
    ends_on: str = None,
):
    """Update an existing project.

    Args:
        project_id: The ID of the project to update
        client_id: The ID of the client to associate with the project
        name: The name of the project
        is_billable: Whether the project is billable or not
        bill_by: The method by which the project is invoiced - "Project", "Tasks", "People", or "none"
        budget_by: The method by which the project is budgeted - "project", "project_cost", "task", "task_fees", "person", or "none"
        code: The project code
        is_active: Whether the project is active or archived
        is_fixed_fee: Whether the project is a fixed-fee project or not
        hourly_rate: Rate for projects billed by Project Hourly Rate
        budget: The budget in hours for the project when budget_by is "project" or "none"
        budget_is_monthly: Option to have the budget reset every month
        notify_when_over_budget: Whether project managers should be notified when the project goes over budget
        over_budget_notification_percentage: Percentage value used to trigger over budget email alerts (0.0 to 100.0)
        show_budget_to_all: Option to show project budget to all employees (defaults to project managers and up)
        cost_budget: The monetary budget for the project when budget_by is "project_cost"
        cost_budget_include_expenses: Option for budget of "project_cost" to include tracked expenses
        fee: The amount you plan to invoice for the project (only used by fixed-fee projects)
        notes: Project notes
        starts_on: Date the project was started (YYYY-MM-DD)
        ends_on: Date the project will end (YYYY-MM-DD)
    """
    params = build_body(
        client_id=client_id,
        name=name,
        is_billable=is_billable,
        bill_by=bill_by,
        budget_by=budget_by,
        code=code,
        is_active=is_active,
        is_fixed_fee=is_fixed_fee,
        hourly_rate=hourly_rate,
        budget=budget,
        budget_is_monthly=budget_is_monthly,
        notify_when_over_budget=notify_when_over_budget,
        over_budget_notification_percentage=over_budget_notification_percentage,
        show_budget_to_all=show_budget_to_all,
        cost_budget=cost_budget,
        cost_budget_include_expenses=cost_budget_include_expenses,
        fee=fee,
        notes=notes,
        starts_on=starts_on,
        ends_on=ends_on,
    )
    response = await harvest_request(f"projects/{project_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_task(
    name: str,
    billable_by_default: bool = None,
    default_hourly_rate: float = None,
    is_default: bool = None,
    is_active: bool = None,
):
    """Create a new task.

    Args:
        name: The name of the task
        billable_by_default: Whether the task should be billable by default when added to a project
        default_hourly_rate: The default hourly rate for the task when added to a project
        is_default: Whether the task should be added to new projects by default
        is_active: Whether the task is active or archived
    """
    params = build_body(
        name=name,
        billable_by_default=billable_by_default,
        default_hourly_rate=default_hourly_rate,
        is_default=is_default,
        is_active=is_active,
    )
    response = await harvest_request("tasks", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_project_task_assignment(
    project_id: int,
    task_id: int,
    is_active: bool = None,
    billable: bool = None,
    hourly_rate: float = None,
    budget: float = None,
):
    """Assign a task to a project.

    Args:
        project_id: The ID of the project
        task_id: The ID of the task to assign
        is_active: Whether the task assignment is active
        billable: Whether the task is billable for this project
        hourly_rate: Rate for this task when bill_by is "Tasks"
        budget: Budget for this task when budget_by is "task"
    """
    params = build_body(
        task_id=task_id,
        is_active=is_active,
        billable=billable,
        hourly_rate=hourly_rate,
        budget=budget,
    )
    response = await harvest_request(f"projects/{project_id}/task_assignments", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_project_user_assignment(
    project_id: int,
    user_id: int,
    is_active: bool = None,
    is_project_manager: bool = None,
    use_default_rates: bool = None,
    hourly_rate: float = None,
    budget: float = None,
):
    """Assign a user to a project.

    Args:
        project_id: The ID of the project
        user_id: The ID of the user to assign
        is_active: Whether the user assignment is active
        is_project_manager: Whether the user should be a project manager for this project
        use_default_rates: Whether to use the user's default rates for this project
        hourly_rate: Rate for this user when bill_by is "People"
        budget: Budget for this user when budget_by is "person"
    """
    params = build_body(
        user_id=user_id,
        is_active=is_active,
        is_project_manager=is_project_manager,
        use_default_rates=use_default_rates,
        hourly_rate=hourly_rate,
        budget=budget,
    )
    response = await harvest_request(f"projects/{project_id}/user_assignments", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_invoice(
    invoice_id: int,
    line_items: list[dict] = None,
    client_id: int = None,
    number: str = None,
    purchase_order: str = None,
    tax: float = None,
    tax2: float = None,
    discount: float = None,
    subject: str = None,
    notes: str = None,
    currency: str = None,
    issue_date: str = None,
    due_date: str = None,
    payment_term: str = None,
):
    """Update an existing invoice, including adding, editing, or removing line items.

    To edit line items, pass a list of line item objects in `line_items`. Each object can be:
      - A NEW line item: omit `id`. Fields: kind (required, e.g. "Service" or "Product"),
        description, quantity, unit_price, project_id, taxed, taxed2.
      - An UPDATE to an existing line item: include `id` of the existing line item plus any
        fields you want to change (description, quantity, unit_price, kind, project_id,
        taxed, taxed2).
      - A REMOVAL: include `id` of the existing line item and `_destroy: true`.

    Line items not mentioned in the list are left unchanged.

    Example line_items:
      [
        {"id": 123, "description": "Updated description", "quantity": 2, "unit_price": 150.0},
        {"id": 456, "_destroy": True},
        {"kind": "Service", "description": "New work", "quantity": 5, "unit_price": 100.0}
      ]

    Args:
        invoice_id: The ID of the invoice to update
        line_items: List of line item objects to create, update, or remove (see description)
        client_id: Change the client associated with this invoice
        number: Update the invoice number
        purchase_order: The purchase order number
        tax: First additional tax percentage
        tax2: Second additional tax percentage
        discount: Discount percentage
        subject: The invoice subject
        notes: Additional notes
        currency: ISO 4217 currency code
        issue_date: Date the invoice was issued (YYYY-MM-DD)
        due_date: Date the invoice is due (YYYY-MM-DD)
        payment_term: Payment term: upon receipt, net 15, net 30, net 45, net 60, or custom
    """
    params = build_body(
        line_items=line_items,
        client_id=client_id,
        number=number,
        purchase_order=purchase_order,
        tax=tax,
        tax2=tax2,
        discount=discount,
        subject=subject,
        notes=notes,
        currency=currency,
        issue_date=issue_date,
        due_date=due_date,
        payment_term=payment_term,
    )
    response = await harvest_request(f"invoices/{invoice_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# Clients (update, delete)
# -----------------------------------------------------------------------------


@mcp.tool()
@requires_write
async def update_client(
    client_id: int,
    name: str = None,
    is_active: bool = None,
    address: str = None,
    currency: str = None,
):
    """Update an existing client.

    Args:
        client_id: The ID of the client to update
        name: The name of the client
        is_active: Whether the client is active or archived
        address: The physical address of the client
        currency: ISO 4217 currency code
    """
    params = build_body(name=name, is_active=is_active, address=address, currency=currency)
    response = await harvest_request(f"clients/{client_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_client(client_id: int):
    """Delete a client. Deleting a client is only possible if it has no projects, invoices, or estimates.

    Args:
        client_id: The ID of the client to delete
    """
    await harvest_request(f"clients/{client_id}", method="DELETE")
    return json.dumps({"deleted": True, "client_id": client_id}, indent=2)


# -----------------------------------------------------------------------------
# Client Contacts
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_contacts(
    client_id: int = None,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all client contacts.

    Args:
        client_id: Filter by client ID
        updated_since: Only return contacts updated since the given date/time (ISO 8601)
        page: The page number for pagination
        per_page: The number of records per page (1-2000)
    """
    params = build_query(client_id=client_id, updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("contacts", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_contact(contact_id: int):
    """Retrieve a specific client contact.

    Args:
        contact_id: The ID of the contact
    """
    response = await harvest_request(f"contacts/{contact_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_contact(
    client_id: int,
    first_name: str,
    title: str = None,
    last_name: str = None,
    email: str = None,
    phone_office: str = None,
    phone_mobile: str = None,
    fax: str = None,
):
    """Create a new client contact.

    Args:
        client_id: The ID of the client to associate the contact with
        first_name: The first name of the contact
        title: The title of the contact
        last_name: The last name of the contact
        email: The email address of the contact
        phone_office: The office phone number
        phone_mobile: The mobile phone number
        fax: The fax number
    """
    params = build_body(
        client_id=client_id,
        first_name=first_name,
        title=title,
        last_name=last_name,
        email=email,
        phone_office=phone_office,
        phone_mobile=phone_mobile,
        fax=fax,
    )
    response = await harvest_request("contacts", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_contact(
    contact_id: int,
    client_id: int = None,
    title: str = None,
    first_name: str = None,
    last_name: str = None,
    email: str = None,
    phone_office: str = None,
    phone_mobile: str = None,
    fax: str = None,
):
    """Update an existing client contact.

    Args:
        contact_id: The ID of the contact to update
        client_id: The ID of the client to associate with this contact
        title: The title of the contact
        first_name: The first name
        last_name: The last name
        email: The email address
        phone_office: The office phone
        phone_mobile: The mobile phone
        fax: The fax number
    """
    params = build_body(
        client_id=client_id,
        title=title,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_office=phone_office,
        phone_mobile=phone_mobile,
        fax=fax,
    )
    response = await harvest_request(f"contacts/{contact_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_contact(contact_id: int):
    """Delete a client contact.

    Args:
        contact_id: The ID of the contact to delete
    """
    await harvest_request(f"contacts/{contact_id}", method="DELETE")
    return json.dumps({"deleted": True, "contact_id": contact_id}, indent=2)


# -----------------------------------------------------------------------------
# Company
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_company():
    """Retrieve the authenticated company's details."""
    response = await harvest_request("company")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_company(
    wants_timestamp_timers: bool = None,
    weekly_capacity: int = None,
):
    """Update the authenticated company.

    Args:
        wants_timestamp_timers: Whether time is tracked via duration or start/end times
        weekly_capacity: Weekly capacity in seconds
    """
    params = build_body(
        wants_timestamp_timers=wants_timestamp_timers,
        weekly_capacity=weekly_capacity,
    )
    response = await harvest_request("company", params, method="PATCH")
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# Estimate Item Categories
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_estimate_item_categories(
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all estimate item categories.

    Args:
        updated_since: Only return categories updated since the given date/time (ISO 8601)
        page: The page number
        per_page: Records per page (1-2000)
    """
    params = build_query(updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("estimate_item_categories", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_estimate_item_category(category_id: int):
    """Retrieve a specific estimate item category.

    Args:
        category_id: The ID of the estimate item category
    """
    response = await harvest_request(f"estimate_item_categories/{category_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_estimate_item_category(name: str):
    """Create a new estimate item category.

    Args:
        name: The name of the estimate item category
    """
    response = await harvest_request("estimate_item_categories", build_body(name=name), method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_estimate_item_category(category_id: int, name: str = None):
    """Update an estimate item category.

    Args:
        category_id: The ID of the category to update
        name: The new name
    """
    response = await harvest_request(
        f"estimate_item_categories/{category_id}", build_body(name=name), method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_estimate_item_category(category_id: int):
    """Delete an estimate item category.

    Args:
        category_id: The ID of the category to delete
    """
    await harvest_request(f"estimate_item_categories/{category_id}", method="DELETE")
    return json.dumps({"deleted": True, "category_id": category_id}, indent=2)


# -----------------------------------------------------------------------------
# Estimates
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_estimates(
    client_id: int = None,
    updated_since: str = None,
    from_date: str = None,
    to_date: str = None,
    state: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all estimates.

    Args:
        client_id: Filter by client ID
        updated_since: Only estimates updated since the given date/time (ISO 8601)
        from_date: Only estimates with an issue_date on or after this (YYYY-MM-DD)
        to_date: Only estimates with an issue_date on or before this (YYYY-MM-DD)
        state: Filter by state: draft, sent, accepted, declined
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(
        client_id=client_id,
        updated_since=updated_since,
        state=state,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("estimates", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_estimate(estimate_id: int):
    """Retrieve a specific estimate.

    Args:
        estimate_id: The ID of the estimate
    """
    response = await harvest_request(f"estimates/{estimate_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_estimate(
    client_id: int,
    number: str = None,
    purchase_order: str = None,
    tax: float = None,
    tax2: float = None,
    discount: float = None,
    subject: str = None,
    notes: str = None,
    currency: str = None,
    issue_date: str = None,
    line_items: list[dict] = None,
):
    """Create a new estimate.

    Args:
        client_id: The ID of the client this estimate is for
        number: Estimate number (auto-generated if omitted)
        purchase_order: Purchase order number
        tax: First tax percentage
        tax2: Second tax percentage
        discount: Discount percentage
        subject: The estimate subject
        notes: Notes
        currency: ISO 4217 currency code
        issue_date: Issue date (YYYY-MM-DD)
        line_items: List of line item dicts: {kind, description, quantity, unit_price, taxed, taxed2, item_category_id}
    """
    params = build_body(
        client_id=client_id,
        number=number,
        purchase_order=purchase_order,
        tax=tax,
        tax2=tax2,
        discount=discount,
        subject=subject,
        notes=notes,
        currency=currency,
        issue_date=issue_date,
        line_items=line_items,
    )
    response = await harvest_request("estimates", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_estimate(
    estimate_id: int,
    client_id: int = None,
    number: str = None,
    purchase_order: str = None,
    tax: float = None,
    tax2: float = None,
    discount: float = None,
    subject: str = None,
    notes: str = None,
    currency: str = None,
    issue_date: str = None,
    line_items: list[dict] = None,
):
    """Update an existing estimate. Line items support create/update/_destroy the same as invoices.

    Args:
        estimate_id: The ID of the estimate to update
        client_id: Client ID
        number: Estimate number
        purchase_order: Purchase order number
        tax: First tax percentage
        tax2: Second tax percentage
        discount: Discount percentage
        subject: Estimate subject
        notes: Notes
        currency: ISO 4217 currency code
        issue_date: Issue date (YYYY-MM-DD)
        line_items: Line item edits ({id,...}, {id,_destroy:true}, or new item)
    """
    params = build_body(
        client_id=client_id,
        number=number,
        purchase_order=purchase_order,
        tax=tax,
        tax2=tax2,
        discount=discount,
        subject=subject,
        notes=notes,
        currency=currency,
        issue_date=issue_date,
        line_items=line_items,
    )
    response = await harvest_request(f"estimates/{estimate_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_estimate(estimate_id: int):
    """Delete an estimate.

    Args:
        estimate_id: The ID of the estimate to delete
    """
    await harvest_request(f"estimates/{estimate_id}", method="DELETE")
    return json.dumps({"deleted": True, "estimate_id": estimate_id}, indent=2)


# -----------------------------------------------------------------------------
# Estimate Messages
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_estimate_messages(
    estimate_id: int,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all messages for an estimate.

    Args:
        estimate_id: The ID of the estimate
        updated_since: Only return messages updated since the given date/time (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request(f"estimates/{estimate_id}/messages", params)
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_estimate_message(
    estimate_id: int,
    recipients: list[dict] = None,
    subject: str = None,
    body: str = None,
    send_me_a_copy: bool = None,
    event_type: str = None,
):
    """Create a message for an estimate or mark it (send/accept/decline/re-open/view).

    Args:
        estimate_id: The ID of the estimate
        recipients: List of {name, email} recipient dicts
        subject: The message subject
        body: The message body
        send_me_a_copy: Whether to send a copy to the sender
        event_type: Event type: send, accept, decline, re-open, view
    """
    params = build_body(
        recipients=recipients,
        subject=subject,
        body=body,
        send_me_a_copy=send_me_a_copy,
        event_type=event_type,
    )
    response = await harvest_request(f"estimates/{estimate_id}/messages", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_estimate_message(estimate_id: int, message_id: int):
    """Delete an estimate message.

    Args:
        estimate_id: The ID of the estimate
        message_id: The ID of the message to delete
    """
    await harvest_request(f"estimates/{estimate_id}/messages/{message_id}", method="DELETE")
    return json.dumps({"deleted": True, "message_id": message_id}, indent=2)


# -----------------------------------------------------------------------------
# Expense Categories
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_expense_categories(
    is_active: bool = None,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all expense categories.

    Args:
        is_active: Filter by active/archived
        updated_since: Only return categories updated since the given date/time (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(is_active=is_active, updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("expense_categories", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_expense_category(category_id: int):
    """Retrieve a specific expense category.

    Args:
        category_id: The ID of the expense category
    """
    response = await harvest_request(f"expense_categories/{category_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_expense_category(
    name: str,
    unit_name: str = None,
    unit_price: float = None,
    is_active: bool = None,
):
    """Create a new expense category.

    Args:
        name: The name of the expense category
        unit_name: Unit name (e.g. "miles")
        unit_price: Unit price
        is_active: Whether active
    """
    params = build_body(name=name, unit_name=unit_name, unit_price=unit_price, is_active=is_active)
    response = await harvest_request("expense_categories", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_expense_category(
    category_id: int,
    name: str = None,
    unit_name: str = None,
    unit_price: float = None,
    is_active: bool = None,
):
    """Update an expense category.

    Args:
        category_id: The ID of the expense category to update
        name: Name
        unit_name: Unit name
        unit_price: Unit price
        is_active: Whether active
    """
    params = build_body(name=name, unit_name=unit_name, unit_price=unit_price, is_active=is_active)
    response = await harvest_request(f"expense_categories/{category_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_expense_category(category_id: int):
    """Delete an expense category.

    Args:
        category_id: The ID of the expense category to delete
    """
    await harvest_request(f"expense_categories/{category_id}", method="DELETE")
    return json.dumps({"deleted": True, "category_id": category_id}, indent=2)


# -----------------------------------------------------------------------------
# Expenses
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_expenses(
    user_id: int = None,
    client_id: int = None,
    project_id: int = None,
    is_billed: bool = None,
    updated_since: str = None,
    from_date: str = None,
    to_date: str = None,
    page: int = None,
    per_page: int = None,
):
    """List expenses with optional filtering.

    Args:
        user_id: Filter by user ID
        client_id: Filter by client ID
        project_id: Filter by project ID
        is_billed: Filter by billed/unbilled
        updated_since: Only expenses updated since the given date/time (ISO 8601)
        from_date: Only expenses with spent_date on or after (YYYY-MM-DD)
        to_date: Only expenses with spent_date on or before (YYYY-MM-DD)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(
        user_id=user_id,
        client_id=client_id,
        project_id=project_id,
        is_billed=is_billed,
        updated_since=updated_since,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("expenses", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_expense(expense_id: int):
    """Retrieve a specific expense.

    Args:
        expense_id: The ID of the expense
    """
    response = await harvest_request(f"expenses/{expense_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_expense(
    project_id: int,
    expense_category_id: int,
    spent_date: str,
    user_id: int = None,
    units: float = None,
    total_cost: float = None,
    notes: str = None,
    billable: bool = None,
):
    """Create a new expense.

    Args:
        project_id: Project ID
        expense_category_id: Expense category ID
        spent_date: Date expense was incurred (YYYY-MM-DD)
        user_id: User ID (defaults to authenticated user)
        units: Quantity of units (for unit-based categories)
        total_cost: Total cost
        notes: Notes
        billable: Whether billable to the client
    """
    params = build_body(
        project_id=project_id,
        expense_category_id=expense_category_id,
        spent_date=spent_date,
        user_id=user_id,
        units=units,
        total_cost=total_cost,
        notes=notes,
        billable=billable,
    )
    response = await harvest_request("expenses", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_expense(
    expense_id: int,
    project_id: int = None,
    expense_category_id: int = None,
    spent_date: str = None,
    units: float = None,
    total_cost: float = None,
    notes: str = None,
    billable: bool = None,
):
    """Update an existing expense.

    Args:
        expense_id: The ID of the expense to update
        project_id: Project ID
        expense_category_id: Expense category ID
        spent_date: Date (YYYY-MM-DD)
        units: Quantity
        total_cost: Total cost
        notes: Notes
        billable: Whether billable
    """
    params = build_body(
        project_id=project_id,
        expense_category_id=expense_category_id,
        spent_date=spent_date,
        units=units,
        total_cost=total_cost,
        notes=notes,
        billable=billable,
    )
    response = await harvest_request(f"expenses/{expense_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_expense(expense_id: int):
    """Delete an expense.

    Args:
        expense_id: The ID of the expense to delete
    """
    await harvest_request(f"expenses/{expense_id}", method="DELETE")
    return json.dumps({"deleted": True, "expense_id": expense_id}, indent=2)


# -----------------------------------------------------------------------------
# Invoice Item Categories
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_invoice_item_categories(
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all invoice item categories.

    Args:
        updated_since: Only categories updated since (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("invoice_item_categories", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_invoice_item_category(category_id: int):
    """Retrieve a specific invoice item category.

    Args:
        category_id: The ID of the category
    """
    response = await harvest_request(f"invoice_item_categories/{category_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_invoice_item_category(name: str):
    """Create a new invoice item category.

    Args:
        name: The name of the category
    """
    response = await harvest_request("invoice_item_categories", build_body(name=name), method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_invoice_item_category(category_id: int, name: str = None):
    """Update an invoice item category.

    Args:
        category_id: The ID of the category to update
        name: New name
    """
    response = await harvest_request(
        f"invoice_item_categories/{category_id}", build_body(name=name), method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_invoice_item_category(category_id: int):
    """Delete an invoice item category.

    Args:
        category_id: The ID of the category to delete
    """
    await harvest_request(f"invoice_item_categories/{category_id}", method="DELETE")
    return json.dumps({"deleted": True, "category_id": category_id}, indent=2)


# -----------------------------------------------------------------------------
# Invoices (free-form create, delete)
# -----------------------------------------------------------------------------


@mcp.tool()
@requires_write
async def create_invoice(
    client_id: int,
    retainer_id: int = None,
    estimate_id: int = None,
    number: str = None,
    purchase_order: str = None,
    tax: float = None,
    tax2: float = None,
    discount: float = None,
    subject: str = None,
    notes: str = None,
    currency: str = None,
    issue_date: str = None,
    due_date: str = None,
    payment_term: str = None,
    line_items: list[dict] = None,
):
    """Create a free-form invoice (for time/expense-based invoices use create_invoice_from_time_and_expenses).

    Args:
        client_id: Client ID
        retainer_id: Associated retainer ID
        estimate_id: Associated estimate ID
        number: Invoice number
        purchase_order: Purchase order
        tax: First tax percentage
        tax2: Second tax percentage
        discount: Discount percentage
        subject: Invoice subject
        notes: Notes
        currency: ISO 4217 code
        issue_date: Issue date (YYYY-MM-DD)
        due_date: Due date (YYYY-MM-DD)
        payment_term: Payment term
        line_items: List of line item dicts {kind, description, quantity, unit_price, taxed, taxed2, project_id, item_category_id}
    """
    params = build_body(
        client_id=client_id,
        retainer_id=retainer_id,
        estimate_id=estimate_id,
        number=number,
        purchase_order=purchase_order,
        tax=tax,
        tax2=tax2,
        discount=discount,
        subject=subject,
        notes=notes,
        currency=currency,
        issue_date=issue_date,
        due_date=due_date,
        payment_term=payment_term,
        line_items=line_items,
    )
    response = await harvest_request("invoices", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_invoice(invoice_id: int):
    """Delete an invoice.

    Args:
        invoice_id: The ID of the invoice to delete
    """
    await harvest_request(f"invoices/{invoice_id}", method="DELETE")
    return json.dumps({"deleted": True, "invoice_id": invoice_id}, indent=2)


# -----------------------------------------------------------------------------
# Invoice Messages
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_invoice_messages(
    invoice_id: int,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all messages for an invoice.

    Args:
        invoice_id: The ID of the invoice
        updated_since: Only messages updated since (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request(f"invoices/{invoice_id}/messages", params)
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_invoice_message(
    invoice_id: int,
    recipients: list[dict] = None,
    subject: str = None,
    body: str = None,
    include_link_to_client_invoice: bool = None,
    attach_pdf: bool = None,
    send_me_a_copy: bool = None,
    thank_you: bool = None,
    event_type: str = None,
    payment_options: list[str] = None,
):
    """Create a message for an invoice or mark an event (send/close/draft/re-open/view).

    Args:
        invoice_id: The ID of the invoice
        recipients: List of {name, email} recipient dicts
        subject: Message subject
        body: Message body
        include_link_to_client_invoice: Include a link to the client invoice
        attach_pdf: Attach a PDF of the invoice
        send_me_a_copy: Send a copy to the sender
        thank_you: Mark this as a thank-you email
        event_type: Event type: send, close, draft, re-open, view
        payment_options: Payment options (e.g. ["credit_card"])
    """
    params = build_body(
        recipients=recipients,
        subject=subject,
        body=body,
        include_link_to_client_invoice=include_link_to_client_invoice,
        attach_pdf=attach_pdf,
        send_me_a_copy=send_me_a_copy,
        thank_you=thank_you,
        event_type=event_type,
        payment_options=payment_options,
    )
    response = await harvest_request(f"invoices/{invoice_id}/messages", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_invoice_message(invoice_id: int, message_id: int):
    """Delete an invoice message.

    Args:
        invoice_id: The ID of the invoice
        message_id: The ID of the message to delete
    """
    await harvest_request(f"invoices/{invoice_id}/messages/{message_id}", method="DELETE")
    return json.dumps({"deleted": True, "message_id": message_id}, indent=2)


# -----------------------------------------------------------------------------
# Invoice Payments (delete)
# -----------------------------------------------------------------------------


@mcp.tool()
@requires_write
async def delete_invoice_payment(invoice_id: int, payment_id: int):
    """Delete an invoice payment.

    Args:
        invoice_id: The ID of the invoice
        payment_id: The ID of the payment to delete
    """
    await harvest_request(f"invoices/{invoice_id}/payments/{payment_id}", method="DELETE")
    return json.dumps({"deleted": True, "payment_id": payment_id}, indent=2)


# -----------------------------------------------------------------------------
# Projects (delete)
# -----------------------------------------------------------------------------


@mcp.tool()
@requires_write
async def delete_project(project_id: int):
    """Delete a project. Only possible if the project has no time/expenses/invoices/estimates/running timers.

    Args:
        project_id: The ID of the project to delete
    """
    await harvest_request(f"projects/{project_id}", method="DELETE")
    return json.dumps({"deleted": True, "project_id": project_id}, indent=2)


# -----------------------------------------------------------------------------
# Project Task Assignments (get, update, delete)
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_project_task_assignment(project_id: int, task_assignment_id: int):
    """Retrieve a specific task assignment on a project.

    Args:
        project_id: The ID of the project
        task_assignment_id: The ID of the task assignment
    """
    response = await harvest_request(f"projects/{project_id}/task_assignments/{task_assignment_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_project_task_assignment(
    project_id: int,
    task_assignment_id: int,
    is_active: bool = None,
    billable: bool = None,
    hourly_rate: float = None,
    budget: float = None,
):
    """Update a project task assignment.

    Args:
        project_id: The ID of the project
        task_assignment_id: The ID of the task assignment
        is_active: Whether active
        billable: Whether billable
        hourly_rate: Hourly rate
        budget: Budget
    """
    params = build_body(is_active=is_active, billable=billable, hourly_rate=hourly_rate, budget=budget)
    response = await harvest_request(
        f"projects/{project_id}/task_assignments/{task_assignment_id}", params, method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_project_task_assignment(project_id: int, task_assignment_id: int):
    """Remove a task assignment from a project.

    Args:
        project_id: The ID of the project
        task_assignment_id: The ID of the task assignment to delete
    """
    await harvest_request(
        f"projects/{project_id}/task_assignments/{task_assignment_id}", method="DELETE"
    )
    return json.dumps({"deleted": True, "task_assignment_id": task_assignment_id}, indent=2)


# -----------------------------------------------------------------------------
# Project User Assignments (get, update, delete)
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_project_user_assignment(project_id: int, user_assignment_id: int):
    """Retrieve a specific user assignment on a project.

    Args:
        project_id: The ID of the project
        user_assignment_id: The ID of the user assignment
    """
    response = await harvest_request(f"projects/{project_id}/user_assignments/{user_assignment_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_project_user_assignment(
    project_id: int,
    user_assignment_id: int,
    is_active: bool = None,
    is_project_manager: bool = None,
    use_default_rates: bool = None,
    hourly_rate: float = None,
    budget: float = None,
):
    """Update a project user assignment.

    Args:
        project_id: The ID of the project
        user_assignment_id: The ID of the user assignment
        is_active: Whether active
        is_project_manager: Whether the user is a project manager
        use_default_rates: Whether to use the user's default rates
        hourly_rate: Hourly rate
        budget: Budget
    """
    params = build_body(
        is_active=is_active,
        is_project_manager=is_project_manager,
        use_default_rates=use_default_rates,
        hourly_rate=hourly_rate,
        budget=budget,
    )
    response = await harvest_request(
        f"projects/{project_id}/user_assignments/{user_assignment_id}", params, method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_project_user_assignment(project_id: int, user_assignment_id: int):
    """Remove a user assignment from a project.

    Args:
        project_id: The ID of the project
        user_assignment_id: The ID of the user assignment to delete
    """
    await harvest_request(
        f"projects/{project_id}/user_assignments/{user_assignment_id}", method="DELETE"
    )
    return json.dumps({"deleted": True, "user_assignment_id": user_assignment_id}, indent=2)


# -----------------------------------------------------------------------------
# Task Assignments (top-level list)
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_task_assignments(
    is_active: bool = None,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all task assignments across the account.

    Args:
        is_active: Filter by active/inactive
        updated_since: Only assignments updated since (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(is_active=is_active, updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("task_assignments", params)
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# User Assignments (top-level list)
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_user_assignments(
    is_active: bool = None,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List all user assignments across the account.

    Args:
        is_active: Filter by active/inactive
        updated_since: Only assignments updated since (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(is_active=is_active, updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("user_assignments", params)
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_expense_categories_report(
    from_date: str,
    to_date: str,
    page: int = None,
    per_page: int = None,
):
    """Expenses report grouped by expense category.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        page: Page number
        per_page: Records per page
    """
    params = build_query(page=page, per_page=per_page, **{"from": from_date, "to": to_date})
    response = await harvest_request("reports/expenses/categories", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_clients_expenses_report(
    from_date: str,
    to_date: str,
    page: int = None,
    per_page: int = None,
):
    """Expenses report grouped by client.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        page: Page number
        per_page: Records per page
    """
    params = build_query(page=page, per_page=per_page, **{"from": from_date, "to": to_date})
    response = await harvest_request("reports/expenses/clients", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_projects_expenses_report(
    from_date: str,
    to_date: str,
    page: int = None,
    per_page: int = None,
):
    """Expenses report grouped by project.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        page: Page number
        per_page: Records per page
    """
    params = build_query(page=page, per_page=per_page, **{"from": from_date, "to": to_date})
    response = await harvest_request("reports/expenses/projects", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_team_expenses_report(
    from_date: str,
    to_date: str,
    page: int = None,
    per_page: int = None,
):
    """Expenses report grouped by team member.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        page: Page number
        per_page: Records per page
    """
    params = build_query(page=page, per_page=per_page, **{"from": from_date, "to": to_date})
    response = await harvest_request("reports/expenses/team", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_project_budget_report(
    is_active: bool = None,
    page: int = None,
    per_page: int = None,
):
    """Project budget report for active/inactive projects.

    Args:
        is_active: Filter by active projects
        page: Page number
        per_page: Records per page
    """
    params = build_query(is_active=is_active, page=page, per_page=per_page)
    response = await harvest_request("reports/project_budget", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_clients_time_report(
    from_date: str,
    to_date: str,
    include_fixed_fee: bool = None,
    page: int = None,
    per_page: int = None,
):
    """Time report grouped by client.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        include_fixed_fee: Include fixed-fee projects
        page: Page number
        per_page: Records per page
    """
    params = build_query(
        include_fixed_fee=include_fixed_fee,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("reports/time/clients", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_projects_time_report(
    from_date: str,
    to_date: str,
    include_fixed_fee: bool = None,
    page: int = None,
    per_page: int = None,
):
    """Time report grouped by project.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        include_fixed_fee: Include fixed-fee projects
        page: Page number
        per_page: Records per page
    """
    params = build_query(
        include_fixed_fee=include_fixed_fee,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("reports/time/projects", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_tasks_time_report(
    from_date: str,
    to_date: str,
    include_fixed_fee: bool = None,
    page: int = None,
    per_page: int = None,
):
    """Time report grouped by task.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        include_fixed_fee: Include fixed-fee projects
        page: Page number
        per_page: Records per page
    """
    params = build_query(
        include_fixed_fee=include_fixed_fee,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("reports/time/tasks", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_team_time_report(
    from_date: str,
    to_date: str,
    include_fixed_fee: bool = None,
    page: int = None,
    per_page: int = None,
):
    """Time report grouped by team member.

    Args:
        from_date: Start date (YYYY-MM-DD, required)
        to_date: End date (YYYY-MM-DD, required)
        include_fixed_fee: Include fixed-fee projects
        page: Page number
        per_page: Records per page
    """
    params = build_query(
        include_fixed_fee=include_fixed_fee,
        page=page,
        per_page=per_page,
        **{"from": from_date, "to": to_date},
    )
    response = await harvest_request("reports/time/team", params)
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# Roles
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_roles(page: int = None, per_page: int = None):
    """List all roles.

    Args:
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(page=page, per_page=per_page)
    response = await harvest_request("roles", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_role(role_id: int):
    """Retrieve a specific role.

    Args:
        role_id: The ID of the role
    """
    response = await harvest_request(f"roles/{role_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_role(name: str, user_ids: list[int] = None):
    """Create a new role.

    Args:
        name: The name of the role
        user_ids: List of user IDs to assign to this role
    """
    response = await harvest_request("roles", build_body(name=name, user_ids=user_ids), method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_role(role_id: int, name: str = None, user_ids: list[int] = None):
    """Update a role.

    Args:
        role_id: The ID of the role to update
        name: New name
        user_ids: List of user IDs assigned to this role
    """
    response = await harvest_request(
        f"roles/{role_id}", build_body(name=name, user_ids=user_ids), method="PATCH"
    )
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_role(role_id: int):
    """Delete a role.

    Args:
        role_id: The ID of the role to delete
    """
    await harvest_request(f"roles/{role_id}", method="DELETE")
    return json.dumps({"deleted": True, "role_id": role_id}, indent=2)


# -----------------------------------------------------------------------------
# Tasks (get, update, delete)
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_task(task_id: int):
    """Retrieve a specific task.

    Args:
        task_id: The ID of the task
    """
    response = await harvest_request(f"tasks/{task_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_task(
    task_id: int,
    name: str = None,
    billable_by_default: bool = None,
    default_hourly_rate: float = None,
    is_default: bool = None,
    is_active: bool = None,
):
    """Update an existing task.

    Args:
        task_id: The ID of the task to update
        name: Name
        billable_by_default: Whether billable by default when added to a project
        default_hourly_rate: Default hourly rate
        is_default: Whether added to new projects by default
        is_active: Whether active
    """
    params = build_body(
        name=name,
        billable_by_default=billable_by_default,
        default_hourly_rate=default_hourly_rate,
        is_default=is_default,
        is_active=is_active,
    )
    response = await harvest_request(f"tasks/{task_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_task(task_id: int):
    """Delete a task. Only possible if there are no associated time entries.

    Args:
        task_id: The ID of the task to delete
    """
    await harvest_request(f"tasks/{task_id}", method="DELETE")
    return json.dumps({"deleted": True, "task_id": task_id}, indent=2)


# -----------------------------------------------------------------------------
# Time Entries (get, restart, external_reference delete)
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_time_entry(time_entry_id: int):
    """Retrieve a specific time entry.

    Args:
        time_entry_id: The ID of the time entry
    """
    response = await harvest_request(f"time_entries/{time_entry_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def restart_time_entry(time_entry_id: int):
    """Restart a stopped time entry.

    Args:
        time_entry_id: The ID of the time entry to restart
    """
    response = await harvest_request(f"time_entries/{time_entry_id}/restart", method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_time_entry_external_reference(time_entry_id: int):
    """Delete the external reference on a time entry.

    Args:
        time_entry_id: The ID of the time entry
    """
    await harvest_request(f"time_entries/{time_entry_id}/external_reference", method="DELETE")
    return json.dumps({"deleted": True, "time_entry_id": time_entry_id}, indent=2)


# -----------------------------------------------------------------------------
# Users (create, update, delete, /me, project assignments)
# -----------------------------------------------------------------------------


@mcp.tool()
async def get_current_user():
    """Retrieve the currently authenticated user."""
    response = await harvest_request("users/me")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_user(
    first_name: str,
    last_name: str,
    email: str,
    timezone: str = None,
    has_access_to_all_future_projects: bool = None,
    is_contractor: bool = None,
    is_active: bool = None,
    weekly_capacity: int = None,
    default_hourly_rate: float = None,
    cost_rate: float = None,
    roles: list[str] = None,
    access_roles: list[str] = None,
):
    """Create a new user.

    Args:
        first_name: First name
        last_name: Last name
        email: Email address
        timezone: IANA timezone name
        has_access_to_all_future_projects: Auto-access future projects
        is_contractor: Whether the user is a contractor
        is_active: Whether active
        weekly_capacity: Weekly capacity (seconds)
        default_hourly_rate: Default hourly rate
        cost_rate: Cost rate
        roles: Role names
        access_roles: Access role names (e.g. "administrator", "manager", "member")
    """
    params = build_body(
        first_name=first_name,
        last_name=last_name,
        email=email,
        timezone=timezone,
        has_access_to_all_future_projects=has_access_to_all_future_projects,
        is_contractor=is_contractor,
        is_active=is_active,
        weekly_capacity=weekly_capacity,
        default_hourly_rate=default_hourly_rate,
        cost_rate=cost_rate,
        roles=roles,
        access_roles=access_roles,
    )
    response = await harvest_request("users", params, method="POST")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_user(
    user_id: int,
    first_name: str = None,
    last_name: str = None,
    email: str = None,
    timezone: str = None,
    has_access_to_all_future_projects: bool = None,
    is_contractor: bool = None,
    is_active: bool = None,
    weekly_capacity: int = None,
    default_hourly_rate: float = None,
    cost_rate: float = None,
    roles: list[str] = None,
    access_roles: list[str] = None,
):
    """Update an existing user.

    Args:
        user_id: The ID of the user to update
        first_name: First name
        last_name: Last name
        email: Email
        timezone: Timezone
        has_access_to_all_future_projects: Auto-access future projects
        is_contractor: Whether contractor
        is_active: Whether active
        weekly_capacity: Weekly capacity (seconds)
        default_hourly_rate: Default hourly rate
        cost_rate: Cost rate
        roles: Role names
        access_roles: Access role names
    """
    params = build_body(
        first_name=first_name,
        last_name=last_name,
        email=email,
        timezone=timezone,
        has_access_to_all_future_projects=has_access_to_all_future_projects,
        is_contractor=is_contractor,
        is_active=is_active,
        weekly_capacity=weekly_capacity,
        default_hourly_rate=default_hourly_rate,
        cost_rate=cost_rate,
        roles=roles,
        access_roles=access_roles,
    )
    response = await harvest_request(f"users/{user_id}", params, method="PATCH")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def delete_user(user_id: int):
    """Delete a user. Only possible if the user has no associated time/expenses/invoices.

    Args:
        user_id: The ID of the user to delete
    """
    await harvest_request(f"users/{user_id}", method="DELETE")
    return json.dumps({"deleted": True, "user_id": user_id}, indent=2)


@mcp.tool()
async def list_user_project_assignments(
    user_id: int,
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List project assignments for a specific user.

    Args:
        user_id: The ID of the user
        updated_since: Only updated since (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request(f"users/{user_id}/project_assignments", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def list_current_user_project_assignments(
    updated_since: str = None,
    page: int = None,
    per_page: int = None,
):
    """List project assignments for the authenticated user.

    Args:
        updated_since: Only updated since (ISO 8601)
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(updated_since=updated_since, page=page, per_page=per_page)
    response = await harvest_request("users/me/project_assignments", params)
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# User Billable Rates
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_user_billable_rates(user_id: int, page: int = None, per_page: int = None):
    """List billable rates for a user.

    Args:
        user_id: The ID of the user
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(page=page, per_page=per_page)
    response = await harvest_request(f"users/{user_id}/billable_rates", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_user_billable_rate(user_id: int, billable_rate_id: int):
    """Retrieve a specific billable rate for a user.

    Args:
        user_id: The ID of the user
        billable_rate_id: The ID of the billable rate
    """
    response = await harvest_request(f"users/{user_id}/billable_rates/{billable_rate_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_user_billable_rate(
    user_id: int,
    amount: float,
    start_date: str = None,
):
    """Create a new billable rate for a user.

    Args:
        user_id: The ID of the user
        amount: The rate amount
        start_date: The date the rate takes effect (YYYY-MM-DD)
    """
    params = build_body(amount=amount, start_date=start_date)
    response = await harvest_request(f"users/{user_id}/billable_rates", params, method="POST")
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# User Cost Rates
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_user_cost_rates(user_id: int, page: int = None, per_page: int = None):
    """List cost rates for a user.

    Args:
        user_id: The ID of the user
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(page=page, per_page=per_page)
    response = await harvest_request(f"users/{user_id}/cost_rates", params)
    return json.dumps(response, indent=2)


@mcp.tool()
async def get_user_cost_rate(user_id: int, cost_rate_id: int):
    """Retrieve a specific cost rate for a user.

    Args:
        user_id: The ID of the user
        cost_rate_id: The ID of the cost rate
    """
    response = await harvest_request(f"users/{user_id}/cost_rates/{cost_rate_id}")
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def create_user_cost_rate(
    user_id: int,
    amount: float,
    start_date: str = None,
):
    """Create a new cost rate for a user.

    Args:
        user_id: The ID of the user
        amount: The rate amount
        start_date: The date the rate takes effect (YYYY-MM-DD)
    """
    params = build_body(amount=amount, start_date=start_date)
    response = await harvest_request(f"users/{user_id}/cost_rates", params, method="POST")
    return json.dumps(response, indent=2)


# -----------------------------------------------------------------------------
# Teammates
# -----------------------------------------------------------------------------


@mcp.tool()
async def list_teammates(user_id: int, page: int = None, per_page: int = None):
    """List teammates for a user.

    Args:
        user_id: The ID of the user whose teammates to list
        page: Page number
        per_page: Records per page (1-2000)
    """
    params = build_query(page=page, per_page=per_page)
    response = await harvest_request(f"users/{user_id}/teammates", params)
    return json.dumps(response, indent=2)


@mcp.tool()
@requires_write
async def update_teammates(user_id: int, teammate_ids: list[int]):
    """Update the list of teammates for a user.

    Args:
        user_id: The ID of the user
        teammate_ids: Full list of user IDs to set as teammates
    """
    params = build_body(teammate_ids=teammate_ids)
    response = await harvest_request(f"users/{user_id}/teammates", params, method="PATCH")
    return json.dumps(response, indent=2)


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
