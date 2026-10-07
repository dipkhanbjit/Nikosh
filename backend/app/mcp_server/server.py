import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.services.blogger import BloggerError, build_post_html, publish_post
from app.services.google_forms import GoogleFormsError, download_file, list_applications
from app.services.telegram import PostingError, announce_job

setup_logging("mcp_server.log", console=False)
logger = logging.getLogger("nikosh_tools")

mcp = FastMCP("nikosh-tools")


@mcp.tool()
def publish_to_blogger(title: str, description: str, apply_url: str = "") -> str:
    """Publish a job description (Markdown) to the Nirvik Careers blog with an
    Apply section linking to the application form. Returns the post URL."""
    try:
        url = publish_post(title, build_post_html(description, apply_url or None))
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
def list_job_applications(job_id: int) -> str:
    """List all Google Form applications submitted for a job. Returns a JSON array
    of {file_id, full_name, email, phone, submitted_at}."""
    try:
        applications = list_applications(job_id)
    except GoogleFormsError as exc:
        logger.error("Listing applications failed for job %s: %s", job_id, exc)
        raise
    logger.info("Listed %s application(s) for job %s", len(applications), job_id)
    return json.dumps(applications)


@mcp.tool()
def download_cv(file_id: str) -> str:
    """Download an applicant's CV from Google Drive into the incoming folder.
    Returns JSON {filename, path, size}."""
    try:
        filename, content = download_file(file_id)
    except GoogleFormsError as exc:
        logger.error("CV download failed for file %s: %s", file_id, exc)
        raise
    incoming = Path(settings.cv_storage_dir) / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    path = incoming / f"{file_id}_{Path(filename).name}"
    path.write_bytes(content)
    logger.info("Downloaded CV %s (%s bytes) to %s", filename, len(content), path)
    return json.dumps({"filename": filename, "path": str(path), "size": len(content)})


if __name__ == "__main__":
    mcp.run()