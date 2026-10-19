import pytest


@pytest.mark.asyncio
async def test_refresh_token_rotation(client, registered_store):
    """Refresh token rotation must work without crashing on SQLite naive datetime."""
    login_resp = await client.post("/auth/login", json={
        "email": registered_store["owner_email"],
        "password": registered_store["owner_password"],
        "store_slug": registered_store["store_slug"],
    })
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["data"]["refresh_token"]

    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    new_data = refresh_resp.json()["data"]
    assert "access_token" in new_data
    assert new_data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_revoked_refresh_token_rejected(client, registered_store):
    """A used refresh token must be rejected after rotation."""
    login_resp = await client.post("/auth/login", json={
        "email": registered_store["owner_email"],
        "password": registered_store["owner_password"],
        "store_slug": registered_store["store_slug"],
    })
    refresh_token = login_resp.json()["data"]["refresh_token"]

    await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    second_resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert second_resp.status_code == 401
