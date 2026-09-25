import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    print("=" * 70)
    print("STARTING FOREST OFFICER USER MANAGEMENT END-TO-END VERIFICATION")
    print("=" * 70)

    # 1. Forest Officer Logs In
    print("\n[STEP 1] Forest Officer logs in...")
    officer_session = requests.Session()
    login_resp = officer_session.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "officer@forest.gov.in",
        "password": "Officer@2026!",
        "role": "forest_officer"
    })
    assert login_resp.status_code == 200, f"Officer login failed: {login_resp.text}"
    login_data = login_resp.json()
    assert login_data.get('role') == 'forest_officer'
    print(f"  -> Officer Login Success! User: {login_data.get('name')}, Role: {login_data.get('role')}")

    # 2. Opens User Management
    print("\n[STEP 2] Forest Officer opens User Management (API & page)...")
    admin_users_resp = officer_session.get(f"{BASE_URL}/api/admin/users")
    assert admin_users_resp.status_code == 200, f"Failed to list users: {admin_users_resp.text}"
    users = admin_users_resp.json().get('users', [])
    print(f"  -> Successfully fetched user directory: {len(users)} registered users found.")

    admin_page_resp = officer_session.get(f"{BASE_URL}/user-management")
    assert admin_page_resp.status_code == 200, f"Failed to load /user-management: {admin_page_resp.status_code}"
    assert "user-mgmt-tab" in admin_page_resp.text
    print("  -> /user-management page accessible and renders user-mgmt-tab successfully.")

    ts = int(time.time())
    new_villager_email = f"test_villager_{ts}@anekal.gov.in"
    new_villager_pass = "TestVillager@2026!"

    # 3. Creates a Villager
    print("\n[STEP 3] Forest Officer creates a new Villager user...")
    create_villager_resp = officer_session.post(f"{BASE_URL}/api/admin/users/create", json={
        "full_name": f"Ramesh Gowda {ts}",
        "email": new_villager_email,
        "phone": "+919876500001",
        "role": "villager",
        "location": "Muthyalamadavu Valley",
        "password": new_villager_pass
    })
    assert create_villager_resp.status_code in [200, 201], f"Create villager failed: {create_villager_resp.text}"
    villager_data = create_villager_resp.json()
    assert villager_data.get("message") == "User created successfully"
    villager_user_id = villager_data["user"]["id"]
    print(f"  -> Villager created! Message: '{villager_data.get('message')}', ID: {villager_user_id}")

    # 4 & 5. Villager receives/uses credentials and logs in
    print("\n[STEP 4 & 5] New Villager logs in with credentials...")
    villager_session = requests.Session()
    villager_login = villager_session.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": new_villager_email,
        "password": new_villager_pass,
        "role": "villager"
    })
    assert villager_login.status_code == 200, f"Villager login failed: {villager_login.text}"
    print(f"  -> Villager authenticated! Redirect: {villager_login.json().get('redirect_url')}")

    # 6. Villager reaches Villager Dashboard
    print("\n[STEP 6] Villager accesses Villager Dashboard...")
    v_dash_resp = villager_session.get(f"{BASE_URL}/villager")
    assert v_dash_resp.status_code == 200
    assert "Villager Safety Portal" in v_dash_resp.text or "Villager" in v_dash_resp.text
    print("  -> Villager reaches Villager Dashboard (/villager) successfully.")

    # 7. Villager CANNOT access User Management
    print("\n[STEP 7] Villager attempts to access User Management & Admin routes (Security enforcement)...")
    v_admin_api = villager_session.get(f"{BASE_URL}/api/admin/users")
    assert v_admin_api.status_code == 403, f"Expected 403 for API, got {v_admin_api.status_code}"
    print(f"  -> [SECURE] Villager blocked from /api/admin/users with HTTP {v_admin_api.status_code} Forbidden.")

    for route in ["/admin", "/user-management", "/forest-officer/users"]:
        v_route = villager_session.get(f"{BASE_URL}{route}")
        assert v_route.status_code == 403, f"Expected 403 on {route}, got {v_route.status_code}"
        print(f"  -> [SECURE] Villager blocked from {route} with HTTP {v_route.status_code} Forbidden.")

    # 8. Forest Officer creates Police user
    print("\n[STEP 8] Forest Officer creates a Police user...")
    new_police_email = f"test_police_{ts}@ksp.gov.in"
    new_police_pass = "TestPolice@2026!"
    create_police_resp = officer_session.post(f"{BASE_URL}/api/admin/users/create", json={
        "full_name": f"Sub-Inspector Kumar {ts}",
        "email": new_police_email,
        "phone": "+919448000002",
        "role": "police",
        "location": "Jigani Police Station",
        "password": new_police_pass
    })
    assert create_police_resp.status_code in [200, 201], f"Create police failed: {create_police_resp.text}"
    print(f"  -> Police user created! Email: {new_police_email}")

    # 9. Police logs in
    print("\n[STEP 9] New Police user logs in...")
    police_session = requests.Session()
    police_login = police_session.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": new_police_email,
        "password": new_police_pass,
        "role": "police"
    })
    assert police_login.status_code == 200, f"Police login failed: {police_login.text}"
    print(f"  -> Police authenticated! Redirect: {police_login.json().get('redirect_url')}")

    # 10. Police reaches Police Dashboard
    print("\n[STEP 10] Police reaches Police Dashboard...")
    p_dash_resp = police_session.get(f"{BASE_URL}/police")
    assert p_dash_resp.status_code == 200
    print("  -> Police reaches Police Dashboard (/police) successfully.")

    # 11. Police CANNOT access User Management
    print("\n[STEP 11] Police attempts to access User Management & Admin routes...")
    p_admin_api = police_session.get(f"{BASE_URL}/api/admin/users")
    assert p_admin_api.status_code == 403
    print(f"  -> [SECURE] Police blocked from /api/admin/users with HTTP {p_admin_api.status_code} Forbidden.")

    for route in ["/admin", "/user-management", "/forest-officer/users"]:
        p_route = police_session.get(f"{BASE_URL}{route}")
        assert p_route.status_code == 403
        print(f"  -> [SECURE] Police blocked from {route} with HTTP {p_route.status_code} Forbidden.")

    # 12. Forest Officer creates another Forest Officer
    print("\n[STEP 12] Forest Officer creates another Forest Officer...")
    new_officer_email = f"test_officer_{ts}@forest.gov.in"
    new_officer_pass = "TestOfficer@2026!"
    create_officer_resp = officer_session.post(f"{BASE_URL}/api/admin/users/create", json={
        "full_name": f"Deputy Conservator {ts}",
        "email": new_officer_email,
        "phone": "+919845000003",
        "role": "forest_officer",
        "location": "Bannerghatta North Range",
        "password": new_officer_pass
    })
    assert create_officer_resp.status_code in [200, 201], f"Create officer failed: {create_officer_resp.text}"
    print(f"  -> New Forest Officer created! Email: {new_officer_email}")

    # 13. New Forest Officer can log in
    print("\n[STEP 13] New Forest Officer logs in...")
    new_officer_session = requests.Session()
    new_officer_login = new_officer_session.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": new_officer_email,
        "password": new_officer_pass,
        "role": "forest_officer"
    })
    assert new_officer_login.status_code == 200, f"New officer login failed: {new_officer_login.text}"
    print(f"  -> New Forest Officer authenticated successfully! Role: {new_officer_login.json().get('role')}")

    new_officer_mgmt = new_officer_session.get(f"{BASE_URL}/api/admin/users")
    assert new_officer_mgmt.status_code == 200
    print("  -> New Forest Officer can access User Management APIs!")

    # EXTRA TEST: User Status Toggle (Disable/Deactivate & Reactivate)
    print("\n[EXTRA STEP] Testing User Deactivation / Activation...")
    disable_resp = officer_session.post(f"{BASE_URL}/api/admin/users/toggle-status", json={
        "user_id": villager_user_id,
        "status": "Inactive"
    })
    assert disable_resp.status_code == 200
    print("  -> Villager account set to 'Inactive'.")

    # Disabled user attempts to login -> must be denied with 403
    inactive_login = requests.Session().post(f"{BASE_URL}/api/auth/login", json={
        "identifier": new_villager_email,
        "password": new_villager_pass,
        "role": "villager"
    })
    assert inactive_login.status_code == 403, f"Expected 403 for deactivated user, got {inactive_login.status_code}"
    print(f"  -> [SECURE] Inactive user login blocked with HTTP 403: {inactive_login.json().get('error')}")

    # Reactivate user
    enable_resp = officer_session.post(f"{BASE_URL}/api/admin/users/toggle-status", json={
        "user_id": villager_user_id,
        "status": "Active"
    })
    assert enable_resp.status_code == 200
    print("  -> Villager account reactivated to 'Active'.")

    reactivated_login = requests.Session().post(f"{BASE_URL}/api/auth/login", json={
        "identifier": new_villager_email,
        "password": new_villager_pass,
        "role": "villager"
    })
    assert reactivated_login.status_code == 200
    print("  -> Reactivated villager can log in successfully.")

    # 14. Logout works
    print("\n[STEP 14] Testing Logout...")
    logout_resp = officer_session.post(f"{BASE_URL}/api/auth/logout")
    assert logout_resp.status_code == 200
    check_session = officer_session.get(f"{BASE_URL}/api/auth/current-user")
    assert check_session.json().get("authenticated") is False
    print("  -> Logout cleared session successfully!")

    print("\n" + "=" * 70)
    print("ALL 14 TESTS + SECURITY & STATUS CHECKS PASSED PERFECTLY!")
    print("=" * 70)

if __name__ == '__main__':
    run_tests()
