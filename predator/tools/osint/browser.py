"""Browser automation tools — Playwright-based web OSINT and interaction.

Provides tools for browsing websites, taking screenshots, extracting text,
filling forms, and interacting with web pages during reconnaissance.
Uses async Playwright with headless Chromium.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult

# ---------------------------------------------------------------------------
# Shared browser instance management
# ---------------------------------------------------------------------------

_browser_lock = asyncio.Lock()
_playwright_instance = None
_browser_instance = None


async def _get_browser():
    """Lazily initialise and return a shared headless Chromium browser."""
    global _playwright_instance, _browser_instance

    async with _browser_lock:
        if _browser_instance is None or not _browser_instance.is_connected():
            # Import here so the module loads even if playwright isn't installed
            from playwright.async_api import async_playwright

            if _playwright_instance is not None:
                try:
                    await _playwright_instance.stop()
                except Exception:
                    pass

            _playwright_instance = await async_playwright().start()
            _browser_instance = await _playwright_instance.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

    return _browser_instance


async def _new_page(timeout: int = 30000):
    """Create a new browser page with sensible defaults."""
    browser = await _get_browser()
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    page = await context.new_page()
    page.set_default_timeout(timeout)
    return page


# ---------------------------------------------------------------------------
# BrowserNavigateTool
# ---------------------------------------------------------------------------


class BrowserNavigateTool(BaseTool):
    """Navigate to a URL and return the page title and text content."""

    name = "browser_navigate"
    description = (
        "Navigate to a URL with a headless Chromium browser and return the "
        "page title and visible text content (truncated to a reasonable length). "
        "Useful for reading web pages during OSINT reconnaissance, checking if "
        "a site is alive, and extracting on-page information. "
        "Optionally wait for a specific CSS selector to appear before returning."
    )
    category = ToolCategory.OSINT
    requires_approval = False
    requires_sudo = False

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to (must include scheme, e.g. https://)",
                },
                "wait_for": {
                    "type": "string",
                    "description": (
                        "Optional CSS selector to wait for before extracting content. "
                        "Useful for SPAs that load content dynamically."
                    ),
                },
                "timeout": {
                    "type": "number",
                    "description": "Navigation timeout in milliseconds (default: 30000)",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        url: str = arguments["url"]
        wait_for: Optional[str] = arguments.get("wait_for")
        timeout: int = int(arguments.get("timeout", 30000))

        page = await _new_page(timeout=timeout)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=timeout)

            title = await page.title()
            # Extract visible text, truncated to ~8000 chars to stay within LLM context
            text_content = await page.evaluate("() => document.body.innerText")
            max_chars = 8000
            truncated = len(text_content) > max_chars
            text_content = text_content[:max_chars]

            status = response.status if response else "unknown"

            output_parts = [
                f"URL: {url}",
                f"Status: {status}",
                f"Title: {title}",
                "",
                "--- Page Content ---",
                text_content,
            ]
            if truncated:
                output_parts.append("\n[... content truncated at 8000 characters ...]")

            return ToolResult(
                output="\n".join(output_parts),
                metadata={
                    "url": url,
                    "status": status,
                    "title": title,
                    "truncated": truncated,
                    "content_length": len(text_content),
                },
            )
        except Exception as exc:
            return ToolResult(
                output=f"Browser navigation failed: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={"url": url},
            )
        finally:
            context = page.context
            await page.close()
            await context.close()


# ---------------------------------------------------------------------------
# BrowserScreenshotTool
# ---------------------------------------------------------------------------


class BrowserScreenshotTool(BaseTool):
    """Take a screenshot of a web page or a specific element."""

    name = "browser_screenshot"
    description = (
        "Take a screenshot of a web page using headless Chromium. "
        "Can capture the full page or a specific element identified by a CSS "
        "selector. Optionally navigate to a URL first. Returns the file path "
        "of the saved PNG screenshot. Useful for visual OSINT, capturing "
        "evidence, and documenting web-based findings."
    )
    category = ToolCategory.OSINT
    requires_approval = False
    requires_sudo = False

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "URL to navigate to before taking the screenshot. "
                        "Required if no page is currently loaded."
                    ),
                },
                "selector": {
                    "type": "string",
                    "description": (
                        "Optional CSS selector of a specific element to screenshot "
                        "instead of the whole page."
                    ),
                },
                "full_page": {
                    "type": "boolean",
                    "description": (
                        "If true, capture the full scrollable page instead of "
                        "just the viewport (default: false)."
                    ),
                },
                "timeout": {
                    "type": "number",
                    "description": "Navigation timeout in milliseconds (default: 30000)",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        url: Optional[str] = arguments.get("url")
        selector: Optional[str] = arguments.get("selector")
        full_page: bool = arguments.get("full_page", False)
        timeout: int = int(arguments.get("timeout", 30000))

        if not url:
            return ToolResult(
                output="A 'url' is required to take a screenshot.",
                is_error=True,
            )

        page = await _new_page(timeout=timeout)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            # Small delay for dynamic content to render
            await page.wait_for_timeout(1000)

            # Build a deterministic screenshot path
            screenshots_dir = os.path.join(tempfile.gettempdir(), "predator_screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}_{tool_call_id[:8]}.png"
            filepath = os.path.join(screenshots_dir, filename)

            if selector:
                element = await page.query_selector(selector)
                if element is None:
                    return ToolResult(
                        output=f"Selector '{selector}' not found on page: {url}",
                        is_error=True,
                        metadata={"url": url, "selector": selector},
                    )
                await element.screenshot(path=filepath)
            else:
                await page.screenshot(path=filepath, full_page=full_page)

            title = await page.title()

            return ToolResult(
                output=f"Screenshot saved: {filepath}\nURL: {url}\nTitle: {title}",
                images=[filepath],
                metadata={
                    "url": url,
                    "title": title,
                    "filepath": filepath,
                    "selector": selector,
                    "full_page": full_page,
                },
            )
        except Exception as exc:
            return ToolResult(
                output=f"Screenshot failed: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={"url": url},
            )
        finally:
            context = page.context
            await page.close()
            await context.close()


# ---------------------------------------------------------------------------
# BrowserExtractTool
# ---------------------------------------------------------------------------


class BrowserExtractTool(BaseTool):
    """Extract structured data from a web page using CSS selectors."""

    name = "browser_extract"
    description = (
        "Navigate to a URL and extract structured data from the page using "
        "CSS selectors. Provide a mapping of field names to CSS selectors and "
        "receive back extracted text (or a specified attribute) for each. "
        "Useful for scraping specific data points during OSINT — e.g. email "
        "addresses, phone numbers, names, social links from target websites."
    )
    category = ToolCategory.OSINT
    requires_approval = False
    requires_sudo = False

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to and extract data from.",
                },
                "selectors": {
                    "type": "object",
                    "description": (
                        "A mapping of field names to CSS selectors. "
                        'Example: {"title": "h1", "emails": "a[href^=mailto]", '
                        '"links": "nav a"}'
                    ),
                },
                "attribute": {
                    "type": "string",
                    "description": (
                        "The attribute to extract from matched elements. "
                        'Default is "textContent". Use "href", "src", "alt", etc. '
                        "for specific attributes."
                    ),
                },
                "timeout": {
                    "type": "number",
                    "description": "Navigation timeout in milliseconds (default: 30000)",
                },
            },
            "required": ["url", "selectors"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        url: str = arguments["url"]
        selectors: dict[str, str] = arguments["selectors"]
        attribute: str = arguments.get("attribute", "textContent")
        timeout: int = int(arguments.get("timeout", 30000))

        if not isinstance(selectors, dict) or not selectors:
            return ToolResult(
                output="'selectors' must be a non-empty object mapping names to CSS selectors.",
                is_error=True,
            )

        page = await _new_page(timeout=timeout)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            results: dict[str, list[str]] = {}

            for field_name, css_selector in selectors.items():
                elements = await page.query_selector_all(css_selector)
                values: list[str] = []
                for el in elements:
                    if attribute == "textContent":
                        val = await el.text_content()
                    else:
                        val = await el.get_attribute(attribute)
                    if val is not None:
                        val = val.strip()
                        if val:
                            values.append(val)
                results[field_name] = values

            # Format output
            output_lines = [f"URL: {url}", f"Attribute: {attribute}", ""]
            for field_name, values in results.items():
                output_lines.append(f"--- {field_name} ({len(values)} matches) ---")
                if values:
                    for v in values[:50]:  # Cap at 50 per field
                        output_lines.append(f"  {v}")
                    if len(values) > 50:
                        output_lines.append(f"  [... {len(values) - 50} more ...]")
                else:
                    output_lines.append("  (no matches)")
                output_lines.append("")

            return ToolResult(
                output="\n".join(output_lines),
                metadata={
                    "url": url,
                    "attribute": attribute,
                    "fields": {k: len(v) for k, v in results.items()},
                },
            )
        except Exception as exc:
            return ToolResult(
                output=f"Extraction failed: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={"url": url},
            )
        finally:
            context = page.context
            await page.close()
            await context.close()
