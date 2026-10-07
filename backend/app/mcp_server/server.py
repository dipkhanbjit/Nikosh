import logging

from mcp.server.fastmcp import FastMCP

from app.core.logging_config import setup_logging
from app.services.blogger import BloggerError, build_post_html, publish_post
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


if __name__ == "__main__":
    mcp.run()