# Laboratorio GNS3 / EVE-NG para la integración y la marcha blanca (v1.0.0)

Esta guía conecta el NOC (que corre en Windows) con **equipos virtuales reales** en GNS3. Con eso se prueban el receptor Syslog, el gestor SSH, la consola, los puertos y la ejecución de acciones aprobadas.

> **Sin GNS3 disponible:** `python tools/equipo_virtual.py --syslog 127.0.0.1:5514` levanta un router Cisco virtual (SSH en 2222, consola telnet en 5099) que envía Syslog al NOC cuando se configura. Sirve para ensayar, pero **la evidencia de la marcha blanca debe ser con GNS3**.

## 1. Topología propuesta

```
                       Red de gestión 192.168.56.0/24 (Host-Only)
   ┌──────────────┐          │
   │  PC Windows  │──────────┤
   │  NOC         │ .1       │
   │  UDP 5514    │          ├── R1-BORDE   (Cisco IOSv)      Gi0/0  .11
   │  Web 8080    │          ├── SW1-ACCESO (Cisco IOSvL2)    Vlan1  .12
   └──────────────┘          ├── FW1        (FortiGate-VM)    port1  .13  (opcional)
                             └── R2-HUAWEI  (Huawei AR/CE)    GE0/0/0 .14 (opcional)

   Enlace de datos: R1-BORDE Gi0/1 (10.0.12.1/30) ─── SW1-ACCESO Gi0/1
```

- **Mínimo para aprobar:** R1-BORDE + SW1-ACCESO (imágenes Cisco de GNS3/CML).
- FortiGate-VM y Huawei son opcionales, según las imágenes que tenga el laboratorio. Las configuraciones de esas marcas se generan igual en la vista **Configuraciones**.

## 2. Red entre Windows y GNS3

### Opción A: GNS3 VM (recomendada para IOSv)
1. En VirtualBox o VMware, la GNS3 VM trae un adaptador **Host-Only**: Windows suele tener la IP `192.168.56.1` en él (compruébalo con `ipconfig`).
2. En el proyecto de GNS3 agrega un nodo **Cloud** que corra en la GNS3 VM y elige su interfaz `eth0` (la Host-Only).
3. Conecta el Cloud a un **Ethernet switch** de GNS3 y a ese switch las interfaces de gestión de los equipos.
4. Las **consolas** de los equipos quedan en la IP de la GNS3 VM (por ejemplo `192.168.56.101:5000`). El puerto exacto se ve en GNS3: clic derecho en el nodo → *Show node information* → *Console*.

### Opción B: Dynamips local (c7200) sin VM
1. Instala el adaptador **Microsoft KM-TEST Loopback** (Administrador de dispositivos → Agregar hardware heredado → Adaptadores de red → Microsoft) y ponle `192.168.56.1/24`.
2. Nodo **Cloud** local → interfaz «Loopback».
3. Las consolas quedan en `127.0.0.1:5000`, `127.0.0.1:5001`…

### EVE-NG
Usa la red **Management (Cloud0)**: los equipos quedan en la red de gestión de EVE (`pnet0`). Las consolas telnet se ven en la página de EVE (IP del servidor EVE, puerto 32769…).

### Firewall de Windows
En PowerShell **como administrador**:
```powershell
netsh advfirewall firewall add rule name="NOC Syslog UDP 5514" dir=in action=allow protocol=UDP localport=5514
```

## 3. Configuración base de los equipos

### R1-BORDE (Cisco IOSv), desde la consola de GNS3
```
enable
configure terminal
hostname R1-BORDE
ip domain-name lab.local
! Usuario para el NOC (la MISMA clave va en SSH_CLAVE del .env)
username noc privilege 15 secret LabNoc2026x
crypto key generate rsa modulus 2048
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
 exit
interface GigabitEthernet0/0
 description Gestion - red del NOC
 ip address 192.168.56.11 255.255.255.0
 no shutdown
 exit
interface GigabitEthernet0/1
 description Enlace a SW1-ACCESO Gi0/1
 ip address 10.0.12.1 255.255.255.252
 no shutdown
end
write memory
! Respaldo local que usa la acción «Restaurar la última configuración respaldada»
copy running-config flash:noc-respaldo.cfg
```
Comprueba desde Windows: `ping 192.168.56.11`.

### SW1-ACCESO (Cisco IOSvL2)
```
enable
configure terminal
hostname SW1-ACCESO
ip domain-name lab.local
username noc privilege 15 secret LabNoc2026x
crypto key generate rsa modulus 2048
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
 exit
interface Vlan1
 ip address 192.168.56.12 255.255.255.0
 no shutdown
 exit
interface GigabitEthernet0/1
 description Enlace a R1-BORDE Gi0/1
end
write memory
```

### Syslog en cada equipo
En el NOC, vista **Configuraciones**:
- Servidor Syslog: `192.168.56.1`, puerto `5514`, UDP.
- Severidad: `0 a 6 (Informational)`. NTP: `pool.ntp.org` (o la IP del servidor NTP del laboratorio).
- Interfaz de origen: `GigabitEthernet0/0` (R1) o `Vlan1` (SW1).

Pega en la consola del equipo las líneas generadas, sin las de comentario. Comprueba con `show logging`.

> **NTP en GNS3:** si los equipos no tienen salida a internet, haz que R1 sea el servidor NTP de los demás (`ntp master 3`) y pon la hora con `clock set`. Así el NOC verá desfases pequeños.

### FortiGate-VM / Huawei (opcional)
- **FortiGate-VM:** `config system interface` → `edit port1` → `set ip 192.168.56.13/24` → `set allowaccess ping ssh`. Luego pega la configuración Fortinet del NOC. Usuario: `config system admin` → `edit noc`.
- **Huawei (eNSP o imagen CE/AR):** `stelnet server enable`, `aaa` → `local-user noc password irreversible-cipher …` → `local-user noc service-type ssh`, `user-interface vty 0 4` → `authentication-mode aaa` / `protocol inbound ssh`. Luego pega la configuración Huawei del NOC.

## 4. Configurar el NOC

### Archivo `.env`
```ini
SSH_USUARIO=noc
SSH_CLAVE=LabNoc2026x
# Si usas la GNS3 VM, agrega su IP para permitir la consola telnet:
CONSOLA_HOSTS_PERMITIDOS=127.0.0.1,localhost,192.168.56.101
```
Reinicia el NOC (`Ctrl+C` y `python app.py`).

### Inventario
Edita o crea cada equipo:

| Campo | R1-BORDE | SW1-ACCESO |
|-------|----------|------------|
| IP | 192.168.56.11 | 192.168.56.12 |
| Marca / modelo | Cisco / IOSv | Cisco / IOSvL2 |
| Tipo de consola | Telnet (GNS3) | Telnet (GNS3) |
| Puerto o destino | 192.168.56.101:5000 (el de GNS3) | 192.168.56.101:5001 |
| Gestión | SSH, puerto 22 | SSH, puerto 22 |
| Equipo simulado | **desmarcado** | **desmarcado** |
| Lista permitida | marcado | marcado |

Luego, en el detalle de cada equipo:
1. **Probar conexión**: debe responder `show clock`.
2. **Leer puertos del equipo**: carga las interfaces reales.

> Los equipos simulados de la semilla se pueden dejar en estado **inactivo** durante la marcha blanca, para que el panel muestre solo el laboratorio.

## 5. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| No llegan eventos | Firewall de Windows o IP de origen distinta | Regla UDP 5514; `logging source-interface`; revisa en Eventos si llegan como «fuente no autorizada» desde otra IP |
| Eventos marcados `fuente_no_autorizada` | La IP del inventario no es la de origen del paquete | Corrige la IP del equipo en el inventario |
| `hora_desfasada` en todos | Reloj del equipo mal | `clock set` / NTP en el equipo |
| «No se pudo conectar por SSH» | SSH no habilitado o sin llaves | `crypto key generate rsa`, `ip ssh version 2`, `transport input ssh` |
| «Usuario o clave SSH incorrectos» | `.env` distinto del equipo | Alinea `SSH_USUARIO` y `SSH_CLAVE` y reinicia el NOC |
| «La llave SSH del equipo cambió» | Se recreó el equipo en GNS3 | Borra la línea del equipo en `data/known_hosts` (solo si tú recreaste el equipo) |
| «CONSOLA_HOSTS_PERMITIDOS» | La consola está en la IP de la GNS3 VM | Agrega esa IP en `.env` |
| `Incompatible ssh peer` | Algoritmos antiguos del IOS | Usa IOSv 15.6 o superior |
