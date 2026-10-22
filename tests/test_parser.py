"""Pruebas del parser Syslog: PRI, severidad, facility y formatos de cada fabricante."""
from noc.syslog_parser import parsear


def test_pri_calcula_facility_y_severidad():
    m = parsear("<189>Oct  9 10:00:00 equipo app: hola")
    assert m.facility == 23 and m.facility_nombre == "local7"
    assert m.severidad == 5 and m.severidad_nombre == "Notice"


def test_sin_pri_usa_valor_por_defecto_rfc3164():
    m = parsear("mensaje sin cabecera")
    assert (m.facility, m.severidad) == (1, 5)
    assert m.formato == "sin_formato"


def test_pri_invalido_se_ignora():
    assert parsear("<999>texto").severidad == 5


def test_cisco():
    m = parsear("<187>45: *Oct  9 02:13:00.123: %LINK-3-UPDOWN: Interface Gi0/1, changed state to down")
    assert m.formato == "cisco" and m.marca_detectada == "Cisco"
    assert m.severidad == 3 and m.app == "LINK-3-UPDOWN"
    assert m.fecha_evento.endswith("T02:13:00")


def test_fortinet():
    m = parsear('<185>date=2026-10-09 time=10:00:01 devname="FW01" logid="0100032002" type="event" '
                'subtype="system" level="alert" msg="Administrator admin login failed"')
    assert m.formato == "fortinet" and m.marca_detectada == "Fortinet"
    assert m.hostname == "FW01" and m.fecha_evento == "2026-10-09T10:00:01"
    assert m.severidad == 1


def test_huawei():
    m = parsear("<188>Oct 09 2026 10:00:00 SW01 %%01IFNET/4/IF_STATE(l)[3]:Interface GE0/0/1 has turned into DOWN state.")
    assert m.marca_detectada == "Huawei" and m.hostname == "SW01"
    assert m.app == "%%01IFNET/4/IF_STATE(l)"  # sin el contador [3]
    assert m.fecha_evento == "2026-10-09T10:00:00"


def test_rfc5424():
    m = parsear("<34>1 2026-10-09T22:14:15.003Z host1 su - ID47 - su root failed")
    assert m.formato == "rfc5424" and m.facility_nombre == "auth" and m.severidad == 2
    assert m.hostname == "host1" and m.app == "su"
