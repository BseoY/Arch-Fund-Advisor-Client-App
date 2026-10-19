import pytest
from fastapi.testclient import TestClient

from arch_morning_view.app import app
from arch_morning_view.store import store


@pytest.fixture(autouse=True)
def empty_store():
    store.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def setup_advisor(client: TestClient, name: str = "Ada", password: str = "password") -> dict:
    response = client.post("/advisor", json={"name": name, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def call(title: str = "Q3", amount: float = 500, due_date: str = "2026-12-01") -> dict:
    return {"kind": "capital_call", "title": title, "amount": amount, "dueDate": due_date}


def test_first_run_creates_the_advisor_and_hashes_the_password(client: TestClient):
    assert client.get("/advisor").json() is False
    session = setup_advisor(client)
    assert session["role"] == "advisor"
    assert session["name"] == "Ada"
    assert "clientId" not in session
    assert client.get("/advisor").json() is True
    assert all(row.password_hash != "password" for row in store.users)
    assert all("password" not in row.password_hash for row in store.users)

    again = client.post("/advisor", json={"name": "", "password": ""})
    assert again.status_code == 409
    assert again.json()["detail"] == "The advisor already exists."


def test_setup_requires_name_and_password(client: TestClient):
    response = client.post("/advisor", json={"name": "  ", "password": "secret"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Name and password are required."


def test_login_session_and_logout(client: TestClient):
    created = setup_advisor(client)
    bad = client.post("/login", json={"name": "Ada", "password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Wrong name or password."

    signed_in = client.post("/login", json={"name": "  ada  ", "password": "password"})
    assert signed_in.status_code == 200
    body = signed_in.json()
    assert body["name"] == "Ada"
    assert body["token"] != created["token"]

    assert client.get("/session").json() is None
    assert client.get("/session", headers=auth("missing")).json() is None
    current = client.get("/session", headers=auth(body["token"]))
    assert current.json()["token"] == body["token"]

    assert client.post("/logout").status_code == 401
    assert client.post("/logout", headers=auth("missing")).status_code == 204
    assert client.post("/logout", headers=auth(body["token"])).status_code == 204
    assert client.get("/session", headers=auth(body["token"])).json() is None


def test_client_login_includes_client_id_and_cannot_manage_clients(client: TestClient):
    advisor = setup_advisor(client)
    created = client.post("/clients", headers=auth(advisor["token"]), json={"name": "Bea", "password": "secret"})
    assert created.status_code == 201
    bea = client.post("/login", json={"name": "Bea", "password": "secret"}).json()
    assert bea["role"] == "client"
    assert bea["clientId"] == created.json()["id"]

    denied = client.get("/clients", headers=auth(bea["token"]))
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Only the advisor can do that."
    missing = client.get("/clients")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Please sign in again."


def test_names_are_unique_without_case(client: TestClient):
    advisor = setup_advisor(client)
    taken = client.post("/clients", headers=auth(advisor["token"]), json={"name": " ada ", "password": "secret"})
    assert taken.status_code == 409
    assert taken.json()["detail"] == "That name is already used."


def test_morning_view_orders_unpaid_calls_and_paid_status_is_advisor_only(client: TestClient):
    advisor = setup_advisor(client)
    bea = client.post("/clients", headers=auth(advisor["token"]), json={"name": "Bea", "password": "pw"}).json()
    fund_a = client.post(f"/clients/{bea['id']}/funds", headers=auth(advisor["token"]), json={"name": "Fund A"}).json()
    fund_b = client.post(f"/clients/{bea['id']}/funds", headers=auth(advisor["token"]), json={"name": "Fund B"}).json()
    client.post(f"/funds/{fund_a['id']}/documents", headers=auth(advisor["token"]), json=call("Q3", 500, "2026-12-01"))
    earlier = client.post(
        f"/funds/{fund_b['id']}/documents",
        headers=auth(advisor["token"]),
        json=call("Q2", 250, "2026-11-01"),
    ).json()
    client.post(
        f"/funds/{fund_a['id']}/documents",
        headers=auth(advisor["token"]),
        json={"kind": "investor_letter", "title": "L", "summary": "New GP"},
    )

    overview = client.get(f"/clients/{bea['id']}", headers=auth(advisor["token"])).json()
    assert [(item["fundName"], item["amount"], item["dueDate"]) for item in overview["morning"]] == [
        ("Fund B", 250, "2026-11-01"),
        ("Fund A", 500, "2026-12-01"),
    ]
    assert [fund["name"] for fund in overview["funds"]] == ["Fund A", "Fund B"]

    paid = client.patch(f"/documents/{earlier['id']}/paid", headers=auth(advisor["token"]), json={"paid": True})
    assert paid.status_code == 204
    overview = client.get(f"/clients/{bea['id']}", headers=auth(advisor["token"])).json()
    assert [(item["fundName"], item["title"]) for item in overview["morning"]] == [("Fund A", "Q3")]
    saved = next(doc for fund in overview["funds"] if fund["name"] == "Fund B" for doc in fund["documents"])
    assert saved["paid"] is True
    assert "checked" not in saved

    client.patch(f"/documents/{earlier['id']}/paid", headers=auth(advisor["token"]), json={"paid": False})
    overview = client.get(f"/clients/{bea['id']}", headers=auth(advisor["token"])).json()
    assert len(overview["morning"]) == 2

    bea_session = client.post("/login", json={"name": "Bea", "password": "pw"}).json()
    denied = client.patch(
        f"/documents/{earlier['id']}/paid",
        headers=auth(bea_session["token"]),
        json={"paid": True},
    )
    assert denied.status_code == 403

    letter = next(doc for fund in overview["funds"] for doc in fund["documents"] if doc["kind"] == "investor_letter")
    not_a_call = client.patch(f"/documents/{letter['id']}/paid", headers=auth(advisor["token"]), json={"paid": True})
    assert not_a_call.status_code == 400
    assert not_a_call.json()["detail"] == "Only capital calls can be paid."


def test_checkmark_is_private_and_clients_are_separated(client: TestClient):
    advisor = setup_advisor(client)
    headers = auth(advisor["token"])
    bea = client.post("/clients", headers=headers, json={"name": "Bea", "password": "pw"}).json()
    cal = client.post("/clients", headers=headers, json={"name": "Cal", "password": "pw"}).json()
    bea_fund = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "Bea Fund"}).json()
    cal_fund = client.post(f"/clients/{cal['id']}/funds", headers=headers, json={"name": "Cal Fund"}).json()
    bea_doc = client.post(f"/funds/{bea_fund['id']}/documents", headers=headers, json=call("Q", 1, "2026-01-01")).json()
    cal_doc = client.post(f"/funds/{cal_fund['id']}/documents", headers=headers, json=call("Q", 1, "2026-02-01")).json()
    bea_token = client.post("/login", json={"name": "Bea", "password": "pw"}).json()["token"]

    other = client.get(f"/clients/{cal['id']}", headers=auth(bea_token))
    assert other.status_code == 404
    assert other.json()["detail"] == "Client not found."
    own = client.get(f"/clients/{bea['id']}", headers=auth(bea_token)).json()
    assert own["funds"][0]["documents"][0]["checked"] is False

    stolen = client.patch(f"/documents/{cal_doc['id']}/checked", headers=auth(bea_token), json={"checked": True})
    assert stolen.status_code == 404
    assert stolen.json()["detail"] == "Document not found."

    advisor_check = client.patch(f"/documents/{bea_doc['id']}/checked", headers=headers, json={"checked": True})
    assert advisor_check.status_code == 403
    assert advisor_check.json()["detail"] == "Only a client can do that."

    assert client.patch(f"/documents/{bea_doc['id']}/checked", headers=auth(bea_token), json={"checked": True}).status_code == 204
    mine = client.get(f"/clients/{bea['id']}", headers=auth(bea_token)).json()
    assert mine["funds"][0]["documents"][0]["checked"] is True
    assert mine["funds"][0]["documents"][0]["paid"] is False
    assert mine["morning"][0]["documentId"] == bea_doc["id"]
    advisor_view = client.get(f"/clients/{bea['id']}", headers=headers).json()
    assert "checked" not in advisor_view["funds"][0]["documents"][0]


def test_replacing_a_document_keeps_paid_status(client: TestClient):
    advisor = setup_advisor(client)
    headers = auth(advisor["token"])
    bea = client.post("/clients", headers=headers, json={"name": "Bea", "password": "pw"}).json()
    fund = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "Fund A"}).json()
    document = client.post(f"/funds/{fund['id']}/documents", headers=headers, json=call()).json()
    client.patch(f"/documents/{document['id']}/paid", headers=headers, json={"paid": True})

    replaced = client.put(
        f"/documents/{document['id']}",
        headers=headers,
        json={"kind": "investor_letter", "title": "Letter", "summary": "Changed"},
    )
    assert replaced.status_code == 200
    assert replaced.json()["kind"] == "investor_letter"
    assert "paid" not in replaced.json()

    restored = client.put(f"/documents/{document['id']}", headers=headers, json=call("Q3 again", 500, "2026-12-01"))
    assert restored.json()["paid"] is True
    overview = client.get(f"/clients/{bea['id']}", headers=headers).json()
    assert overview["morning"] == []


def test_document_validation_messages(client: TestClient):
    advisor = setup_advisor(client)
    headers = auth(advisor["token"])
    bea = client.post("/clients", headers=headers, json={"name": "Bea", "password": "pw"}).json()
    fund = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "Fund A"}).json()

    cases = [
        ({"kind": "capital_call", "title": "  ", "amount": 10, "dueDate": "2026-01-01"}, "A document needs a title."),
        ({"kind": "capital_call", "title": "Q", "amount": 0, "dueDate": "2026-01-01"}, "Amount due must be greater than zero."),
        ({"kind": "capital_call", "title": "Q", "amount": 10, "dueDate": "January"}, "Due date is required."),
        ({"kind": "investor_letter", "title": "L", "summary": " "}, "An investor letter needs a summary."),
        ({"kind": "other", "title": "L"}, "Unknown document type."),
    ]
    for body, detail in cases:
        response = client.post(f"/funds/{fund['id']}/documents", headers=headers, json=body)
        assert response.status_code == 400
        assert response.json()["detail"] == detail

    missing_fund = client.post("/funds/missing/documents", headers=headers, json={"title": ""})
    assert missing_fund.status_code == 404
    assert missing_fund.json()["detail"] == "Fund not found."


def test_deleting_a_client_removes_login_funds_and_documents(client: TestClient):
    advisor = setup_advisor(client)
    headers = auth(advisor["token"])
    bea = client.post("/clients", headers=headers, json={"name": "Bea", "password": "pw"}).json()
    fund = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "F"}).json()
    client.post(f"/funds/{fund['id']}/documents", headers=headers, json=call())
    assert client.delete(f"/clients/{bea['id']}", headers=headers).status_code == 204
    assert client.post("/login", json={"name": "Bea", "password": "pw"}).status_code == 401
    overview = client.get(f"/clients/{bea['id']}", headers=headers)
    assert overview.status_code == 404
    assert store.funds == []
    assert store.documents == []
    assert client.delete("/clients/missing", headers=headers).status_code == 204


def test_deleting_a_fund_removes_its_documents(client: TestClient):
    advisor = setup_advisor(client)
    headers = auth(advisor["token"])
    bea = client.post("/clients", headers=headers, json={"name": "Bea", "password": "pw"}).json()
    fund = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "F"}).json()
    client.post(f"/funds/{fund['id']}/documents", headers=headers, json=call())
    assert client.delete(f"/funds/{fund['id']}", headers=headers).status_code == 204
    overview = client.get(f"/clients/{bea['id']}", headers=headers).json()
    assert overview["funds"] == []
    assert overview["morning"] == []
    missing = client.delete("/funds/missing", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Fund not found."


def test_rename_client_and_fund(client: TestClient):
    advisor = setup_advisor(client)
    headers = auth(advisor["token"])
    bea = client.post("/clients", headers=headers, json={"name": "Bea", "password": "pw"}).json()
    renamed = client.patch(f"/clients/{bea['id']}", headers=headers, json={"name": "Beatrice", "password": "next"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Beatrice"
    assert client.post("/login", json={"name": "Beatrice", "password": "next"}).status_code == 200
    assert client.post("/login", json={"name": "Bea", "password": "pw"}).status_code == 401

    fund = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "  "})
    assert fund.status_code == 400
    assert fund.json()["detail"] == "Fund name is required."
    created = client.post(f"/clients/{bea['id']}/funds", headers=headers, json={"name": "Old"}).json()
    updated = client.patch(f"/funds/{created['id']}", headers=headers, json={"name": "New"})
    assert updated.json()["name"] == "New"
    missing = client.post("/clients/missing/funds", headers=headers, json={"name": ""})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Client not found."


def test_seeded_store_shows_a_morning_list():
    store.seed()
    with TestClient(app) as client:
        advisor = client.post("/login", json={"name": "Ada", "password": "password"}).json()
        bea = client.post("/login", json={"name": "Bea", "password": "password"}).json()
        clients = client.get("/clients", headers=auth(advisor["token"])).json()
        assert [row["name"] for row in clients] == ["Bea", "Cal"]
        overview = client.get(f"/clients/{bea['clientId']}", headers=auth(advisor["token"])).json()
        assert [(item["fundName"], item["title"], item["amount"], item["dueDate"]) for item in overview["morning"]] == [
            ("Northwind Growth", "Q3 capital call", 250000, "2026-11-01"),
            ("Harbor Credit", "October call", 75000, "2026-11-20"),
            ("Northwind Growth", "Q4 capital call", 500000, "2026-12-15"),
        ]
        assert [fund["name"] for fund in overview["funds"]] == ["Harbor Credit", "Northwind Growth"]
        northwind = overview["funds"][1]
        assert [doc["title"] for doc in northwind["documents"]] == [
            "Quarterly letter",
            "Q4 capital call",
            "Q3 capital call",
            "Q2 capital call",
        ]
        assert "checked" not in northwind["documents"][2]
        bea_view = client.get(f"/clients/{bea['clientId']}", headers=auth(bea["token"])).json()
        q3 = next(doc for doc in bea_view["funds"][1]["documents"] if doc["title"] == "Q3 capital call")
        assert q3["checked"] is True
        assert q3["paid"] is False
