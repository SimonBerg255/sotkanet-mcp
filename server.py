import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from mcp.server.fastmcp import Icon
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

load_dotenv()

# Pre-warm caches on import — never wait for first tool call
print("Pre-warming Sotkanet caches...", flush=True)
from sotkanet_client import get_indicators_cached, get_regions_cached

_indicators = get_indicators_cached()
_regions = get_regions_cached()
print(f"Cache warm: {len(_indicators)} indicators, {len(_regions)} regions. Server ready.", flush=True)

from tools_sotkanet import (
    search_indicators,
    browse_indicator_groups,
    get_indicator_metadata,
    get_indicator_data,
    compare_regions,
    get_trend,
)


####### CUSTOM MIDDLEWARE #######

class IPAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_ips: list[str]):
        super().__init__(app)
        self.allowed_ips = set(allowed_ips)
        self.allow_all = "*" in self.allowed_ips

    async def dispatch(self, request, call_next):
        if self.allow_all:
            return await call_next(request)
        client_ip = request.client.host if request.client else None
        if client_ip not in self.allowed_ips:
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "your_ip": client_ip},
            )
        return await call_next(request)


ALLOWED_IPS = ["*"]  # Restrict to specific IPs in production
middleware = [Middleware(IPAllowlistMiddleware, allowed_ips=ALLOWED_IPS)]


####### SERVER METADATA #######

icon = Icon(src="https://raw.githubusercontent.com/SimonBerg255/sotkanet-mcp/main/sotkanet.png")

INSTRUCTION_STRING = """
You are connected to Sotkanet — Finland's national statistics and indicator bank for
population health and welfare, maintained by THL (Finnish Institute for Health and Welfare).

## What this server can answer
- Health service usage: GP visits, hospital admissions, waiting times
- Elderly and social care: home care, institutional care, disability services
- Mental health: hospitalizations, outpatient care, substance abuse
- Child welfare: child protection clients, foster care
- Public health indicators: vaccination, mortality, chronic disease
- Social support: income support recipients, long-term unemployment
- Municipal benchmarking: how one region compares to others

## Agent decision tree — follow this exactly

1. User asks about a health/welfare topic with no indicator ID:
   → FIRST call search_indicators with relevant keywords
   → If no results → try broader keywords or call browse_indicator_groups
   → Found indicator? → call get_indicator_metadata to confirm it fits

2. User asks "which regions are best/worst at X?":
   → search_indicators → get ID → compare_regions

3. User asks about a specific region over time:
   → search_indicators → get ID → get_trend

4. User asks for current values across all counties:
   → search_indicators → get ID → get_indicator_data
     with region_category="HYVINVOINTIALUE" (default, 23 counties)

5. Never call get_indicator_data with region_category="KUNTA" unless
   the user explicitly requests municipality-level data. Use compare_regions
   for ranking instead.

## Region categories
- HYVINVOINTIALUE = Wellbeing services counties (23) ← recommended default
- MAAKUNTA = Regions (19)
- ERVA = University hospital special responsibility areas (5)
- MAA = Whole country (1, region id=658)
- KUNTA = Municipalities (308) ← large, avoid unless explicitly needed

## Language
All data available in English (en), Finnish (fi), and Swedish (sv).
Default to English unless user specifies otherwise.

## Limitations
- Data is not real-time — typically updated annually or quarterly
- Some indicators provided by third parties; THL data is CC BY 4.0
- Municipality-level data for some indicators may have gaps

Source: https://sotkanet.fi | THL — Finnish Institute for Health and Welfare
"""

VERSION = "1.0.0"
WEBSITE_URL = "https://sotkanet.fi"


####### SERVER CONFIGURATION #######

mcp = FastMCP(
    name="Sotkanet",
    instructions=INSTRUCTION_STRING,
    version=VERSION,
    website_url=WEBSITE_URL,
    icons=[icon],
)


####### TOOLS #######

# All tools run automatically without user confirmation per Intric best practice.
# Data-read operations from a public API need no destructive-action guardrail.

mcp.tool(meta={"requires_permission": False})(search_indicators)
mcp.tool(meta={"requires_permission": False})(browse_indicator_groups)
mcp.tool(meta={"requires_permission": False})(get_indicator_metadata)
mcp.tool(meta={"requires_permission": False})(get_indicator_data)
mcp.tool(meta={"requires_permission": False})(compare_regions)
mcp.tool(meta={"requires_permission": False})(get_trend)


####### CUSTOM ROUTES #######

# Intric uses /health to check if the server is running.
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


####### RUNNING THE SERVER #######
# Run with: uvicorn server:app --host 0.0.0.0 --port 8000
# MCP endpoint available at: http://localhost:8000/mcp

app = mcp.http_app(middleware=middleware)
