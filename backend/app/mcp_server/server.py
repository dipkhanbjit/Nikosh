import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.services.blogger import BloggerError, build_post_html, publish_post
from app.services.job_forms import FormError, create_job_form as create_form
from app.services.job_forms import download_file, list_responses, trash_file
from app.services.job_forms import set_form_open as set_open
from app.services.telegram import PostingError, announce_job

setup_logging("mcp_server.log", console=False)
logger = logging.getLogger("nikosh_tools")

mcp = FastMCP("nikosh-tools")


@mcp.tool()
def publish_to_blogger(title: str, description: str, apply_url: str = "", deadline: str = "") -> str:
    """Publish a job description (Markdown) to the Nirvik Careers blog with an
    Apply section linking to the application form and showing the deadline. Returns the post URL."""
    try:
        url = publish_post(title, build_post_html(description, apply_url or None, deadline or None))
    except BloggerError as exc:
        logger.error("Blogger post failed for '%s': %s", title, exc)
        raise
    logger.info("Blogger post published for '%s': %s", title, url)
    return url


@mcp.tool()
def publish_to_telegram(title: str, details: str, link: str, apply_url: str = "") -> str:
    """Announce a job opening on the Nirvik Careers Telegram channel with links to
    the full job description and the application form. Returns the post URL."""
    try:
        url = announce_job(title, details, link, apply_url or None)
    except PostingError as exc:
        logger.error("Telegram post failed for '%s': %s", title, exc)
        raise
    logger.info("Telegram post published for '%s': %s", title, url)
    return url


@mcp.tool()
def create_job_form(title: str, description: str) -> str:
    """Create a dedicated Google Form for one job by copying the application template,
    then set its title and description and open it. Returns JSON {form_id, form_url}."""
    try:
        form = create_form(title, description)
    except FormError as exc:
        logger.error("Form creation failed for '%s': %s", title, exc)
        raise
    logger.info("Form created for '%s': %s", title, form["form_id"])
    return json.dumps(form)


@mcp.tool()
def set_form_open(form_id: str, accepting: bool) -> str:
    """Open (accepting=true) or close (accepting=false) a job's Google Form for new responses."""
    try:
        set_open(form_id, accepting)
    except FormError as exc:
        logger.error("Changing form %s failed: %s", form_id, exc)
        raise
    state = "opened" if accepting else "closed"
    logger.info("Form %s %s", form_id, state)
    return state


@mcp.tool()
def list_job_applications(form_id: str) -> str:
    """List all applications submitted to a job's Google Form. Returns a JSON array of
    {response_id, full_name, email, phone, cv_file_id, cv_filename, submitted_at}."""
    try:
        applications = list_responses(form_id)
    except FormError as exc:
        logger.error("Listing applications failed for form %s: %s", form_id, exc)
        raise
    logger.info("Listed %s application(s) for form %s", len(applications), form_id)
    return json.dumps(applications)


@mcp.tool()
def download_cv(file_id: str) -> str:
    """Download an applicant's CV from Google Drive into the incoming folder.
    Returns JSON {filename, path, size}."""
    try:
        filename, content = download_file(file_id)
    except FormError as exc:
        logger.error("CV download failed for file %s: %s", file_id, exc)
        raise
    incoming = Path(settings.cv_storage_dir) / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    path = incoming / f"{file_id}_{Path(filename).name}"
    path.write_bytes(content)
    logger.info("Downloaded CV %s (%s bytes) to %s", filename, len(content), path)
    return json.dumps({"filename": filename, "path": str(path), "size": len(content)})


@mcp.tool()
def trash_drive_file(file_id: str) -> str:
    """Move an applicant's CV in Google Drive to the trash. Returns 'trashed' or 'not_found'."""
    try:
        found = trash_file(file_id)
    except FormError as exc:
        logger.error("Trashing Drive file %s failed: %s", file_id, exc)
        raise
    state = "trashed" if found else "not_found"
    logger.info("Drive file %s %s", file_id, state)
    return state


if __name__ == "__main__":
    mcp.run()