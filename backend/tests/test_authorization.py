import pytest
from httpx import AsyncClient

from app.db.models.shg import SHG


@pytest.mark.asyncio
async def test_role_matrix_list_users(
    client: AsyncClient,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    # Admin allowed (200)
    assert (await client.get("/api/v1/users", headers=admin_headers)).status_code == 200

    # Leader, Auditor, Member forbidden (403)
    assert (await client.get("/api/v1/users", headers=leader_headers)).status_code == 403
    assert (await client.get("/api/v1/users", headers=auditor_headers)).status_code == 403
    assert (await client.get("/api/v1/users", headers=member_headers)).status_code == 403


@pytest.mark.asyncio
async def test_role_matrix_create_group(
    client: AsyncClient,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    payload = {
        "name": "New Test Group Matrix",
        "village": "Village Z",
        "district": "District Z",
        "formation_date": "2025-01-01",
        "meeting_day": "Tuesday",
        "meeting_frequency": "MONTHLY",
    }
    # Admin allowed (201)
    assert (await client.post("/api/v1/groups", headers=admin_headers, json=payload)).status_code == 201

    # Leader, Auditor, Member forbidden (403)
    assert (await client.post("/api/v1/groups", headers=leader_headers, json=payload)).status_code == 403
    assert (await client.post("/api/v1/groups", headers=auditor_headers, json=payload)).status_code == 403
    assert (await client.post("/api/v1/groups", headers=member_headers, json=payload)).status_code == 403


@pytest.mark.asyncio
async def test_role_matrix_get_assigned_group(
    client: AsyncClient,
    test_group: SHG,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    # All assigned roles have read access to their assigned group
    assert (await client.get(f"/api/v1/groups/{test_group.id}", headers=admin_headers)).status_code == 200
    assert (await client.get(f"/api/v1/groups/{test_group.id}", headers=leader_headers)).status_code == 200
    assert (await client.get(f"/api/v1/groups/{test_group.id}", headers=auditor_headers)).status_code == 200
    assert (await client.get(f"/api/v1/groups/{test_group.id}", headers=member_headers)).status_code == 200


@pytest.mark.asyncio
async def test_role_matrix_update_assigned_group(
    client: AsyncClient,
    test_group: SHG,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    # Admin and Leader can update assigned group
    assert (await client.patch(f"/api/v1/groups/{test_group.id}", headers=admin_headers, json={"name": "Renamed 1"})).status_code == 200
    assert (await client.patch(f"/api/v1/groups/{test_group.id}", headers=leader_headers, json={"name": "Renamed 2"})).status_code == 200

    # Auditor and Member are forbidden (403)
    assert (await client.patch(f"/api/v1/groups/{test_group.id}", headers=auditor_headers, json={"name": "Renamed 3"})).status_code == 403
    assert (await client.patch(f"/api/v1/groups/{test_group.id}", headers=member_headers, json={"name": "Renamed 4"})).status_code == 403


@pytest.mark.asyncio
async def test_role_matrix_create_member_assigned_group(
    client: AsyncClient,
    test_group: SHG,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    payload = {
        "full_name": "New Enrolled Member",
        "phone": "9876543299",
        "joined_on": "2025-01-01",
        "id_proof_number": "123456789012",
        "role": "MEMBER",
    }
    # Admin and Leader can enroll member
    assert (await client.post(f"/api/v1/groups/{test_group.id}/members", headers=admin_headers, json=payload)).status_code == 201
    assert (await client.post(f"/api/v1/groups/{test_group.id}/members", headers=leader_headers, json=payload)).status_code == 201

    # Auditor and Member are forbidden (403)
    assert (await client.post(f"/api/v1/groups/{test_group.id}/members", headers=auditor_headers, json=payload)).status_code == 403
    assert (await client.post(f"/api/v1/groups/{test_group.id}/members", headers=member_headers, json=payload)).status_code == 403


@pytest.mark.asyncio
async def test_cross_group_access_returns_404(
    client: AsyncClient,
    other_group: SHG,
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    """
    SPEC Section 2 non-negotiable rule:
    Object-level queries on group-scoped data must filter by caller's permitted group IDs.
    Out-of-scope objects return 404 (not 403) to prevent existence leakage.
    """
    # Group detail on unassigned group -> 404
    assert (await client.get(f"/api/v1/groups/{other_group.id}", headers=leader_headers)).status_code == 404
    assert (await client.get(f"/api/v1/groups/{other_group.id}", headers=auditor_headers)).status_code == 404
    assert (await client.get(f"/api/v1/groups/{other_group.id}", headers=member_headers)).status_code == 404

    # Group settings on unassigned group -> 404
    assert (await client.get(f"/api/v1/groups/{other_group.id}/settings", headers=leader_headers)).status_code == 404
    assert (await client.put(f"/api/v1/groups/{other_group.id}/settings", headers=leader_headers, json={"late_fine_per_day": "15.00"})).status_code == 404

    # Group members on unassigned group -> 404
    assert (await client.get(f"/api/v1/groups/{other_group.id}/members", headers=leader_headers)).status_code == 404
    assert (await client.post(f"/api/v1/groups/{other_group.id}/members", headers=leader_headers, json={"full_name": "Test", "joined_on": "2025-01-01"})).status_code == 404


@pytest.mark.asyncio
async def test_pii_masking_for_auditors_and_members(
    client: AsyncClient,
    test_group: SHG,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    # 1. Admin and Leader see full phone/address
    res_admin = await client.get(f"/api/v1/groups/{test_group.id}/members", headers=admin_headers)
    assert res_admin.status_code == 200
    admin_m = res_admin.json()["items"][0]
    assert admin_m["phone"] == "9876543213"
    assert "House 1" in admin_m["address"]

    res_leader = await client.get(f"/api/v1/groups/{test_group.id}/members", headers=leader_headers)
    assert res_leader.status_code == 200
    leader_m = res_leader.json()["items"][0]
    assert leader_m["phone"] == "9876543213"

    # 2. Auditor sees masked phone and address
    res_auditor = await client.get(f"/api/v1/groups/{test_group.id}/members", headers=auditor_headers)
    assert res_auditor.status_code == 200
    auditor_m = res_auditor.json()["items"][0]
    assert auditor_m["phone"] == "******3213"
    assert auditor_m["address"] == "***, Village A"
    assert auditor_m["id_proof_last4"] == "1234"
