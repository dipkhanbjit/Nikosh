import markdown as md

from app.core.config import settings
from app.services.google_clients import blogger_service


class BloggerError(Exception):
    pass


def build_post_html(description: str, apply_url: str | None, deadline: str | None = None) -> str:
    html = md.markdown(description)
    if apply_url:
        html += '<hr><h2>Apply Now</h2>'
        if deadline:
            html += f"<p><strong>Application deadline:</strong> {deadline}</p>"
        html += (
            f'<p><a href="{apply_url}" target="_blank" rel="noopener">'
            "Click here to apply with your CV</a></p>"
        )
    return html


def publish_post(title: str, html: str) -> str:
    """Publish a post to the Nikosh blog and return its public URL."""
    if not settings.blogger_blog_id:
        raise BloggerError("Blogger is not configured")
    try:
        post = blogger_service().posts().insert(
            blogId=settings.blogger_blog_id,
            body={"title": title, "content": html},
        ).execute()
    except Exception as exc:
        raise BloggerError(f"Blogger rejected the post: {exc.__class__.__name__}") from None
    return post["url"]