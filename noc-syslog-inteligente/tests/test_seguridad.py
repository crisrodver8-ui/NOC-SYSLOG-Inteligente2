"""Pruebas de seguridad: lista de comandos de la consola y catálogo cerrado de acciones."""
from noc import consola
from noc.catalogo_acciones import AccionInvalida, construir_comando


def test_consola_permite_y_bloquea():
    assert consola.validar("Cisco", "show version")[0]
    assert consola.validar("Cisco", "SHOW   VERSION")[0]                 # normaliza espacios y mayúsculas
    assert not consola.validar("Cisco", "configure terminal")[0]
    assert not consola.validar("Cisco", "show version ; reload")[0]      # encadenamiento
    assert not consola.validar("Huawei", "show version")[0]              # comando de otra marca
    assert not consola.validar("Fortinet", "execute reboot")[0]


def test_catalogo_valida_parametros():
    assert construir_comando("bloquear_ip", "Cisco", "203.0.113.5").count("203.0.113.5") == 1
    for tipo, param in (("bloquear_ip", "1.1.1.1; reload"), ("deshabilitar_cuenta", "x\nreload"), ("borrar_todo", "")):
        try:
            construir_comando(tipo, "Cisco", param)
            raise AssertionError("debió rechazarse")
        except AccionInvalida:
            pass
