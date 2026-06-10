# -*- coding: utf-8 -*-
"""
sync_tokko.py — Sincroniza propiedades desde la API de Tokko Broker
y genera propiedades.json para la web de Juárez Beltrán.

Uso local (CMD):
    set TOKKO_API_KEY=xxxxxxxxxxxxxxxx
    python sync_tokko.py

En GitHub Actions la key viene del Secret TOKKO_API_KEY.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

API_KEY = os.environ.get("TOKKO_API_KEY", "").strip()
BASE_URL = "https://www.tokkobroker.com/api/v1/property/"
PAGE_SIZE = 20          # recomendado por Tokko: páginas de no más de 20
MAX_PROPS = 2000        # tope de seguridad
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "propiedades.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JBWebSync/1.0",
    "Accept": "application/json",
}


def fetch_page(offset):
    """Trae una página de propiedades desde Tokko."""
    params = {
        "format": "json",
        "key": API_KEY,
        "lang": "es_ar",
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def primera_operacion(prop):
    """Devuelve (tipo_operacion, precio, moneda, periodo) de la primera operación con precio."""
    for op in prop.get("operations", []) or []:
        tipo = op.get("operation_type", "")
        for p in op.get("prices", []) or []:
            return tipo, p.get("price"), p.get("currency"), p.get("period", 0)
        return tipo, None, None, None
    return None, None, None, None


def simplificar(prop):
    """Extrae solo los campos que la web necesita."""
    operacion, precio, moneda, periodo = primera_operacion(prop)

    fotos = []
    for ph in prop.get("photos", []) or []:
        if ph.get("image"):
            fotos.append({
                "url": ph.get("image"),
                "thumb": ph.get("thumb") or ph.get("image"),
            })

    ubicacion = prop.get("location") or {}
    tipo = prop.get("type") or {}

    return {
        "id": prop.get("id"),
        "referencia": prop.get("reference_code"),
        "titulo": prop.get("publication_title") or "",
        "descripcion": prop.get("description") or "",
        "operacion": operacion,                          # "Sale" / "Rent" / etc.
        "precio": precio,
        "moneda": moneda,                                # "USD" / "ARS"
        "muestra_precio": not prop.get("web_price") is False,
        "tipo": tipo.get("name") or "",                  # Departamento, Casa, Local...
        "direccion": prop.get("fake_address") or prop.get("address") or "",
        "barrio": ubicacion.get("name") or "",
        "ubicacion_completa": ubicacion.get("full_location") or "",
        "ambientes": prop.get("room_amount"),
        "dormitorios": prop.get("suite_amount"),
        "banos": prop.get("bathroom_amount"),
        "cocheras": prop.get("parking_lot_amount"),
        "sup_cubierta": prop.get("roofed_surface"),
        "sup_total": prop.get("total_surface"),
        "antiguedad": prop.get("age"),
        "apto_credito": prop.get("is_suitable_for_credit"),
        "lat": prop.get("geo_lat"),
        "lng": prop.get("geo_long"),
        "fotos": fotos,
        "video": (prop.get("videos") or [{}])[0].get("player_url") if prop.get("videos") else None,
        "destacada": prop.get("is_starred_on_web", False),
        "creada": prop.get("created_at"),
        "actualizada": prop.get("deleted_at"),  # Tokko usa este campo como "última modificación"
    }


def main():
    if not API_KEY:
        print("ERROR: falta la variable de entorno TOKKO_API_KEY")
        print('  En CMD:  set TOKKO_API_KEY=tu_key   y volvé a correr el script.')
        sys.exit(1)

    propiedades = []
    offset = 0
    total_api = None

    print("Sincronizando propiedades desde Tokko...")
    while offset < MAX_PROPS:
        try:
            data = fetch_page(offset)
        except requests.HTTPError as e:
            print(f"ERROR HTTP en offset {offset}: {e}")
            print("Respuesta:", e.response.text[:500] if e.response is not None else "(sin cuerpo)")
            sys.exit(1)
        except requests.RequestException as e:
            print(f"ERROR de conexión en offset {offset}: {e}")
            sys.exit(1)

        meta = data.get("meta", {})
        objetos = data.get("objects", [])
        if total_api is None:
            total_api = meta.get("total_count")
            print(f"Total de propiedades activas en Tokko: {total_api}")

        if not objetos:
            break

        for prop in objetos:
            propiedades.append(simplificar(prop))

        offset += PAGE_SIZE
        print(f"  ... {len(propiedades)} procesadas")

        if total_api is not None and offset >= total_api:
            break
        time.sleep(0.5)  # no castigar la API

    resultado = {
        "generado": datetime.now(timezone.utc).isoformat(),
        "total": len(propiedades),
        "propiedades": propiedades,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)

    print(f"\nOK: {len(propiedades)} propiedades guardadas en {OUTPUT}")

    # Resumen rápido por operación y tipo
    ops, tipos = {}, {}
    for p in propiedades:
        ops[p["operacion"]] = ops.get(p["operacion"], 0) + 1
        tipos[p["tipo"]] = tipos.get(p["tipo"], 0) + 1
    print("Por operación:", ops)
    print("Por tipo:", tipos)


if __name__ == "__main__":
    main()
