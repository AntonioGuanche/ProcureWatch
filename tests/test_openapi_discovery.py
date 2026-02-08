"""Unit tests for OpenAPI discovery heuristics (no network)."""
import sys
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.bosa.openapi_discovery import (
    discover_cpv_label_endpoint,
    discover_publication_detail_endpoint,
    discover_search_publications_endpoint,
)

# Minimal fake SEA spec: POST /publications/search with terms, page, pageSize
FAKE_SEA_SPEC = {
    "swagger": "2.0",
    "basePath": "/api/eProcurementSea/v1",
    "paths": {
        "/publications/search": {
            "post": {
                "operationId": "searchPublications",
                "summary": "Search BDA publications",
                "parameters": [],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "terms": {"type": "string"},
                                    "page": {"type": "integer"},
                                    "pageSize": {"type": "integer"},
                                },
                            }
                        }
                    }
                },
            }
        },
        "/other/endpoint": {
            "get": {
                "operationId": "getOther",
                "summary": "Other endpoint",
            },
        },
    },
}

# OpenAPI 2 style: single body param with schema
FAKE_SEA_SPEC_V2 = {
    "swagger": "2.0",
    "basePath": "/api/eProcurementSea/v1",
    "paths": {
        "/sea/search/publications": {
            "post": {
                "operationId": "searchPublicationsBda",
                "summary": "Search publications in BDA",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "terms": {"type": "string"},
                                "page": {"type": "integer"},
                                "pageSize": {"type": "integer"},
                            },
                        },
                    }
                ],
            }
        },
    },
}

# Spec with search/publications and generateShortLink: winner must be GET or POST /search/publications
# GET has response schema with publications/items so it gets response bonus; prefer GET when both exist
FAKE_SEA_SPEC_WITH_SHORTLINK = {
    "swagger": "2.0",
    "basePath": "/api/eProcurementSea/v1",
    "paths": {
        "/search/publications": {
            "get": {
                "operationId": "getSearchPublications",
                "summary": "Search BDA publications",
                "parameters": [
                    {"name": "terms", "in": "query"},
                    {"name": "page", "in": "query"},
                    {"name": "pageSize", "in": "query"},
                ],
                "responses": {
                    "200": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "publications": {"type": "array"},
                                "total": {"type": "integer"},
                            },
                        },
                    },
                },
            },
            "post": {
                "operationId": "searchPublications",
                "summary": "Search publications",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "terms": {"type": "string"},
                                "page": {"type": "integer"},
                                "pageSize": {"type": "integer"},
                            },
                        },
                    }
                ],
                "responses": {
                    "200": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "items": {"type": "array"},
                                "total": {"type": "integer"},
                            },
                        },
                    },
                },
            },
        },
        "/search/publications/generateShortLink": {
            "post": {
                "operationId": "generateShortLink",
                "summary": "Generate short link for publication",
                "parameters": [{"name": "body", "in": "body", "schema": {"type": "object"}}],
            },
        },
    },
}

# Minimal fake LOC spec: GET /cpv/{code} with language
FAKE_LOC_SPEC = {
    "openapi": "3.0.0",
    "paths": {
        "/cpv/{code}": {
            "get": {
                "operationId": "getCpvDescription",
                "summary": "Get CPV code description",
                "parameters": [
                    {"name": "code", "in": "path", "required": True},
                    {"name": "language", "in": "query"},
                ],
            }
        },
        "/other": {
            "get": {
                "operationId": "getOther",
                "summary": "Other",
            },
        },
    },
}


def test_discover_search_publications_endpoint_sea() -> None:
    """Discovery picks POST /publications/search with terms/page/pageSize."""
    candidates = discover_search_publications_endpoint(FAKE_SEA_SPEC_V2)
    assert len(candidates) >= 1
    best = candidates[0]
    assert "publication" in best.path.lower() or "search" in best.path.lower()
    assert best.method == "POST"
    assert best.term_param is not None
    assert best.page_param is not None
    assert best.page_size_param is not None
    assert best.score > 0


def test_discover_search_publications_endpoint_prefers_search_params() -> None:
    """Discovery prefers endpoints with term, page, pageSize params."""
    candidates = discover_search_publications_endpoint(FAKE_SEA_SPEC_V2)
    assert len(candidates) >= 1
    best = candidates[0]
    assert best.term_param in ("terms", "term", "query", "q") or best.term_param
    assert best.page_param
    assert best.page_size_param


def test_discover_cpv_label_endpoint_loc() -> None:
    """Discovery picks GET /cpv/{code} with code and language."""
    candidates = discover_cpv_label_endpoint(FAKE_LOC_SPEC)
    assert len(candidates) >= 1
    best = candidates[0]
    assert "cpv" in best.path.lower()
    assert best.method == "GET"
    assert best.code_param is not None
    assert best.lang_param is not None or "language" in str(best.path_params).lower()
    assert best.score > 0


def test_discover_cpv_label_path_params() -> None:
    """Discovery extracts path params for CPV (e.g. {code})."""
    candidates = discover_cpv_label_endpoint(FAKE_LOC_SPEC)
    assert len(candidates) >= 1
    best = candidates[0]
    assert "code" in best.path
    assert best.path_params == ["code"] or "code" in best.path_params


def test_search_publications_never_picks_generate_shortlink() -> None:
    """With GET/POST /search/publications and POST generateShortLink, winner is never generateShortLink."""
    candidates = discover_search_publications_endpoint(FAKE_SEA_SPEC_WITH_SHORTLINK)
    assert len(candidates) >= 1
    best = candidates[0]
    assert "generateshortlink" not in best.path.lower(), (
        f"Chosen endpoint must not be generateShortLink, got {best.method} {best.path}"
    )
    # Winner must be one of the real search endpoints
    assert best.path.rstrip("/").endswith("/search/publications"), (
        f"Chosen endpoint must be GET or POST /search/publications, got {best.method} {best.path}"
    )
    assert best.method in ("GET", "POST")


def test_search_publications_prefers_get_when_both_exist() -> None:
    """When both GET and POST /search/publications exist, discovery prefers GET with query params."""
    candidates = discover_search_publications_endpoint(FAKE_SEA_SPEC_WITH_SHORTLINK)
    assert len(candidates) >= 1
    best = candidates[0]
    assert best.path.rstrip("/").endswith("/search/publications")
    assert best.method == "GET", (
        f"Should prefer GET /search/publications when both exist, got {best.method} {best.path}"
    )


# Fake SEA spec with publication detail: GET /publications/{id}
FAKE_SEA_SPEC_PUBLICATION_DETAIL = {
    "swagger": "2.0",
    "basePath": "/api/eProcurementSea/v1",
    "paths": {
        "/publications/{id}": {
            "get": {
                "operationId": "getPublicationDetail",
                "summary": "Get publication detail by ID",
                "parameters": [{"name": "id", "in": "path", "required": True, "type": "string"}],
            },
        },
        "/publications/{publicationId}/summary": {
            "get": {
                "operationId": "getPublicationSummary",
                "summary": "Get publication summary",
                "parameters": [{"name": "publicationId", "in": "path", "required": True}],
            },
        },
    },
}


def test_discover_publication_detail_endpoint() -> None:
    """Discovery picks GET /publications/{id} with path param for publication detail."""
    candidates = discover_publication_detail_endpoint(FAKE_SEA_SPEC_PUBLICATION_DETAIL)
    assert len(candidates) >= 1
    best = candidates[0]
    assert best.method == "GET"
    assert "/publications" in best.path.lower()
    assert "{" in best.path and "}" in best.path
    assert best.path_params
    assert best.score > 0
    # Prefer path with "detail" in operationId/summary
    assert "detail" in best.operation_id.lower() or "detail" in best.summary.lower()
