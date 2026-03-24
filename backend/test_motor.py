"""
Script de prueba — procesa las 3 facturas sin necesitar el servidor corriendo.
Útil para verificar que el motor funciona antes de levantar la API.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from motor import extraer_datos, clasificar

FACTURAS = [
    ("facturas/factura_verde.pdf",    "VERDE"),
    ("facturas/factura_amarilla.pdf", "AMARILLA"),
    ("facturas/factura_roja.pdf",     "ROJA"),
]

ICONOS  = {"verde": "✓", "amarilla": "⚠", "roja": "✗"}
COLORES = {"verde": "\033[32m", "amarilla": "\033[33m", "roja": "\033[31m"}
RESET   = "\033[0m"

print(f"\n{'═'*62}")
print(f"  MOTOR DE APROBACIÓN — HOTEL — TEST")
print(f"{'═'*62}")

for ruta, zona_esperada in FACTURAS:
    if not os.path.exists(ruta):
        print(f"\n  [ERROR] No existe: {ruta}")
        print(f"  Ejecuta primero: python generar_facturas.py")
        continue

    print(f"\n  Procesando: {ruta}")
    print(f"  {'─'*56}")

    datos         = extraer_datos(ruta)
    clasificacion = clasificar(datos)
    zona          = clasificacion["zona"]
    color         = COLORES.get(zona, "")
    icono         = ICONOS.get(zona, "?")

    print(f"  Proveedor : {datos.get('proveedor','—')}")
    print(f"  RUT       : {datos.get('rut','—')}")
    print(f"  Folio     : {datos.get('folio','—')}")
    print(f"  Total CLP : $ {datos.get('total',0):,.0f}")
    print(f"  Vencimiento: {datos.get('fecha_vencimiento','—')}")
    print(f"  {'─'*56}")
    print(f"  Zona      : {color}{zona.upper()} {icono}{RESET}")
    for m in clasificacion["motivos"]:
        print(f"    → {m}")
    print(f"  Acción    : {clasificacion['accion']}")

    ok = zona == zona_esperada.lower()
    status = f"{color}CORRECTO{RESET}" if ok else f"\033[31mESPERADO {zona_esperada}{RESET}"
    print(f"  Test      : {status}")

print(f"\n{'═'*62}")
print(f"  Todos los tests completados.")
print(f"  Para iniciar el servidor: python motor.py")
print(f"  Para ver la API:          http://localhost:8000/docs")
print(f"{'═'*62}\n")
