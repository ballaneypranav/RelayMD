from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.job_assigned import JobAssigned
from ...models.no_job_available import NoJobAvailable
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    worker_id: UUID,
    x_api_token: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_token, Unset):
        headers["X-API-Token"] = x_api_token

    params: dict[str, Any] = {}

    json_worker_id = str(worker_id)
    params["worker_id"] = json_worker_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/jobs/request",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | JobAssigned | NoJobAvailable | None:
    if response.status_code == 200:

        def _parse_response_200(data: object) -> JobAssigned | NoJobAvailable:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_0 = JobAssigned.from_dict(data)

                return response_200_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_200_type_1 = NoJobAvailable.from_dict(data)

            return response_200_type_1

        response_200 = _parse_response_200(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | JobAssigned | NoJobAvailable]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    worker_id: UUID,
    x_api_token: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | JobAssigned | NoJobAvailable]:
    """Request Job

    Args:
        worker_id (UUID):
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobAssigned | NoJobAvailable]
    """

    kwargs = _get_kwargs(
        worker_id=worker_id,
        x_api_token=x_api_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    worker_id: UUID,
    x_api_token: None | str | Unset = UNSET,
) -> HTTPValidationError | JobAssigned | NoJobAvailable | None:
    """Request Job

    Args:
        worker_id (UUID):
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobAssigned | NoJobAvailable
    """

    return sync_detailed(
        client=client,
        worker_id=worker_id,
        x_api_token=x_api_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    worker_id: UUID,
    x_api_token: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | JobAssigned | NoJobAvailable]:
    """Request Job

    Args:
        worker_id (UUID):
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobAssigned | NoJobAvailable]
    """

    kwargs = _get_kwargs(
        worker_id=worker_id,
        x_api_token=x_api_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    worker_id: UUID,
    x_api_token: None | str | Unset = UNSET,
) -> HTTPValidationError | JobAssigned | NoJobAvailable | None:
    """Request Job

    Args:
        worker_id (UUID):
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobAssigned | NoJobAvailable
    """

    return (
        await asyncio_detailed(
            client=client,
            worker_id=worker_id,
            x_api_token=x_api_token,
        )
    ).parsed
