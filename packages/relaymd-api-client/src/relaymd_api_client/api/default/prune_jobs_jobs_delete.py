from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.job_status import JobStatus
from ...models.prune_jobs_jobs_delete_response_prune_jobs_jobs_delete import (
    PruneJobsJobsDeleteResponsePruneJobsJobsDelete,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    status: list[JobStatus] | Unset = UNSET,
    older_than_days: int | Unset = 30,
    x_api_token: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_token, Unset) and x_api_token is not None:
        headers["X-API-Token"] = x_api_token

    params: dict[str, Any] = {}

    json_status: list[str] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = []
        for status_item_data in status:
            status_item = status_item_data.value
            json_status.append(status_item)

    params["status"] = json_status

    params["older_than_days"] = older_than_days

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/jobs",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete | None:
    if response.status_code == 200:
        response_200 = PruneJobsJobsDeleteResponsePruneJobsJobsDelete.from_dict(response.json())

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
) -> Response[HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: list[JobStatus] | Unset = UNSET,
    older_than_days: int | Unset = 30,
    x_api_token: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete]:
    """Prune Jobs

     Hard-delete terminal-status jobs whose updated_at is older than N days.

    Args:
        status (list[JobStatus] | Unset): Terminal statuses to prune.
        older_than_days (int | Unset):  Default: 30.
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete]
    """

    kwargs = _get_kwargs(
        status=status,
        older_than_days=older_than_days,
        x_api_token=x_api_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    status: list[JobStatus] | Unset = UNSET,
    older_than_days: int | Unset = 30,
    x_api_token: None | str | Unset = UNSET,
) -> HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete | None:
    """Prune Jobs

     Hard-delete terminal-status jobs whose updated_at is older than N days.

    Args:
        status (list[JobStatus] | Unset): Terminal statuses to prune.
        older_than_days (int | Unset):  Default: 30.
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete
    """

    return sync_detailed(
        client=client,
        status=status,
        older_than_days=older_than_days,
        x_api_token=x_api_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: list[JobStatus] | Unset = UNSET,
    older_than_days: int | Unset = 30,
    x_api_token: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete]:
    """Prune Jobs

     Hard-delete terminal-status jobs whose updated_at is older than N days.

    Args:
        status (list[JobStatus] | Unset): Terminal statuses to prune.
        older_than_days (int | Unset):  Default: 30.
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete]
    """

    kwargs = _get_kwargs(
        status=status,
        older_than_days=older_than_days,
        x_api_token=x_api_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    status: list[JobStatus] | Unset = UNSET,
    older_than_days: int | Unset = 30,
    x_api_token: None | str | Unset = UNSET,
) -> HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete | None:
    """Prune Jobs

     Hard-delete terminal-status jobs whose updated_at is older than N days.

    Args:
        status (list[JobStatus] | Unset): Terminal statuses to prune.
        older_than_days (int | Unset):  Default: 30.
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PruneJobsJobsDeleteResponsePruneJobsJobsDelete
    """

    return (
        await asyncio_detailed(
            client=client,
            status=status,
            older_than_days=older_than_days,
            x_api_token=x_api_token,
        )
    ).parsed
