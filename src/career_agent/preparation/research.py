"""Read-only search boundary: provider shape ends here, never becomes domain instructions."""

import json
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import Field, ValidationError

from career_agent.domain.schemas import Contract
from career_agent.models.contracts import ModelGatewayError
from career_agent.preparation.contracts import ResearchEvidence


class SearchInput(Contract):
    query: str = Field(min_length=1, max_length=500)


class SearchResult(Contract):
    evidence: list[ResearchEvidence] = Field(max_length=5)


class SearchToolMetadata(Contract):
    tool_name: str = "company_search"
    tool_version: str = "company-search-v1"
    input_schema_version: str = "search-input-v1"
    output_schema_version: str = "search-result-v1"
    side_effect: str = "read_only_external"
    timeout_seconds: int = 15
    max_attempts: int = 1  # A failed attempt consumes one of the two search slots.
    idempotency: str = "read_only_not_repeatable"
    trust_level: str = "untrusted_external"
    estimated_cost_class: str = "basic_payg_equivalent_not_billed"


SEARCH_PARAMETERS = {
    "search_depth": "basic",
    "max_results": 5,
    "include_answer": False,
    "include_raw_content": False,
    "auto_parameters": False,
}


class SearchReuseContract(Contract):
    """Trusted adapter configuration, not a model- or caller-supplied cache key."""

    provider: str
    version: str
    parameters: dict[str, str | int | bool]


class ResearchAdapter(Protocol):
    async def search(self, query: SearchInput) -> SearchResult: ...


class FixtureResearchAdapter:
    reuse_contract = SearchReuseContract(
        provider="fixture", version="fixture-search-v1", parameters=SEARCH_PARAMETERS
    )

    async def search(self, query: SearchInput) -> SearchResult:
        return SearchResult(
            evidence=[
                ResearchEvidence(
                    id=uuid4(),
                    source_url="https://example.invalid/company",
                    title="合成公司资料",
                    content=(
                        "示例公司提供开发工具与数据服务，公开介绍其工程团队使用 API 与自动化测试。"
                        "此为合成资料，不代表真实公司。团队同时维护合成数据实验和服务可靠性记录。"
                    ),
                    retrieved_at=datetime.now(UTC),
                    provider="fixture",
                )
            ]
        )


class TavilyResearchAdapter:
    reuse_contract = SearchReuseContract(
        provider="tavily", version="tavily-search-v1", parameters=SEARCH_PARAMETERS
    )

    def __init__(self, key: str, client: httpx.AsyncClient, timeout: float = 15) -> None:
        self.key, self.client, self.timeout = key, client, timeout

    async def search(self, query: SearchInput) -> SearchResult:
        try:
            async with self.client.stream(
                "POST",
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.key}"},
                json={
                    "query": query.query,
                    **self.reuse_contract.parameters,
                },
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 200000:
                        raise ModelGatewayError("research_response_too_large")
            data = json.loads(body)
            evidence = []
            for item in data["results"][:5]:
                url = urlsplit(item["url"])
                if (
                    url.scheme not in {"http", "https"}
                    or not url.hostname
                    or url.username
                    or url.password
                ):
                    continue
                content = item.get("content", "")
                if not content:
                    continue
                evidence.append(
                    ResearchEvidence(
                        id=uuid4(),
                        source_url=item["url"],
                        title=item.get("title", "")[:500],
                        content=content[:6000],
                        retrieved_at=datetime.now(UTC),
                        provider="tavily",
                    )
                )
            return SearchResult(evidence=evidence)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError):
            raise ModelGatewayError("research_failed") from None
