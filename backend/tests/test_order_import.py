"""P6c: CSV / Excel order import with a row-level validation report."""
import io

import pytest
from app.services.order_import import MAX_ROWS, ImportFileError, parse_orders
from openpyxl import Workbook


def csv_bytes(text: str) -> bytes:
    return text.strip().encode()


def test_valid_csv_gives_customers():
    rep = parse_orders("orders.csv", csv_bytes("""
ID, X, Y, Demand, ready_time, due_time, service_time
1, 3, 0, 2, 0, 100, 5
2, 3.5, 4, 2, , ,
"""))
    d = rep.to_dict()
    assert d["ok"] and d["rows"] == 2 and d["invalid_rows"] == 0
    assert d["customers"][0] == {"id": 1, "x": 3.0, "y": 0.0, "demand": 2, "ready_time": 0.0, "due_time": 100.0,
                                 "service_time": 5.0}
    assert d["customers"][1] == {"id": 2, "x": 3.5, "y": 4.0, "demand": 2}


def test_every_bad_row_is_reported_with_row_number_and_nothing_is_imported():
    rep = parse_orders("orders.csv", csv_bytes("""
id,x,y,demand,ready_time,due_time
1,3,0,2,10,5
1,1,1,2,,
x,1,1,0,,
4,,1,abc,-1,
5,1,1,3,,
"""))
    d = rep.to_dict()
    assert not d["ok"] and d["customers"] == []
    assert d["rows"] == 5 and d["valid_rows"] == 1 and d["invalid_rows"] == 4
    got = {(i["row"], i["field"]) for i in d["issues"]}
    assert (2, "due_time") in got  # due before ready
    assert (3, "id") in got  # duplicate id, header is row 1
    assert {(4, "id"), (4, "demand")} <= got
    assert {(5, "x"), (5, "demand"), (5, "ready_time")} <= got
    assert "first on row 2" in next(i["message"] for i in d["issues"] if i["row"] == 3)


def test_lon_lat_columns_are_accepted_and_range_checked():
    rep = parse_orders("o.csv", csv_bytes("customer_id,lon,lat,demand\n1,77.6,12.9,1\n2,200,95,1"))
    assert rep.coordinates == "lonlat"
    assert {(i.row, i.field) for i in rep.issues} == {(3, "lon"), (3, "lat")}


def test_excel_file_is_read():
    wb = Workbook()
    ws = wb.active
    ws.append(["id", "x", "y", "demand"])
    ws.append([1, 3, 0, 2])
    ws.append([2, -3, 0, 2.5])
    buf = io.BytesIO()
    wb.save(buf)
    d = parse_orders("orders.xlsx", buf.getvalue()).to_dict()
    assert d["rows"] == 2 and d["valid_rows"] == 1
    assert d["issues"] == [{"row": 3, "field": "demand", "message": "must be a whole number > 0"}]


@pytest.mark.parametrize("name,data,msg", [
    ("orders.txt", b"id,x,y,demand\n1,1,1,1", ".csv or .xlsx"),
    ("orders.csv", b"", "empty"),
    ("orders.csv", b"id,x,demand\n1,1,1", "missing required column(s): y"),
    ("orders.csv", b"id,x,y,demand", "no data rows"),
    ("orders.csv", b"id,x,y,demand,x\n1,1,1,1,1", "duplicate column"),
    ("orders.csv", "id,x,y,demand\n".encode() + b"\n".join(b"%d,1,1,1" % i for i in range(1, MAX_ROWS + 2)),
     "too many rows"),
    ("orders.xlsx", b"not a zip", "cannot read Excel"),
    ("orders.csv", b"\xff\xfe\x00id", "UTF-8"),
])
def test_unreadable_files_are_rejected_as_a_whole(name, data, msg):
    with pytest.raises(ImportFileError, match=msg.replace("(", r"\(").replace(")", r"\)").replace(".", r"\.")):
        parse_orders(name, data)


def test_import_endpoint_reports_rows_and_needs_a_key(tmp_path):
    from app.db.keys import create_tenant, issue_key
    from app.db.models import AuditLog
    from app.db.session import admin_session
    from app.main import create_app
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    app = create_app(tmp_path)
    with TestClient(app) as c:
        with admin_session(app.state.db) as s:
            t = create_tenant(s, "A")
            _, key = issue_key(s, t.id)
            s.commit()
        files = {"file": ("orders.csv", b"id,x,y,demand\n1,1,1,1\n2,1,1,0", "text/csv")}
        assert c.post("/api/orders/import", files=files).status_code == 401
        r = c.post("/api/orders/import", files=files, headers={"X-API-Key": key})
        assert r.status_code == 200
        body = r.json()
        assert not body["ok"] and body["issues"] == [{"row": 3, "field": "demand",
                                                      "message": "must be a whole number > 0"}]
        bad = c.post("/api/orders/import", files={"file": ("o.txt", b"x", "text/plain")}, headers={"X-API-Key": key})
        assert bad.status_code == 422 and ".csv or .xlsx" in bad.json()["detail"]["message"]
        with admin_session(app.state.db) as s:
            assert [a.action for a in s.scalars(select(AuditLog))] == ["orders.import", "orders.import"]
