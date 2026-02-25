from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.register_worker_workers_register_post_response_register_worker_workers_register_post import (
    RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost,
)
from ...models.worker_register import WorkerRegister
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: WorkerRegister,
    x_api_token: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_token, Unset):
        headers["X-API-Token"] = x_api_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/workers/register",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
    | None
):
    if response.status_code == 200:
        response_200 = (
            RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost.from_dict(
                response.json()
            )
        )

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
) -> Response[
    HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: WorkerRegister,
    x_api_token: None | str | Unset = UNSET,
) -> Response[
    HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
]:
    """Register Worker

    Args:
        x_api_token (None | str | Unset):
        body (WorkerRegister):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_token=x_api_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: WorkerRegister,
    x_api_token: None | str | Unset = UNSET,
) -> (
    HTTPValidationError
    | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
    | None
):
    """Register Worker

    Args:
        x_api_token (None | str | Unset):
        body (WorkerRegister):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_token=x_api_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: WorkerRegister,
    x_api_token: None | str | Unset = UNSET,
) -> Response[
    HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
]:
    """Register Worker

    Args:
        x_api_token (None | str | Unset):
        body (WorkerRegister):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_token=x_api_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: WorkerRegister,
    x_api_token: None | str | Unset = UNSET,
) -> (
    HTTPValidationError
    | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
    | None
):
    """Register Worker

    Args:
        x_api_token (None | str | Unset):
        body (WorkerRegister):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RegisterWorkerWorkersRegisterPostResponseRegisterWorkerWorkersRegisterPost
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_token=x_api_token,
        )
    ).parsed
