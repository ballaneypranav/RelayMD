from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.get_slurm_clusters_config_slurm_clusters_get_response_get_slurm_clusters_config_slurm_clusters_get import GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    x_api_token: None | str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_token, Unset):
        headers["X-API-Token"] = x_api_token



    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/config/slurm-clusters",
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_api_token: None | str | Unset = UNSET,

) -> Response[GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError]:
    """ Get Slurm Clusters

    Args:
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        x_api_token=x_api_token,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient | Client,
    x_api_token: None | str | Unset = UNSET,

) -> GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError | None:
    """ Get Slurm Clusters

    Args:
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError
     """


    return sync_detailed(
        client=client,
x_api_token=x_api_token,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_api_token: None | str | Unset = UNSET,

) -> Response[GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError]:
    """ Get Slurm Clusters

    Args:
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        x_api_token=x_api_token,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    x_api_token: None | str | Unset = UNSET,

) -> GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError | None:
    """ Get Slurm Clusters

    Args:
        x_api_token (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetSlurmClustersConfigSlurmClustersGetResponseGetSlurmClustersConfigSlurmClustersGet | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
x_api_token=x_api_token,

    )).parsed
